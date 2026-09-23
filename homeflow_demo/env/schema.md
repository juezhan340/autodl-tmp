# `homeflow_demo/env/schema.py` 说明

## 职责

在场景进入 `HomeEpisodeEnv` 之前，检查设备、设备状态字段、目标谓词、最大步数、动作名和参数容器的结构，避免错误数据进入状态机。

## 输入

```text
场景字典
动作字典
```

## 输出

```text
validate_scenario_dict -> 错误字符串列表
ensure_valid_scenario -> Scenario
validate_action_dict -> 错误字符串列表
ensure_valid_action -> Action
```

## 失败行为

```text
校验失败：抛出 SchemaValidationError
校验成功：返回类型明确的 dataclass
```

## 校验范围

```text
场景必需字段：scenario_id、user_request、devices、goal
设备类型：light、thermostat、switch、lock
设备字段：每类设备只能使用 V1 工具支持的状态字段
初始值域：power、brightness、color_temp、temperature、mode、locked 必须满足工具值域
目标谓词：引用已存在设备和字段
max_turns：1～64；旧字段 max_steps 仍可读取
max_tool_calls_per_turn：1～64
动作名：query_device、control_device、finish
```

这个模块只做场景和动作对象的结构校验；设备命令和值域、查询字段存在性仍由 `tool_schema.py` 做运行时校验。
