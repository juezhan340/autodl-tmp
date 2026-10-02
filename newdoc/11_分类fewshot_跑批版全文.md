# 分类 few-shot：100 条跑批所用版本（逐条全文）

> 来源：`new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/`
> 这是 `runs/qwen15b_eval_100_fs_by_task/` 那次评测（100 条、46 条全过）实际注入的示例。
> 每类的示例数不强行统一：T1 两个示例，T2/T3/T4/T5 各一个示例；消息条数随工具步数变化。
> 本文件只做展示，不改文件、不跑评测。

## 0 组装方式

```text
A 侧 messages = [system（A_policy.md 渲染后）]
             + [该类的 few-shot 消息（见下）]
             + [包装过的真实任务 user]

真实任务包装：
以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
[TASK] <user_request>
按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；一次只调一个工具；最多 12 步，尽快交 finish。
```

## 消息条数一览

```text
T1: 20 条消息
T2: 16 条消息
T3: 10 条消息
T4: 8 条消息
T5: 6 条消息
```

## T1（20 条消息）

```text
[ 1] user      示例一（精确控制）：把卧室台灯关掉。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_lamp", "display_name": "卧室台灯"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_lamp"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_lamp", "state": {"on": true, "level": 80}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_lamp", "action": "turn_off", "params": {}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_lamp", "action": "turn_off", "state_after": {"on": false, "level": 80}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"卧室台灯已关闭。","outcome":"completed"}}
[11] user      示例二（方向控制）：卧室有点热，空调调低一点。
[12] assistant {"name": "observe_home", "arguments": {}}
[13] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[14] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[15] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[16] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[17] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}, {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}}}, {"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[18] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[19] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[20] assistant {"name":"finish","arguments":{"summary":"卧室空调调低了一档。","outcome":"completed"}}
```

## T2（16 条消息）

```text
[ 1] user      示例（多设备控制）：睡前把客厅电视关掉，卧室空调调低一点，卧室加湿器别动。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_tv", "display_name": "客厅电视"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_living_tv"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_tv", "state": {"on": true, "mode": "tv", "level": 40}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}, {"action": "set_percentage", "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_living_tv", "action": "turn_off", "params": {}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_living_tv", "action": "turn_off", "state_after": {"on": false, "mode": "tv", "level": 40}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[11] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}, {"device_id": "device_bedroom_humidifier", "display_name": "卧室加湿器"}]}}, "error": null}
[12] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[13] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[14] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[15] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[16] assistant {"name":"finish","arguments":{"summary":"客厅电视已关闭，卧室空调调低了一档；卧室加湿器没有动。","outcome":"completed"}}
```

## T3（10 条消息）

```text
[ 1] user      示例（模糊意图）：屋里像蒸笼，睡不着。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"屋里闷，卧室空调已调低一档。","outcome":"completed"}}
```

## T4（8 条消息）

```text
[ 1] user      示例（做不到的目标）：把卧室空调调到三度。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"三度低于可调下限七度，没有改温度。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
```

## T5（6 条消息）

```text
[ 1] user      示例（查询）：卧室现在多少度？
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "environment": {"temperature": 24.5}, "devices": [{"device_id": "sensor_bedroom_env", "display_name": "卧室温湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

## 文件

```text
示例目录   new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/（T1–T5.json + .md + README）
跑批结果   new_demo/runs/qwen15b_eval_100_fs_by_task/（100 条，46 条 C 四项全过）
对比报告   newdoc/09_分类fewshot_100条.md
```
