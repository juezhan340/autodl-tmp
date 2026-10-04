"""使用 TRL/PEFT 训练，默认只检查；微型冒烟和完整训练有独立入口。"""

from __future__ import annotations

import argparse
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from common import annotate_json_tree, data_dir, digest, file_sha256, load_config, read_json, write_json
from data import load_tokenizer, prepare_data, tokenized_split, verify_manifest
from progress import TrainingProgress, make_progress_callback


def require_training_permission(mode: str, confirmed: bool) -> None:
    """完整训练必须显式确认，检查和微型冒烟不能绕过该入口。"""
    if mode == "train" and not confirmed:
        raise ValueError("full training requires --confirm-full-training")


def checkpoint_payload(state, config: dict, data_manifest_hash: str) -> dict:
    """将 epoch 和 step 与配置、数据版本绑定，便于恢复和追溯。"""
    return {"epoch": round(float(state.epoch or 0), 6), "global_step": int(state.global_step), "config_sha256": digest(config), "data_manifest_sha256": data_manifest_hash}


def make_checkpoint_callback(config: dict, run_dir: Path, manifest_hash: str):
    """逐次登记 epoch 检查点，不删除历史 adapter 或优化器状态。"""
    from transformers import TrainerCallback

    class EpochCheckpointIndex(TrainerCallback):
        """每次 Trainer 保存后登记文件存在性和元数据。"""

        def on_save(self, args, state, control, **kwargs):
            """记录完整可恢复检查点，缺文件立即让预测试失败。"""
            checkpoint = run_dir / f"checkpoint-{state.global_step}"
            required = ("adapter_model.safetensors", "adapter_config.json", "trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth")
            missing = [name for name in required if not (checkpoint / name).exists()]
            if missing:
                raise ValueError(f"checkpoint incomplete: {missing}")
            payload = checkpoint_payload(state, config, manifest_hash)
            payload["path"] = str(checkpoint)
            payload["adapter_sha256"] = file_sha256(checkpoint / "adapter_model.safetensors")
            index_path = run_dir / "checkpoint_index.json"
            index = read_json(index_path) if index_path.exists() else []
            index = [row for row in index if row["global_step"] != state.global_step]
            index.append(payload)
            write_json(index_path, index)
            annotate_json_tree(checkpoint)
            return control

    return EpochCheckpointIndex()


def sequence_length(row: dict) -> int:
    """按 token 长度选择冒烟样本，验证实际最长输入的显存路径。"""
    return len(row["input_ids"])


def validate_resume(run_dir: Path, resume: str, config: dict, manifest_hash: str) -> None:
    """恢复必须指向当前运行，并匹配配置和数据版本。"""
    resume_path = Path(resume).resolve()
    if resume_path.parent != run_dir.resolve() or not (resume_path / "trainer_state.json").exists():
        raise ValueError("resume checkpoint must belong to this run")
    saved = read_json(run_dir / "run_config.json")
    if saved["config"] != config:
        raise ValueError("resume configuration differs from the saved run")
    if saved["data_manifest_sha256"] != manifest_hash:
        raise ValueError("resume dataset version differs from the saved run")


def build_training_args(config: dict, run_dir: Path, smoke: bool):
    """配置官方 Trainer；每个 epoch 保存、验证且不轮换删除检查点。"""
    from trl import SFTConfig
    return SFTConfig(
        output_dir=str(run_dir),
        num_train_epochs=2 if smoke else config["epochs"],
        per_device_train_batch_size=config["micro_batch_size"],
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=1 if smoke else config["gradient_accumulation_steps"],
        learning_rate=config["learning_rate"],
        warmup_ratio=0 if smoke else 0.1,
        lr_scheduler_type="linear",
        optim="adamw_torch",
        max_grad_norm=1.0,
        bf16=True,
        tf32=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        save_strategy="epoch",
        eval_strategy="epoch",
        save_total_limit=None,
        save_only_model=False,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=1,
        report_to="none",
        seed=config["seed"],
        data_seed=config["seed"],
        max_length=config["max_length"],
        packing=False,
        completion_only_loss=False,
        assistant_only_loss=False,
        dataset_kwargs={"skip_prepare_dataset": True},
        remove_unused_columns=False,
        dataloader_num_workers=0,
        dataloader_pin_memory=True,
    )


def run_training(config: dict, mode: str, confirmed: bool = False, resume: str | None = None) -> dict:
    """冒烟只用一个micro-batch做两次更新；完整500条仅在确认入口执行。"""
    require_training_permission(mode, confirmed)
    manifest = prepare_data(config)
    plan = {"mode": mode, "full_training_started": mode == "train", "train_count": manifest["splits"]["train"]["count"], "validation_count": manifest["splits"]["validation"]["count"], "test_count": manifest["splits"]["test"]["count"], "effective_batch": config["micro_batch_size"] * config["gradient_accumulation_steps"]}
    if mode == "check":
        return plan
    if mode not in ("smoke", "train"):
        raise ValueError("unknown training mode")
    smoke = mode == "smoke"
    if smoke:
        plan["effective_batch"] = config["micro_batch_size"]
    import torch
    from transformers import set_seed
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise ValueError("CUDA with BF16 is required for this experiment")
    if smoke and resume:
        raise ValueError("smoke does not resume a full training checkpoint")
    set_seed(config["seed"])
    root = Path(config["output_root"])
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / ("smoke-" + suffix if mode == "smoke" else "sft-main")
    manifest_hash = file_sha256(data_dir(config) / "manifest.json")
    if run_dir.exists() and not resume:
        raise ValueError("run directory exists; explicit checkpoint resume is required")
    if resume:
        validate_resume(run_dir, resume, config, manifest_hash)
    run_dir.mkdir(parents=True, exist_ok=True)
    progress = TrainingProgress(run_dir, config, mode)
    try:
        return execute_training(config, mode, plan, run_dir, manifest_hash, progress, resume)
    except BaseException as exc:
        progress.update(status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed", error=f"{type(exc).__name__}: {exc}")
        raise


def execute_training(config: dict, mode: str, plan: dict, run_dir: Path, manifest_hash: str, progress: TrainingProgress, resume: str | None) -> dict:
    """执行训练主体，将数据准备、加载、更新和异常状态分别落盘。"""
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, DataCollatorForSeq2Seq
    from trl import SFTTrainer
    smoke = mode == "smoke"
    tokenizer = load_tokenizer(config)
    train_rows = tokenized_split(config, "train", tokenizer)
    validation_rows = tokenized_split(config, "validation", tokenizer)
    if smoke:
        train_rows = sorted(train_rows, key=sequence_length, reverse=True)[:config["micro_batch_size"]]
        validation_rows = validation_rows[:2]
    write_json(run_dir / "run_config.json", {"config": config, "mode": mode, "training_examples": len(train_rows), "validation_examples": len(validation_rows), "data_manifest_sha256": manifest_hash})
    progress.update(phase="loading_model", train_count=len(train_rows), validation_count=len(validation_rows))
    model = AutoModelForCausalLM.from_pretrained(config["base_model"], local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa")
    model.config.use_cache = False
    lora = LoraConfig(task_type="CAUSAL_LM", r=config["lora_r"], lora_alpha=config["lora_alpha"], lora_dropout=config["lora_dropout"], bias="none", target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True, pad_to_multiple_of=8, label_pad_token_id=-100)
    torch.cuda.reset_peak_memory_stats()
    trainer = SFTTrainer(model=model, args=build_training_args(config, run_dir, smoke), train_dataset=Dataset.from_list(train_rows), eval_dataset=Dataset.from_list(validation_rows), processing_class=tokenizer, data_collator=collator, peft_config=lora, callbacks=[make_checkpoint_callback(config, run_dir, manifest_hash), make_progress_callback(progress)])
    started = time.perf_counter()
    result = trainer.train(resume_from_checkpoint=resume)
    elapsed = time.perf_counter() - started
    if not math.isfinite(float(result.training_loss)):
        raise ValueError("training produced a non-finite loss")
    final_dir = run_dir / "selected_adapter"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    index = read_json(run_dir / "checkpoint_index.json")
    if smoke and (trainer.state.global_step != 2 or len(index) != 2):
        raise ValueError("smoke must produce exactly two updates and two epoch checkpoints")
    if not smoke and len(index) != config["epochs"]:
        raise ValueError("full training must retain a checkpoint for every epoch")
    summary = {**plan, "run_dir": str(run_dir), "updates": trainer.state.global_step, "training_examples_used": len(train_rows), "epochs_completed": trainer.state.epoch, "checkpoint_count": len(index), "best_checkpoint": trainer.state.best_model_checkpoint, "selected_adapter": str(final_dir), "training_loss": result.training_loss, "elapsed_seconds": round(elapsed, 3), "gpu_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1), "gpu_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 1), "trainable_parameters": sum(p.numel() for p in trainer.model.parameters() if p.requires_grad), "log_history": trainer.state.log_history}
    write_json(run_dir / "training_summary.json", summary)
    annotate_json_tree(run_dir)
    progress.update(status="completed", phase="completed", checkpoint_count=len(index), best_checkpoint=Path(trainer.state.best_model_checkpoint).name if trainer.state.best_model_checkpoint else None, selected_adapter="selected_adapter")
    del trainer, model
    torch.cuda.empty_cache()
    return summary


def main() -> None:
    """默认只检查；完整训练与恢复都必须明确确认。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--mode", choices=("check", "smoke", "train"), default="check")
    parser.add_argument("--confirm-full-training", action="store_true")
    parser.add_argument("--resume-from-checkpoint")
    args = parser.parse_args()
    require_training_permission(args.mode, args.confirm_full_training)
    summary = run_training(load_config(args.config), args.mode, args.confirm_full_training, args.resume_from_checkpoint)
    print(summary)


if __name__ == "__main__":
    main()
