# `homeflow_demo/eval/deepseek_trajectory_judge.py` 说明

## 职责

对 C 已完成确定性执行的候选轨迹做语义审查。T4 危险拒绝和 T5 环境查询默认必须调用；T3 模糊意图也调用；T1/T2 若只评价物理状态可以跳过。

```text
Scenario + 公开 turns + finish + deterministic_result
  -> DeepSeekTrajectoryJudge × 3
  -> 多数投票
  -> pass / rejected / system_failure
```

## 输入输出

裁判不会收到 `final_state`、hidden conditions 或完整内部验证实现，只读取工具 observation 和 C 的确定性摘要。输出 `SemanticJudgeResult`，其中：

```text
pass             语义票多数通过
rejected         有足够有效票但多数否定
system_failure   没有足够有效票，等待重跑
```

`system_failure` 不等于模型策略失败；`rejected` 才是候选语义质量失败。
