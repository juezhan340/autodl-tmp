# `homeflow_demo/eval/episode_evaluator.py` 说明

## 职责

这是 C 模块的隐藏 verifier 和结果汇总层。它读取 Scenario 中模型不可见的 `conditions`、`keep`，但不生成模型响应，也不修改 B 的状态。

```text
输入：Scenario、B runtime_state、ToolEvent、终止状态、finish_payload、逐 turn reward
输出：EpisodeEvaluation
```

## 成功条件

```text
传统控制任务：Scenario 可行、finish 已请求、没有截断、conditions 和 keep 全部满足
V2 answered：finish outcome/facts 合法、required_observations 满足、家庭状态未变化
V2 refused：finish outcome/reason_code 合法、required_observations 满足、家庭状态未变化
```

`deterministic_passed` 只表示代码能确认的结果。T3/T4/T5 还要由 `DeepSeekTrajectoryJudge` 检查自然语言语义；语义裁判不能覆盖确定性失败。策略错误、环境故障和未决错误另行计数。

## 质量门禁

`accepted_for_sft` 只有在 episode 成功、轨迹没有策略错误或环境故障、工具结果完整且没有终止后多余动作时才为真。所有拒绝原因写入 `rejection_reasons`。

无法归因的错误单独计入 `unresolved_error_count`，不混入策略负奖励；存在未决错误的轨迹不通过 SFT 质量门禁。
