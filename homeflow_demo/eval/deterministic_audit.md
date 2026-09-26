# `homeflow_demo/eval/deterministic_audit.py` 说明

## 职责

把 C 的 `EpisodeEvaluation` 和完整轨迹整理为 `deterministic_result`。该模块不调用 DeepSeek，不评价自然语言修辞，只汇总代码已经确认的事实：

```text
目标状态是否满足
required_observations 是否满足
查询/拒绝任务是否保持状态不变
finish 契约是否合法
是否发生协议或环境错误
轨迹是否可重放
```

## 输入输出

```text
audit_episode(scenario, episode_run)
  输入：Scenario、EpisodeRun
  输出：deterministic_result 字典
```

语义裁判只读取这个摘要和公开轨迹事实，不能用它重新执行 HomeEnv，也不能覆盖确定性失败。
