# `homeflow_demo/eval/trajectory_quality.py` 说明

## 职责

把 `EpisodeEvaluation` 和完整轨迹转成 `accepted_for_sft` 门禁。成功和失败轨迹都会执行确定性重放；只有任务成功、没有错误污染、事件完整且 B 可重放的轨迹才会被接收。V2 的最终 route 还会在此基础上区分 `semantic_rejected` 和 `system_failure`。

```text
apply_trajectory_quality(evaluation, trajectory, scenario)
  -> 检查 success / 错误 / 截断
  -> 检查每个 turn 和 result envelope
  -> 从初始 Scenario 重放所有规范 ToolCall
  -> 比对 tool result、state_diff、final_state
  -> 写 accepted_for_sft / rejection_reasons / trajectory_replayable
```

重放比较忽略 `elapsed_ms`，因为它是机器诊断数据，不是环境状态。

无法归因的 `SERVICE_ERROR` 等错误会记为 `unresolved_error`，不计入策略惩罚，也会阻止轨迹进入 SFT。

环境故障导致的 truncated 轨迹可以在没有 `finish` 的情况下判定为可重放；可重放只证明执行确定性，不会覆盖环境故障的 rejected 结论。

重放器按轨迹里的规范 ToolCall 依次调用 B，不复现已经删除的发现链闸门。
