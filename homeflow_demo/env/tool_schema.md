# `homeflow_demo/env/tool_schema.py` 说明

## 职责

统一定义模型能看到的工具、参数形状、设备 action 参数校验、返回外壳和错误归因。

```text
家庭语义工具
  observe_home()
  inspect_room(room_id)
  inspect_device(device_id)
  execute_action(device_id, action, params)

 runner 工具
  finish(summary, outcome?, facts?, reason_code?)
```

## 返回外壳

```text
成功：{ok:true, data:{...}, error:null, meta:{elapsed_ms, clock:"none"}}
失败：{ok:false, data:null, error:{code,message,hint?}, meta:{elapsed_ms, clock:"none"}}
```

`policy_result_view()` 在下一轮 observation 中删除 `elapsed_ms`，但完整值仍保留在 ToolEvent 审计记录里。

## 错误归因

```text
策略/协议错误：UNKNOWN_ROOM、UNKNOWN_DEVICE、UNSUPPORTED_ACTION、BAD_REQUEST
环境错误：      DEVICE_UNAVAILABLE、BACKEND_UNREACHABLE
未决错误：      SERVICE_ERROR，交给 C 结合上下文处理
```

本模块不解析模型厂商消息，也不执行状态修改。

动作参数会重复校验缺失、多余、类型、枚举、范围和步长；`NaN`、`Infinity` 等非有限数统一返回 `BAD_REQUEST`。

每个规范 `ToolCall` 必须带非空 `call_id`，便于 C、B 和轨迹重放稳定对齐事件。

V2 的 `finish` 可提交：

```json
{
  "summary": "简短说明",
  "outcome": "completed | answered | refused",
  "facts": [],
  "reason_code": "OUT_OF_SAFE_RANGE"
}
```

`summary` 仍是唯一必填字段；隐藏任务契约由 C 检查，HomeEnv 不解释这些字段。

工具名、`call_id` 和参数名都必须是字符串；异常 Python 对象不会绕过校验或让环境崩溃。
