# `homeflow_demo/env/models.py` 说明

## 职责

集中定义 V1.2 的唯一数据契约。A、B、C、数据生成器和测试都复用这些类型，不再各自拼装旧版扁平字典。

```text
Scenario
├── Home
│   ├── Room：房间一级实体和 device_ids 索引
│   └── Device：sensor 或 actuator
│       ├── state
│       └── actions[ActionSchema]
├── TaskSpec
│   ├── user_request：模型可见
│   ├── conditions：C 可见的隐藏目标
│   ├── keep：C 可见的状态保持条件
│   ├── category：V2 五类任务类别
│   ├── required_observations：查询/拒绝所需观察
│   └── expected_finish：结构化 finish 隐藏契约
└── EpisodeConfig
```

## 关键输入输出

```text
Scenario.from_dict(dict) -> Scenario
Scenario.to_dict()        -> 可重放 JSON
ToolCall                  -> C 交给 B 的统一调用：name / arguments / call_id
AssistantTurn             -> C 解析后的一次模型决策
ToolEvent                 -> B 的调用结果与 state_diff
EnvStepResult             -> B 的 observation + ToolEvent
```

`ToolCall.from_dict()` 保留输入字段的原始类型，由 `tool_schema.py` 统一转成 `BAD_REQUEST`；不会用 `str()` 把错误类型伪装成合法工具名或 ID。

V2 的 `TaskSpec.expected_finish` 保存 `completed / answered / refused`、事实和允许的拒绝理由；它只供 C 确定性审查使用。模型通过公开 `finish` 工具提交对应字段。

## 边界

```text
本文件只定义结构和序列化
不解析模型厂商消息
不校验设备动作
不修改设备状态
不读取隐藏目标做评测
```
