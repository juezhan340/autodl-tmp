# `homeflow_demo/env/home_env.py` 说明

## 职责

`HomeEpisodeEnv` 是 Demo 的环境真值层。V1.1 起，公开 `step()` 的一个 step 对应一次 assistant turn；turn 内的多个工具调用由环境逐个执行并记录为 `tool_events`，最后只聚合出一条策略 transition。

## 输入

```text
reset：Scenario 对象或场景字典
step：AssistantTurn、Action、动作字典或 JSON 字符串
restore：同一场景生成的 snapshot
```

## 输出

```text
reset -> observation, info
step  -> StepResult(observation, reward, terminated, truncated, info)
snapshot -> 可 JSON 序列化的环境状态
trajectory -> 一条 turn 对应一条 transition，内部包含多个 tool_events
final_result -> FinalResult，包含 turns 和兼容字段 steps
```

## 状态流转

```text
reset
  -> StateEngine 加载设备
  -> completion 初始值
  -> 返回用户请求、设备状态和工具 schema

AssistantTurn_t
  -> normalize_assistant_turn
  -> 检查 max_tool_calls_per_turn
  -> _apply_action(Action_0), _apply_action(Action_1), ...
  -> 记录 ToolEvent_0, ToolEvent_1, ...
  -> 汇总 completion、reward、terminated/truncated
  -> 写入一条 turn-level trajectory
```

双设备例子：一次模型输出同时关闭灯和调空调。

```text
turn_1
  tool_event_0: bedroom.light -> off
  tool_event_1: bedroom.air_conditioner -> 26
  trajectory 条数 = 1
```

一个模型 completion 只对应一条 RL transition，不把后续工具调用虚构成新的策略步。

## reward 规则

```text
完成度提升：2.0 * 本 turn 完成度增量
有效状态变化：+0.02 / 个发生变化的控制调用
无效重复：-0.10 / 个重复控制调用
非法工具调用：-0.30 / 个
finish 成功：+1.00
finish 失败：-0.50
turn 成本：-0.01
```

## 重要边界

```text
目标条件只由环境内部持有，不放进 observation
DeepSeek、训练器和评测器不能直接修改设备状态
非法工具调用写入 tool_event，但不会修改设备状态
超过单 turn 工具上限时，整个 turn 不执行
max_turns 统计 assistant 输出次数，不统计工具调用数
同一场景必须通过 reset/fork 生成独立 rollout
```
