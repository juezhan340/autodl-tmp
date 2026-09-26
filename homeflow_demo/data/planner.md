# `homeflow_demo/data/planner.py` 说明

## 职责

把 `OraclePolicy` 接入 `EpisodeRunner`，统一生成参考计划和 C 模块评测后的 V1.2 轨迹。规划器不再直接调用环境，也不维护另一套成功判定。

```text
Scenario
  -> OraclePolicy：产生发现式 ToolCall
  -> EpisodeRunner：管理 A/B 回合
  -> EpisodeEvaluation：成功、错误、reward、SFT 门禁
```

## 输入输出

```text
plan_scenario(Scenario) -> PlanResult
  feasible：场景定义的可行性标签
  calls：规范 ToolCall 序列
  reason：不可行任务的预期失败原因

run_oracle_episode(Scenario) -> 完整 V1.2 轨迹字典
```

`sensor_readonly` 和 `missing_device` 会保留为经过环境验证的失败轨迹，不伪造成 Oracle 成功样本。
