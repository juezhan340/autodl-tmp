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

`observe_home` 不返回 `device_id`。外部模型要拿到 id，只能自己去 `inspect_room`。这是观察内容，不是执行器闸门。`elapsed_ms` 保留在 ToolEvent 审计中，从下一轮模型 observation 删除。

`inspect_room` / `inspect_device` / `execute_action` 不检查有没有先观察。真实 id 可以直接执行；房间或设备不存在才返回 `UNKNOWN_*`。参数越界返回 `BAD_REQUEST`，动作不支持返回 `UNSUPPORTED_ACTION`。`snapshot/restore/fork` 只复制家庭状态和事件，不保存发现权限。

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
