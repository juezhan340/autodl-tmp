"""实现与TRL同形的clip/KL/DAPO冒烟损失，显式分离上下文和策略mask。"""

from __future__ import annotations

import copy
import hashlib


def activate(model, name):
    """切换adapter后重新锁定梯度归属，基座与参考始终不进优化器。"""
    model.set_adapter(name)
    for key, parameter in model.named_parameters():
        parameter.requires_grad_(name == "policy" and (".lora_A.policy." in key or ".lora_B.policy." in key))


def adapter_digest(model, name):
    """对FP32 adapter逐张量取指纹，检查参考未改与原权重精度一致。"""
    from peft import get_peft_model_state_dict
    result = hashlib.sha256()
    for key, value in sorted(get_peft_model_state_dict(model, adapter_name=name).items()):
        result.update(key.encode())
        result.update(value.detach().cpu().float().contiguous().numpy().tobytes())
    return result.hexdigest()


def load_model(config):
    """加载一份BF16基座和两套FP32 SFT副本，不修改原SFT检查点。"""
    import torch
    from peft import PeftModel, get_peft_model_state_dict, set_peft_model_state_dict
    from safetensors.torch import load_file
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model = AutoModelForCausalLM.from_pretrained(config["base_model"], local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa")
    model = PeftModel.from_pretrained(model, config["sft_adapter"], adapter_name="policy", is_trainable=True)
    reference_config = copy.deepcopy(model.peft_config["policy"])
    reference_config.inference_mode = True
    model.add_adapter("sft_reference", reference_config)
    for key, parameter in model.named_parameters():
        if ".lora_A." in key or ".lora_B." in key:
            parameter.data = parameter.data.float()
    saved = load_file(config["sft_adapter"] + "/adapter_model.safetensors")
    set_peft_model_state_dict(model, saved, adapter_name="policy")
    set_peft_model_state_dict(model, saved, adapter_name="sft_reference")
    for name in ("policy", "sft_reference"):
        current = get_peft_model_state_dict(model, adapter_name=name)
        if set(current) != set(saved) or any(value.dtype != torch.float32 or not torch.equal(value.cpu(), saved[key]) for key, value in current.items()):
            raise ValueError("adapter FP32 tensors differ from the saved SFT adapter")
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.p = 0.0
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.to("cuda")
    activate(model, "policy")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(config["base_model"], local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def make_batch(packed, pad_id, device):
    """右padding训练序列；真实观察attention为1，loss mask保持0。"""
    import torch
    width = max(len(row["input_ids"]) for row in packed)
    ids = torch.full((len(packed), width), pad_id, dtype=torch.long, device=device)
    attention = torch.zeros_like(ids)
    policy = torch.zeros_like(ids)
    for index, row in enumerate(packed):
        length = len(row["input_ids"])
        ids[index, :length] = torch.tensor(row["input_ids"], device=device)
        attention[index, :length] = 1
        policy[index, :length] = torch.tensor(row["policy_mask"], device=device)
    positions = policy[:, 1:].any(dim=0).nonzero().flatten()
    if not len(positions):
        raise ValueError("no sampled policy tokens")
    return {"input_ids": ids, "attention_mask": attention, "positions": positions, "mask": policy[:, positions + 1], "targets": ids[:, positions + 1]}


def token_logps(model, batch, temperature):
    """只为采样位置的并集计算词表logits，避免回执位置的巨大输出矩阵。"""
    from trl.trainer.utils import selective_log_softmax
    logits = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"], logits_to_keep=batch["positions"], use_cache=False).logits
    return selective_log_softmax(logits / temperature, batch["targets"])


def surrogate_loss(current, old, reference, advantages, mask, denominator, beta, epsilon):
    """沿用token概率比值、裁剪和KL估计；分母只计累计更新的采样token。"""
    import torch
    if denominator <= 0:
        raise ValueError("policy token denominator must be positive")
    # 非策略位置先清零，避免无意义的巨大KL产生inf再乘0变成NaN。
    active = mask.bool()
    current = torch.where(active, current, torch.zeros_like(current))
    old = torch.where(active, old, torch.zeros_like(old))
    reference = torch.where(active, reference, torch.zeros_like(reference))
    ratio = torch.exp(current - old)
    clipped = ratio.clamp(1 - epsilon, 1 + epsilon)
    advantage = advantages[:, None]
    difference = reference - current
    kl = torch.exp(difference) - difference - 1
    per_token = -torch.minimum(ratio * advantage, clipped * advantage) + beta * kl
    loss = (per_token * mask).sum() / denominator
    return loss, {"kl_sum": float((kl.detach() * mask).sum()), "initial_logprob_delta": float(((current.detach() - old).abs() * mask).max()), "clip_tokens": int(((ratio.detach() - clipped.detach()).abs() > 0).logical_and(mask.bool()).sum())}
