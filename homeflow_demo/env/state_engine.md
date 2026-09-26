# `homeflow_demo/env/state_engine.py` 说明

## 职责

`StateEngine` 是 B 模块的确定性状态层。它读取房间和设备，执行已通过工具形状检查的调用，并保证失败时无部分写入。

```text
observe_home
  -> 房间目录 + 传感器派生环境摘要
  -> 不返回 device_id

inspect_room(room_id)
  -> 房间内全部设备轻量摘要

inspect_device(device_id)
  -> 完整 state + actions

execute_action(device_id, action, params)
  -> 根据该设备 actions 重复校验
  -> 在候选副本修改
  -> 成功后一次性提交
  -> 返回 state_after / state_diff / verified
```

## 规范动作到状态字段

```text
turn_on / turn_off / toggle -> on
set_mode                    -> mode
set_temperature             -> target
set_percentage              -> level
```

传感器 `actions=[]`，因此任何写入都会在状态修改前返回 `UNSUPPORTED_ACTION`。
