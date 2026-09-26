# `homeflow_demo/eval/metrics.py` 说明

## 职责

把一批完整轨迹或 `EpisodeEvaluation` 汇总成 V1.2 的稳定基础指标，供数据 manifest、smoke eval 和后续 V4 比较复用。

```text
输入：trajectory[] 或 EpisodeEvaluation[]
输出：episode_count / success_rate / accepted_for_sft_rate
      三类错误总数 / mean_reward / failure_class_counts
```

本模块只聚合 C 已经给出的统一结果，不重新解释状态或工具事件。
