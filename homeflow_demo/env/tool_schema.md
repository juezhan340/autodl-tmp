# `homeflow_demo/env/tool_schema.py` 说明

## 职责

定义模型可见的工具集合，并在动作进入状态机之前完成工具名、设备 ID、命令和参数值校验。

## 工具

```text
query_device：    查询设备字段
control_device：  修改设备字段
finish：           声明 episode 结束
```

## 输入

```text
Action 对象
AssistantTurn 中的 Action 列表
设备状态字典
JSON 字符串或动作字典
```

## 输出

```text
available_tools() -> 工具 schema 列表
normalize_action() -> Action
normalize_assistant_turn() -> AssistantTurn
validate_action() -> ValidationResult
```

## 失败行为

```text
未知工具：      UNKNOWN_TOOL
未知设备：      UNKNOWN_DEVICE
未知查询字段：  UNKNOWN_FIELD
命令不匹配：    INVALID_COMMAND
参数越界：      VALUE_OUT_OF_RANGE
格式错误：      INVALID_ARGUMENTS
```

校验失败时，状态引擎不能被调用，设备状态不能发生变化。
