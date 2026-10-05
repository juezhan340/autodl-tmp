"""维护500训练任务覆盖与反馈优先级，不缓存可用于跨policy训练的旧轨迹。"""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

from runtime import digest, read_json, read_jsonl, write_json

CATEGORIES = ("T1", "T2", "T3", "T4", "T5")


def classify(scores):
    """区分可靠结构差异、软差异、同分成功和同分困难。"""
    rewards = [row["total_reward"] for row in scores]
    variable = max(rewards) - min(rewards) > 1e-8
    structural = ("progress", "evidence", "ordinary_error", "false_finish", "budget")
    reliable = any(len({row["terms"].get(key, 0) for row in scores}) > 1 for key in structural)
    reliable = reliable or len({row["safety_gate"] for row in scores}) > 1
    easy = all(row["terms"].get("success", 0) > 0 and not row["safety_gate"] for row in scores)
    return {"bucket": "informative" if variable else "easy" if easy else "hard", "structural_variation": reliable, "reward_range": max(rewards) - min(rewards)}


class FeedbackSampler:
    """采样器只写抽样元数据，实际新轨迹由训练主进程独占生成。"""

    def __init__(self, config):
        """核对分割隔离，建立剩余400优先、历史100随后覆盖的顺序。"""
        self.config = config
        self.rng = random.Random(config["seed"])
        root = Path(config["sft_data"])
        self.tasks = read_jsonl(root / "train_scenarios.jsonl")
        forbidden = {row["group_id"] for split in ("validation", "test") for row in read_jsonl(root / f"{split}_scenarios.jsonl")}
        counts = Counter(row["category"] for row in self.tasks)
        if len(self.tasks) != 500 or counts != Counter({name: 100 for name in CATEGORIES}):
            raise ValueError("formal run requires the balanced 500-task training pool")
        if len({row["sample_id"] for row in self.tasks}) != 500 or len({row["group_id"] for row in self.tasks}) != 500 or any(row["group_id"] in forbidden for row in self.tasks):
            raise ValueError("training task duplication or validation/test overlap")
        previous = Path(config["previous_stage_run"])
        old = {row["sample_id"] for row in read_json(previous / "selected_tasks.json")["tasks"]}
        if len(old) != 100 or not old.issubset({row["sample_id"] for row in self.tasks}):
            raise ValueError("previous stage selection is not the same training pool")
        self.order = self.interleave([row for row in self.tasks if row["sample_id"] not in old]) + self.interleave([row for row in self.tasks if row["sample_id"] in old])
        self.cursor = 0
        self.category_cursor = 0
        self.covered = set()
        self.candidates = 0
        self.informative_candidates = 0
        self.structural_candidates = 0
        self.meta = {row["sample_id"]: {"bucket": "unknown", "structural_variation": False, "draws": 0, "current_reviews": 0, "last_policy_version": None} for row in self.tasks}
        for directory in sorted((previous / "updates").glob("update-*")):
            rows, scores = read_jsonl(directory / "rollouts.jsonl"), read_jsonl(directory / "rewards.jsonl")
            for start in range(0, len(rows), config["num_generations"]):
                self.meta[rows[start]["sample_id"]].update(classify(scores[start:start + config["num_generations"]]), historical_only=True)
        if config.get("resume_run"):
            resume = Path(config["resume_run"])
            saved = read_json(resume / "sampler_state.json")
            if saved["task_pool_sha256"] != digest(self.tasks):
                raise ValueError("resume sampler task pool changed")
            self.order = read_jsonl(resume / "selected_tasks.jsonl")
            if {row["sample_id"] for row in self.order} != set(self.meta) or len(self.order) != 500:
                raise ValueError("resume coverage order is not the same full pool")
            self.meta = saved["feedback"]
            self.cursor = saved["cursor"]
            self.category_cursor = saved["category_cursor"]
            self.candidates = saved["candidate_groups"]
            self.informative_candidates = saved["informative_candidates"]
            self.structural_candidates = saved["structural_candidates"]
            self.covered = {key for key, row in self.meta.items() if row["current_reviews"] > 0}
            self.rng.setstate(restore_tuple(saved["random_state"]))

    def interleave(self, rows):
        """分类内打乱后五类交织，避免顺序训练完T1才轮到其他类。"""
        buckets = {name: [row for row in rows if row["category"] == name] for name in CATEGORIES}
        for values in buckets.values():
            self.rng.shuffle(values)
        return [buckets[name][index] for index in range(max(map(len, buckets.values()))) for name in CATEGORIES if index < len(buckets[name])]

    def draw(self, excluded):
        """首遍优先唯一覆盖；其后五类轮转并降低同分易题复访概率。"""
        if self.cursor < len(self.order):
            task = self.order[self.cursor]
            self.cursor += 1
        else:
            category = CATEGORIES[self.category_cursor % len(CATEGORIES)]
            self.category_cursor += 1
            pool = [row for row in self.tasks if row["category"] == category and row["sample_id"] not in excluded]
            weights = []
            for row in pool:
                state = self.meta[row["sample_id"]]
                weight = {"informative": 6, "hard": 3, "easy": 1, "unknown": 3}[state["bucket"]]
                weights.append(weight / (1 + state["draws"] / 3))
            task = self.rng.choices(pool, weights=weights, k=1)[0]
        self.meta[task["sample_id"]]["draws"] += 1
        return task

    def record(self, task, scores, policy_version):
        """仅在完整奖励有效后推进覆盖和候选计数，旧优先级可被新反馈覆盖。"""
        feedback = classify(scores)
        state = self.meta[task["sample_id"]]
        state.update(feedback, current_reviews=state["current_reviews"] + 1, last_policy_version=policy_version, historical_only=False)
        self.covered.add(task["sample_id"])
        self.candidates += 1
        self.informative_candidates += int(feedback["bucket"] == "informative")
        self.structural_candidates += int(feedback["bucket"] == "informative" and feedback["structural_variation"])
        return feedback

    def snapshot(self):
        """统计覆盖、类别、候选预算和反馈桶，供日志与页面同源读取。"""
        return {"tasks_completed": len(self.covered), "candidate_groups": self.candidates, "trajectories_completed": self.candidates * self.config["num_generations"], "groups_scored": self.candidates, "informative_candidates": self.informative_candidates, "structural_candidates": self.structural_candidates, "informative_candidate_rate": self.informative_candidates / self.candidates if self.candidates else 0, "coverage_by_category": dict(Counter(row["category"] for row in self.tasks if row["sample_id"] in self.covered)), "sampling_buckets": dict(Counter(row["bucket"] for row in self.meta.values()))}

    def save(self, run_dir):
        """落盘完整反馈状态与随机数，自动生成同名中文说明。"""
        write_json(Path(run_dir) / "sampler_state.json", {**self.snapshot(), "cursor": self.cursor, "category_cursor": self.category_cursor, "task_pool_sha256": digest(self.tasks), "feedback": self.meta, "random_state": self.rng.getstate(), "cross_policy_rollout_reuse": False})


def select_groups(candidates, count, target):
    """整体选G4，先可靠差异再软差异，并保留可用易题和困难锚点。"""
    informative = sorted((row for row in candidates if row["bucket"] == "informative"), key=lambda row: not row["structural_variation"])
    selected = informative[:target]
    for bucket in ("easy", "hard"):
        anchor = next((row for row in candidates if row["bucket"] == bucket), None)
        if anchor is not None:
            selected.append(anchor)
    used = {row["candidate_id"] for row in selected}
    for row in informative + candidates:
        if len(selected) == count:
            break
        if row["candidate_id"] not in used:
            selected.append(row)
            used.add(row["candidate_id"])
    return selected


def restore_tuple(value):
    """将JSON里的随机数状态列表递归恢复成random.setstate要求的元组。"""
    return tuple(restore_tuple(item) for item in value) if isinstance(value, list) else value
