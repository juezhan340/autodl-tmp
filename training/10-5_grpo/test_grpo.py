"""无网络CPU回归：轨迹重放、奖励边界、分组、原始token和冻结参考。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime import annotate_jsonl_tree, load_config, read_jsonl
from trajectory import preprocess, unsafe_attempt
from reward import assign_advantages, judge_one, score, valid_review
from rollout import BatchService, generate_group, pack_calls
from model_math import activate, adapter_digest, make_batch, surrogate_loss, token_logps
from new_demo.agents.A_policy import ScriptPolicy
from new_demo.env.B_home_env import HomeEnv
from new_demo.eval.C_episode_runner import EpisodeRunner

ARCHIVE = Path("/root/autodl-tmp/training_runs/10-5_sft/comparison_test_20261005")


def sample(model, sample_id):
    """测试夹具仅读归档，其他机器没有归档时明确跳过对应重放测试。"""
    path = ARCHIVE / model / "trajectories.jsonl"
    if not path.exists():
        pytest.skip("server archive is not available")
    return next(row for row in read_jsonl(path) if row["sample_id"] == sample_id)


def semantic(truthful=True, complete=True):
    """返回显式人工设定的测试判定，不把它冒充真实API评分。"""
    return {"status": "reviewed", "truthful": truthful, "complete_and_truthful": complete}


def test_config_and_removed_terms():
    """配置16轨迹与micro2累计8一致，删除三种用户不希望启用的项。"""
    config = load_config()
    assert config["groups_per_update"] * config["num_generations"] == 16
    assert config["micro_batch"] * config["accumulation"] == 16
    assert not ({"waste", "fabrication", "call_cost"} & set(config["reward_weights"]))


def test_actual_progress_and_false_finish():
    """正确T2累计进度1，错误T2只有2/3；多余调用没有单独处罚。"""
    config = load_config()
    good = preprocess(sample("epoch2", "sc_T2_097"))
    bad = preprocess(sample("epoch3", "sc_T2_097"))
    assert good["progress_final"] == 1 and sum(item["progress_delta"] for item in good["steps"]) == 1
    assert good["evidence_fraction"] == 1
    assert score(good, semantic(), config)["total_reward"] == 6
    assert bad["progress_final"] == pytest.approx(2/3)
    assert bad["false_finish"] and bad["error_count"] == 0 and not bad["unsafe_events"]
    assert score(bad, semantic(False, False), config)["total_reward"] == pytest.approx(-0.25)


def test_safety_gate_and_enum_error():
    """越界恢复拒绝仍危险，错误枚举只按真实错误回执处理。"""
    config = load_config()
    unsafe = preprocess(sample("epoch3", "sc_T4_142"))
    assert score(unsafe, None, config)["total_reward"] == -5
    ordinary = preprocess(sample("epoch3", "sc_T2_376"))
    assert ordinary["error_count"] >= 1 and not ordinary["unsafe_events"]
    row = sample("epoch3", "sc_T4_142")
    env = HomeEnv()
    env.reset(row["scenario"])
    event = next(event for turn in row["record"]["turns"] for event in turn["events"] if event["tool_name"] == "execute_action" and event["arguments"]["action"] == "set_percentage")
    assert "out_of_safe_range_attempt" in unsafe_attempt(env.scenario, "T1", event)


def test_keep_restored_is_still_a_process_violation():
    """显式keep被改坏后恢复，C终态能过但奖励门控保留过程证据。"""
    row = sample("epoch2", "sc_T2_097")
    scenario = copy.deepcopy(row["scenario"])
    scenario["episode_config"]["max_turns"] = 20
    responses = [turn["tool_calls"][0] for turn in row["record"]["turns"]]
    responses[-1:-1] = [{"name": "execute_action", "arguments": {"device_id": "device_study_light", "action": "turn_on", "params": {}}}, {"name": "execute_action", "arguments": {"device_id": "device_study_light", "action": "turn_off", "params": {}}}]
    run = EpisodeRunner(ScriptPolicy(responses)).run(scenario)
    derived = {"sample_id": "keep-regression", "category": "T2", "scenario": scenario, "record": run.record, "labels": run.labels.to_dict()}
    evidence = preprocess(derived)
    assert evidence["labels"]["C-2"]
    assert any(item["reason"] == "keep_violated_during_episode" for item in evidence["unsafe_events"])


def test_query_evidence_disabled_and_semantics_pending():
    """查询空conditions不自动奖励满进度，待审结尾不变成零分。"""
    evidence = preprocess(sample("epoch3", "sc_T5_192"))
    assert evidence["progress_final"] == 0 and evidence["evidence_fraction"] == 0
    assert evidence["evidence_status"].startswith("disabled")
    assert score(evidence, None, load_config())["total_reward"] is None


def test_corrupt_event_is_rejected():
    """修改真实回执时在预处理层报错，不能把损坏数据当坏模型。"""
    row = sample("epoch2", "sc_T2_097")
    row["record"]["turns"][0]["events"][0]["result"]["ok"] = False
    with pytest.raises(ValueError, match="replay mismatch"):
        preprocess(row)


def test_group_membership_and_pending():
    """组内任务完全相同且四条都有分，优势只减本组均值。"""
    rows = [{"group_id": "a", "scenario": {"task": 1}} for _ in range(4)]
    scores = [{"status": "scored", "total_reward": value} for value in (6, 4, 2, 0)]
    assert assign_advantages(rows, scores, 4) == [3, 1, -1, -3]
    with pytest.raises(ValueError):
        assign_advantages(rows[:-1], scores[:-1], 4)
    scores[-1] = {"status": "pending", "total_reward": None}
    with pytest.raises(ValueError, match="pending"):
        assign_advantages(rows, scores, 4)
    scores[-1] = {"status": "scored", "total_reward": float("nan")}
    with pytest.raises(ValueError, match="finite"):
        assign_advantages(rows, scores, 4)
    scores[-1] = {"status": "scored", "total_reward": 0}
    rows[-1]["scenario"] = {"task": 2}
    with pytest.raises(ValueError):
        assign_advantages(rows, scores, 4)


class FakeJudge:
    """无网络三票客户端，支持合法回复和无效布尔类型。"""

    def __init__(self, invalid=False):
        """保存测试模式并计数，未创建真实API客户端。"""
        self.invalid = invalid
        self.calls = 0

    def complete_json(self, messages, role):
        """只返回测试JSON，模拟1不能冒充严格布尔true。"""
        self.calls += 1
        return SimpleNamespace(request_id=str(self.calls)), {"truthful": 1 if self.invalid else True, "answers_request": True}


def test_judge_schema_and_three_votes():
    """三票全合法才可使用，不合法票不会被记成模型失败。"""
    row = sample("epoch2", "sc_T2_097")
    client = FakeJudge()
    assert judge_one(row, client)["status"] == "reviewed" and client.calls == 3
    assert judge_one(row, FakeJudge(True))["status"] == "pending"


def test_review_cache_validates_aggregate_and_votes():
    """待审、缺票及聚合值被篡改的缓存均不可复用。"""
    votes = [{"truthful": True, "answers_request": True} for _ in range(3)]
    item = {"status": "reviewed", "truthful": True, "complete_and_truthful": True, "votes": votes}
    assert valid_review(item)
    item["complete_and_truthful"] = False
    assert not valid_review(item)
    assert not valid_review({"status": "pending"})


def test_jsonl_annotation_preserves_original_bytes(tmp_path):
    """补运行日志说明时只写md，原JSONL字节和末尾换行不变。"""
    path = tmp_path / "completions.jsonl"
    original = b'{"status": "ok"}\n'
    path.write_bytes(original)
    annotate_jsonl_tree(tmp_path)
    assert path.read_bytes() == original
    assert "1 行" in path.with_suffix(".md").read_text(encoding="utf-8")


class EchoBackend:
    """只返回请求编号的CPU批量后端，用于核对并发路由。"""

    def __init__(self):
        """保存实际批次大小，不依赖GPU和网络。"""
        self.sizes = []

    def generate(self, requests):
        """按批内原顺序返回编号，检测Future是否串线。"""
        self.sizes.append(len(requests))
        return [row["value"] for row in requests]


def test_four_way_batch_routes_results_and_closes():
    """四个请求合成一个批次，结果对应原请求且线程结束。"""
    backend = EchoBackend()
    service = BatchService(backend, 4)
    try:
        futures = [service.submit({"value": index}) for index in range(4)]
        assert [future.result(timeout=3) for future in futures] == list(range(4))
        assert backend.sizes == [4]
    finally:
        service.close()
    assert not service.thread.is_alive()


def test_token_packing_masks_and_prefix_mismatch():
    """保留观察attention、屏蔽观察loss，并拒绝不一致的采样历史。"""
    calls = [{"input_ids": [1, 2], "generated_ids": [3, 4]}, {"input_ids": [1, 2, 3, 4, 5, 6], "generated_ids": [7, 8]}]
    packed = pack_calls(calls, 16)
    assert packed["policy_mask"] == [0, 0, 1, 1, 0, 0, 1, 1]
    batch = make_batch([packed], 0, "cpu")
    assert batch["attention_mask"].tolist() == [[1]*8]
    calls[-1]["input_ids"][2] = 9
    with pytest.raises(ValueError, match="prefix"):
        pack_calls(calls, 16)


def test_loss_ignores_nonpolicy_overflow():
    """非采样位置不能因exp巨大而出现inf乘0，梯度方向符合优势。"""
    import torch
    current = torch.tensor([[-2.0, -1000.0]], requires_grad=True)
    old = torch.tensor([[-2.0, 0.0]])
    loss, metrics = surrogate_loss(current, old, old, torch.tensor([1.0]), torch.tensor([[1, 0]]), 1, .02, .2)
    assert torch.isfinite(loss) and metrics["kl_sum"] == 0
    loss.backward()
    assert current.grad[0, 0] < 0 and current.grad[0, 1] == 0


def test_tiny_model_selected_logits_and_reference_freeze():
    """CPU小模型验证稀疏logits等价、policy梯度存在且参考没有更新。"""
    import torch
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict, set_peft_model_state_dict
    from transformers import Qwen2Config, Qwen2ForCausalLM
    from trl.trainer.utils import selective_log_softmax
    torch.manual_seed(7)
    base = Qwen2ForCausalLM(Qwen2Config(vocab_size=32, hidden_size=16, intermediate_size=32, num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1))
    lora = LoraConfig(task_type="CAUSAL_LM", r=2, lora_alpha=4, lora_dropout=0, target_modules=["q_proj", "v_proj"])
    model = get_peft_model(base, lora, adapter_name="policy")
    for name, parameter in model.named_parameters():
        if ".lora_B.policy." in name:
            torch.nn.init.normal_(parameter, std=.02)
    state = {key: value.detach().clone() for key, value in get_peft_model_state_dict(model, adapter_name="policy").items()}
    model.add_adapter("sft_reference", copy.deepcopy(lora))
    set_peft_model_state_dict(model, state, adapter_name="sft_reference")
    activate(model, "policy")
    packed = pack_calls([{"input_ids": [1, 2], "generated_ids": [3, 4]}, {"input_ids": [1, 2, 3, 4, 5, 6], "generated_ids": [7, 8]}], 16)
    batch = make_batch([packed], 0, "cpu")
    model.eval()
    current = token_logps(model, batch, 1)
    dense = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"], use_cache=False).logits
    assert torch.allclose(current, selective_log_softmax(dense[:, batch["positions"]], batch["targets"]), atol=1e-6)
    activate(model, "sft_reference")
    with torch.no_grad():
        reference = token_logps(model, batch, 1)
    assert torch.allclose(current.detach(), reference, atol=1e-6)
    frozen_hash = adapter_digest(model, "sft_reference")
    activate(model, "policy")
    optimizer = torch.optim.SGD([item for item in model.parameters() if item.requires_grad], lr=.1)
    loss, _ = surrogate_loss(current, current.detach(), reference, torch.tensor([1.0]), batch["mask"], packed["sampled_tokens"], .02, .2)
    loss.backward()
    optimizer.step()
    assert adapter_digest(model, "sft_reference") == frozen_hash
    assert token_logps(model, batch, 1).mean() > current.detach().mean()
