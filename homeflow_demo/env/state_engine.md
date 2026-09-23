# `homeflow_demo/env/state_engine.py` 说明

## 职责

`StateEngine` 是 HomeEnv 的确定性状态转移层。它只负责读取设备状态、执行已通过参数校验的控制动作、生成状态差异和保存恢复快照。

## 输入

```text
设备列表：id、type、room、state
query：device_id、fields
control：已由 tool_schema 校验的 Action
snapshot：同一场景的设备状态快照
```

## 输出

```text
devices：当前设备状态深拷贝
query：设备状态摘要
control：changed、state_diff、current_state
snapshot：可恢复的设备状态
```

## 状态流转

```text
Action
  -> tool_schema.validate_action
  -> StateEngine.control
  -> 更新一个设备字段
  -> 返回 before/after 差异
```

## 不负责

```text
不负责决定动作是否合法
不负责判断目标是否完成
不负责计算 episode reward
不负责调用语言模型
```

