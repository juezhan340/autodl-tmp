# `homeflow_demo/env/home_env.py` 说明

## 职责

`HomeEnv` 是 V1.2 的 B 模块。它只维护家庭运行状态并执行 C 传入的规范化 `ToolCall`。

```text
输入：ToolCall{name, arguments, call_id}
输出：EnvStepResult
      ├── observation：下一轮模型可见上下文
      └── ToolEvent：完整 result envelope + state_diff
```

## Observation 边界

```text
可见：scenario_id、user_request、tools、last_tool_result
不可见：隐藏 conditions、keep、完整设备库存、verifier 结果
```

设备 ID 必须通过 `observe_home -> inspect_room` 发现。`elapsed_ms` 保留在 ToolEvent 审计中，但从下一轮模型 observation 删除。

环境维护“已枚举家庭、已发现设备、已检查设备”三级会话状态。`observe_home` 成功后才能用返回的 `room_id` 调用 `inspect_room`；房间检查成功后，其设备 ID 才能用于 `inspect_device`；读取完整 state/actions 后才能 `execute_action`。直接猜测 ID 或动作分别返回 `UNKNOWN_*`、`BAD_REQUEST`。这些状态会进入 `snapshot/restore/fork`。

`access_state` 只向 C 暴露发现权限，不包含隐藏目标或可写状态。C 用它禁止同一 assistant turn 消费前一个工具刚返回的新信息。

## 不负责

```text
不解析模型厂商消息
不接受 AssistantTurn
不处理 finish
不管理 turn/max_turns
不读取隐藏目标
不计算 reward
不判断 episode success
```

`snapshot/restore/fork` 用于生成相同初始状态且互相隔离的 rollout。
