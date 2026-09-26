# `homeflow_demo/env/__init__.py` 说明

## 功能

集中导出 V1.2 的 B 环境模块和统一数据契约。

```text
HomeEnv
Scenario / Home / Room / Device
ActionSchema / ParameterSchema
ToolCall / ToolEvent / EnvStepResult
AssistantTurn
SchemaValidationError / ensure_valid_scenario
```

V1.2 不再导出旧 `HomeEpisodeEnv` 名称。环境只接受规范化 `ToolCall`，不处理 AssistantTurn、reward 或 episode 终止。
