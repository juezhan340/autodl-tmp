# `homeflow_demo/data/build_v2_dataset.py` 说明

## 职责

这是第一步代码的总编排入口，按以下顺序执行：

```text
TaskBlueprint
  -> DeepSeekTaskWriter
  -> StaticTaskValidator
  -> DeepSeekTaskReviewer
  -> ScenarioCompiler
  -> C EpisodeRunner + A DeepSeekPolicy + B HomeEnv
  -> DeterministicAudit
  -> DeepSeekTrajectoryJudge
  -> ResultMerger / DatasetRouter
```

## 输入输出

```text
build_v2_smoke(output_dir, seed, count_per_category, concurrency, judge_votes)
  输入：输出目录、随机种子、每类尝试次数、并发数、语义裁判票数
  输出：summary 字典和 output_dir 下的 raw/processed JSONL
```

默认每类生成 1 条 Blueprint，共 5 条；通过 `--count-per-category 4` 可生成五类各 4 条、总计 20 条。策略 rollout 使用 `--concurrency` 个并发 worker，任务改写、任务审查和轨迹回合会写入 `data_raw/v2/`；最终轨迹写入：

```text
data_processed/v2/
  scenarios_smoke.jsonl
  trajectories_clean_success.jsonl
  trajectories_recovered_success.jsonl
  trajectories_semantic_rejected.jsonl
  trajectories_failed.jsonl
  trajectories_system_failure.jsonl
```

脚本还会运行一个本地格式错误探针，确认非法 JSON 消耗一个 turn，下一轮 context 收到 `INVALID_ASSISTANT_RESPONSE`。
