"""测试数据隔离、助手监督、训练确认开关和完整成功判定。"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from common import atomic_text, data_dir, load_config, read_jsonl, write_json
from data import clean_success, encode_record, group_id, load_tokenizer, prepare_data, reconstruct_messages, split_rows, verify_manifest
from evaluate import final_success, run_evaluation
from train import build_training_args, checkpoint_payload, make_checkpoint_callback, require_training_permission, run_training, validate_resume


@pytest.fixture(scope="session")
def config():
    """读取真实配置，仅测试局部副本，不修改正式参数。"""
    return load_config()


@pytest.fixture(scope="session")
def rows(config):
    """加载真实千条轨迹，测试不会生成额外教师数据。"""
    return read_jsonl(config["dataset_source"])


@pytest.fixture(scope="session")
def tokenizer(config):
    """用本地官方 tokenizer 检查助手区域，不加载神经网络。"""
    return load_tokenizer(config)


@pytest.fixture(scope="session")
def prepared(config, tmp_path_factory):
    """在 pytest 临时目录导出隔离副本，避免篡改真实产物。"""
    clone = dict(config)
    clone["output_root"] = str(tmp_path_factory.mktemp("prepared"))
    prepare_data(clone)
    return clone


def record_for(row):
    """从教师轨迹得到供 tokenizer 接收的最小可见记录。"""
    return {"sample_id": row["scenario"]["scenario_id"], "messages": reconstruct_messages(row)}


def test_clean_pool_has_994(rows):
    """六条越界后恢复轨迹不能混入无错误成功池。"""
    assert sum(clean_success(row) for row in rows) == 994


def test_messages_hide_task_and_call_id(rows):
    """模型输入不出现隐藏目标，助手 JSON 也不携带审计 id。"""
    messages = reconstruct_messages(rows[0])
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": rows[0]["scenario"]["user_request"]}
    assert all("call_id" not in m["content"] for m in messages)
    assert all('"conditions"' not in m["content"] and '"expected_finish"' not in m["content"] for m in messages)
    assert messages[-1]["role"] == "assistant"


def test_groups_ignore_ids_wording_and_order(rows):
    """同一家庭任务的运行编号、意图改写及数组排序不能跨集合。"""
    row = rows[0]
    clone = copy.deepcopy(row)
    clone["scenario"]["scenario_id"] = "another_run"
    clone["scenario"]["user_request"] = "同一任务的另一种说法"
    clone["scenario"]["task"]["intent"] = "改写后的背景"
    clone["scenario"]["home"]["rooms"].reverse()
    clone["scenario"]["home"]["devices"].reverse()
    assert group_id(row) == group_id(clone)


def test_split_sizes_and_no_leakage(rows, config):
    """四个集合互斥，500/100/200按五类均分。"""
    splits, _ = split_rows(rows, config)
    assert {k: len(v) for k, v in splits.items()} == {"train": 500, "validation": 100, "test": 200, "reserve": 194}
    seen = set()
    for selected in splits.values():
        ids = {group_id(row) for row in selected}
        assert not seen & ids
        seen.update(ids)
    for category in ("T1", "T2", "T3", "T4", "T5"):
        assert sum(r["category"] == category for r in splits["train"]) == 100


def test_split_independent_of_file_order(rows, config):
    """反转输入行顺序，不改变确定性划分。"""
    left, _ = split_rows(rows, config)
    right, _ = split_rows(list(reversed(rows)), config)
    assert {k: [group_id(r) for r in v] for k, v in left.items()} == {k: [group_id(r) for r in v] for k, v in right.items()}


def test_not_enough_groups_fails(rows, config):
    """类别配额不足时失败，不复制少量样本凑数。"""
    with pytest.raises(ValueError, match="not enough"):
        split_rows(rows[:5], config)


def test_conflicting_group_category_fails(rows, config):
    """同组被标成不同任务类别时不能静默划分。"""
    clone = copy.deepcopy(rows[0])
    clone["category"] = "T2"
    with pytest.raises(ValueError, match="conflicting"):
        split_rows(rows + [clone], config)


@pytest.mark.parametrize("category", ["T1", "T2", "T3", "T4", "T5"])
def test_all_assistant_spans_and_eos_supervised(rows, tokenizer, config, category):
    """每类完整轨迹的每个助手正文与结束 token 都必须受监督。"""
    row = next(r for r in rows if r["category"] == category and clean_success(r))
    encoded, audit = encode_record(record_for(row), tokenizer, config["max_length"])
    assert audit["assistant_spans"] == len(row["record"]["turns"])
    assert any(label == -100 for label in encoded["labels"])
    assert any(label == tokenizer.eos_token_id for label in encoded["labels"])


def test_no_truncation(rows, tokenizer):
    """超长样本直接失败，不能静默删掉末尾 finish。"""
    with pytest.raises(ValueError, match="truncation forbidden"):
        encode_record(record_for(rows[0]), tokenizer, 10)


def test_template_change_is_detected(rows, tokenizer, config, monkeypatch):
    """损失标记不能改变实际呈现给模型的文本。"""
    monkeypatch.setattr(tokenizer, "chat_template", "changed")
    with pytest.raises(ValueError, match="changed"):
        encode_record(record_for(rows[0]), tokenizer, config["max_length"])


def test_prepared_file_tampering_fails(prepared):
    """准备完成后任何数据文件变化都会被指纹检查发现。"""
    path = data_dir(prepared) / "train.jsonl"
    original = path.read_text()
    atomic_text(path, original + "\n")
    with pytest.raises(ValueError, match="modified"):
        verify_manifest(prepared)
    atomic_text(path, original)
    verify_manifest(prepared)


def test_full_training_requires_confirmation():
    """没有确认开关时完整训练在加载模型之前就被阻止。"""
    with pytest.raises(ValueError, match="confirm-full-training"):
        require_training_permission("train", False)
    require_training_permission("smoke", False)


def test_smoke_resume_rejected_before_model_load(config):
    """实际进入smoke分支检查模式变量，且不能载入完整恢复路径。"""
    with pytest.raises(ValueError, match="smoke does not resume"):
        run_training(config, "smoke", resume="not-a-smoke-checkpoint")


def test_resume_dataset_change_rejected(config, tmp_path):
    """相同运行目录和配置也不能掩盖数据版本变化。"""
    checkpoint = tmp_path / "checkpoint-1"
    write_json(checkpoint / "trainer_state.json", {"global_step": 1})
    write_json(tmp_path / "run_config.json", {"config": config, "data_manifest_sha256": "old"})
    with pytest.raises(ValueError, match="dataset version"):
        validate_resume(tmp_path, str(checkpoint), config, "new")


def test_resume_from_other_run_rejected(config, tmp_path):
    """其他运行目录中的检查点不能混入当前实验。"""
    with pytest.raises(ValueError, match="belong"):
        validate_resume(tmp_path / "current", str(tmp_path / "other" / "checkpoint-1"), config, "hash")


def test_epoch_args_keep_all_checkpoints(config, tmp_path):
    """每个 epoch 保存且不限制保留数量；冒烟只做两个更新周期。"""
    args = build_training_args(config, tmp_path, True)
    assert args.num_train_epochs == 2
    assert args.gradient_accumulation_steps == 1
    assert args.save_strategy.value == "epoch"
    assert args.save_total_limit is None
    assert args.save_only_model is False
    formal = build_training_args(config, tmp_path, False)
    assert formal.per_device_train_batch_size == 4
    assert formal.gradient_accumulation_steps == 2
    assert formal.save_strategy.value == "epoch"
    assert formal.save_total_limit is None
    assert formal.save_only_model is False
    assert formal.logging_steps == 1


def test_checkpoint_index_requires_optimizer_state(config, tmp_path):
    """只有 adapter 的目录不能被标为完整可恢复检查点。"""
    callback = make_checkpoint_callback(config, tmp_path, "manifest")
    with pytest.raises(ValueError, match="incomplete"):
        callback.on_save(None, SimpleNamespace(epoch=1, global_step=1), None)


def test_checkpoint_metadata_binds_data(config):
    """检查点记录 epoch、step 和对应数据指纹。"""
    payload = checkpoint_payload(SimpleNamespace(epoch=2, global_step=2), config, "manifest_hash")
    assert payload["epoch"] == 2 and payload["global_step"] == 2
    assert payload["data_manifest_sha256"] == "manifest_hash"


@pytest.mark.parametrize("category", ["T3", "T4", "T5"])
def test_no_d6_is_not_full_success(category):
    """没有语义复核时四程序标签全过也不能宣称完整成功。"""
    row = {"category": category, "labels": {"C-1": True, "C-2": True, "C-3": True, "C-4": True}, "d6": "待审"}
    assert final_success(row, "off") is None


def test_final_test_requires_confirmation(config, tmp_path):
    """200条最终测试不会被预测试入口顺手运行。"""
    with pytest.raises(ValueError, match="confirm-final-test"):
        run_evaluation(config, "test", tmp_path)


def test_unknown_config_key_fails(config, tmp_path):
    """拼错配置键不会被忽略。"""
    clone = dict(config)
    clone["unknown"] = 1
    path = tmp_path / "config.json"
    write_json(path, clone)
    with pytest.raises(ValueError, match="config keys"):
        load_config(path)
