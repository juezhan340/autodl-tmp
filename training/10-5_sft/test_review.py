"""使用无网络假客户端测试D6并发补审、确认开关和缓存恢复。"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import review
from common import atomic_text, digest, read_json, write_json, write_jsonl


class FakeClient:
    """提供三票的确定性结果，不读取密钥、不连接任何服务。"""

    bad_verdict = False

    def __init__(self, env_path, raw_dir):
        """给补审入口提供非敏感配置与独立计数器。"""
        self.api_key = "nonfunctional-test-value"
        self.external_model = "fake-judge"
        self.external_temperature = 0.7
        self.base_url = "https://example.invalid"
        self.http_attempts = 0
        self.lock = threading.Lock()

    def complete_json(self, messages, **kwargs):
        """每次模拟一票并计数，无HTTP传输。"""
        with self.lock:
            self.http_attempts += 1
        return None, {"verdict": "不合法" if self.bad_verdict else "对"}


@pytest.fixture
def sources(tmp_path, monkeypatch):
    """生成四份最小评测输入，只允许epoch2和epoch3进入语义补审。"""
    monkeypatch.setattr(review, "CountedClient", FakeClient)
    monkeypatch.setattr(FakeClient, "bad_verdict", False)
    for name in review.MODELS:
        category = "T1" if name == "epoch1" else "T5"
        passed = name != "baseline"
        row = {"sample_id": "same-task-id", "category": category, "scenario": {"user_request": "卧室现在多少度？"}, "record": {"scenario_id": "same-task-id", "turns": [], "finish": {"summary": "20度", "outcome": "completed"}}, "labels": {key: passed for key in ("C-1", "C-2", "C-3", "C-4")}, "d6": "跳过" if category == "T1" else "待审", "d6_votes": [], "final_success": passed if category == "T1" else None}
        write_jsonl(tmp_path / name / "trajectories.jsonl", [row], "测试夹具")
        write_json(tmp_path / name / "summary.json", {"total": 1, "generation_errors": 0, "few_shot": False})
    return tmp_path


def test_review_requires_confirmation(tmp_path):
    """收费确认失败必须发生在读取密钥或源文件之前。"""
    with pytest.raises(ValueError, match="confirm-api-review"):
        review.run_review(tmp_path, tmp_path / ".env.deepseek", 100, False)


def test_review_workers_capped_at_100(tmp_path):
    """并发上限不允许因参数拼错而无限扩张。"""
    with pytest.raises(ValueError, match="between 1 and 100"):
        review.run_review(tmp_path, tmp_path / ".env.deepseek", 101, True)


def test_review_uses_three_votes_and_preserves_sources(sources):
    """同任务不同模型独立投票，完整源轨迹仍保留原位。"""
    result = review.run_review(sources, sources / ".env.deepseek", 100, True)
    assert result["eligible_trajectories"] == 2
    assert result["http_attempts_this_invocation"] == 6
    assert result["original_source_files_unchanged"]
    assert result["models"]["baseline"]["full_success_total"] == 0
    assert result["models"]["epoch1"]["full_success_total"] == 1
    assert result["models"]["epoch2"]["full_success_total"] == 1
    assert len(read_json(sources / "semantic_review/review_manifest.json")["source_sha256"]) == 4


def test_completed_cache_does_not_repeat_calls(sources):
    """恢复已完成评审不再发送新的票。"""
    review.run_review(sources, sources / ".env.deepseek", 2, True)
    resumed = review.run_review(sources, sources / ".env.deepseek", 100, True)
    assert resumed["jobs_this_invocation"] == 0
    assert resumed["http_attempts_this_invocation"] == 0


def test_invalid_votes_remain_pending_and_explicit_retry(sources, monkeypatch):
    """无效三票保持待确认，显式重试才重新调用六票。"""
    monkeypatch.setattr(FakeClient, "bad_verdict", True)
    result = review.run_review(sources, sources / ".env.deepseek", 2, True)
    assert result["models"]["epoch2"]["pending_semantic_total"] == 1
    assert result["models"]["epoch2"]["full_success_total"] == 0
    monkeypatch.setattr(FakeClient, "bad_verdict", False)
    resumed = review.run_review(sources, sources / ".env.deepseek", 2, True)
    assert resumed["jobs_this_invocation"] == 0
    retried = review.run_review(sources, sources / ".env.deepseek", 2, True, retry_system_failures=True)
    assert retried["http_attempts_this_invocation"] == 6
    assert retried["models"]["epoch2"]["pending_semantic_total"] == 0


def test_cache_tail_recovered_and_version_checked(tmp_path):
    """仅去掉中断半行，完整源版本冲突不能吞掉。"""
    row = {"sample_id": "x"}
    entry = {"model": "epoch1", "sample_id": "x", "source_row_sha256": digest(row), "d6": "对"}
    path = tmp_path / "cache.jsonl"
    write_jsonl(path, [entry], "测试缓存")
    atomic_text(path, path.read_text() + '{"unfinished":')
    assert review.load_cache(path, {("epoch1", "x"): row})[("epoch1", "x")]["d6"] == "对"
    with pytest.raises(ValueError, match="different source"):
        review.load_cache(path, {("epoch1", "x"): {"sample_id": "changed"}})
