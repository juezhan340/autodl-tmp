# `homeflow_demo/agents/oracle_policy.py` 说明

## 职责

提供不调用外部模型的 A 模块，用于 V1.2 回合链路 smoke test、可重放验收和之后的数据核验。

```text
observe_home
  -> inspect_room
  -> inspect_device
  -> execute_action（目标状态不同且设备公开支持时）
  -> finish
```

Oracle 使用 Scenario 的隐藏任务构造参考计划，这是教师/上界角色的权限；被测模型只收到 C 组装的 observation 与工具 schema。

阈值任务可在 `metadata.context_device_ids` 声明决策所需的传感器。Oracle 会像普通设备一样先通过房间发现并读取它，再决定是否操作目标执行器。

## 输入输出

```text
输入：Scenario
respond(context) -> OpenAI function-call 兼容 assistant message
```

每次响应只发一个工具调用，避免同一回合内工具调用之间存在依赖。

`planned_calls` 只读暴露规范调用序列，供数据构建和审计读取；实际 episode 仍由 `EpisodeRunner` 通过 `respond()` 驱动。
