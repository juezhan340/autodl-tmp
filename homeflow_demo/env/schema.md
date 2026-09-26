# `homeflow_demo/env/schema.py` 说明

## 职责

在 Scenario 进入 HomeEnv 前一次性检查结构和引用，防止错误场景在运行中才暴露。

```text
校验对象
  房间：room_id、display_name、device_ids
  设备：device_id、room_id、kind、device_type、state、actions
  关系：Room.device_ids 与 Device.room_id 双向一致
  传感器：actions 必须为空；每个房间最多一个温度源和一个湿度源
  动作：参数类型、范围、步长、枚举
  动作签名：开关动作无参数；mode/value 参数名固定；温度和百分比必须公开范围与步长
  运行值域：set_temperature 保持在 7～32；set_percentage 保持在 0～100
  模式值域：set_mode 只能公开 off / cool / heat / auto
  隐藏任务：conditions/keep、required_observations、expected_finish 引用存在的实体字段
  V2 类别：single_control / multi_control / vague_intent / dangerous_refusal / environment_query
  回合：max_turns、max_tool_calls_per_turn
  元数据：feasible 必须是布尔值，数值字段拒绝 NaN/Infinity
```

## 输入输出

```text
validate_scenario_dict(dict) -> 全部错误字符串
ensure_valid_scenario(dict)  -> Scenario
```

校验失败抛出 `SchemaValidationError`。`answered` 和 `refused` 任务允许没有 conditions，但必须由 C 检查 required observations 和 expected finish。模块不执行工具、不修改状态，也不判断一次模型轨迹是否成功。
