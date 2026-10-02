你要干什么：
你是数据辅助生成器。根据本轮 s0 写一份 T5 环境查询的 task JSON。画像仅供参考，口吻可以沾一点。
conditions、keep、required_observations 必须是空数组。不要改任何设备。
outcome 必须是 completed。不要写 facts。
intent 只问本轮能读到的量：传感器 state，或执行器已经公开的 on/mode/level/target。
目录没有光照传感器、噪声传感器，不要问光线够不够、吵不吵。
没有的房间不要写进 intent。不要写成控制。
不要写用户那句口语。只输出一个 JSON 对象。

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p03","name":"王芳","age":28,"occupation":"护士","habits":"夜班回来先开热水器和卫生间排气扇洗澡；睡觉前看湿度，太干就开卧室加湿器"}

例子里的 s0：
{
  "rooms": [
    {"room_id": "room_bedroom", "display_name": "卧室", "device_ids": ["device_bedroom_light", "device_bedroom_lamp", "device_bedroom_climate", "device_bedroom_humidifier", "sensor_bedroom_env"]},
    {"room_id": "room_living", "display_name": "客厅", "device_ids": ["device_living_tv"]},
    {"room_id": "room_kitchen", "display_name": "厨房", "device_ids": ["device_kitchen_fridge", "device_kitchen_oven"]}
  ],
  "devices": [
    {
      "device_id": "device_bedroom_light",
      "room_id": "room_bedroom",
      "display_name": "卧室主灯",
      "kind": "actuator",
      "device_type": "light",
      "state": {"on": true, "mode": "bright"},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["dim", "bright"]}}}
      ],
      "available": true
    },
    {
      "device_id": "device_bedroom_lamp",
      "room_id": "room_bedroom",
      "display_name": "卧室台灯",
      "kind": "actuator",
      "device_type": "light",
      "state": {"on": true, "level": 80},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_percentage", "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}}}
      ],
      "available": true
    },
    {
      "device_id": "device_bedroom_climate",
      "room_id": "room_bedroom",
      "display_name": "卧室空调",
      "kind": "actuator",
      "device_type": "climate",
      "state": {"on": true, "mode": "cool", "target": 27.0},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}}},
        {"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}
      ],
      "available": true
    },
    {
      "device_id": "device_bedroom_humidifier",
      "room_id": "room_bedroom",
      "display_name": "卧室加湿器",
      "kind": "actuator",
      "device_type": "humidifier",
      "state": {"on": false},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}}
      ],
      "available": true
    },
    {
      "device_id": "sensor_bedroom_env",
      "room_id": "room_bedroom",
      "display_name": "卧室温湿度传感器",
      "kind": "sensor",
      "device_type": "environment_sensor",
      "state": {"temperature": 30.0, "humidity": 35.0},
      "actions": [],
      "available": true
    },
    {
      "device_id": "device_living_tv",
      "room_id": "room_living",
      "display_name": "客厅电视",
      "kind": "actuator",
      "device_type": "tv",
      "state": {"on": true, "mode": "tv", "level": 40},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["tv", "hdmi", "av"]}}},
        {"action": "set_percentage", "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}}}
      ],
      "available": true
    },
    {
      "device_id": "device_kitchen_fridge",
      "room_id": "room_kitchen",
      "display_name": "厨房冰箱",
      "kind": "actuator",
      "device_type": "refrigerator",
      "state": {"on": true, "target": 4.0},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 2.0, "maximum": 8.0, "step": 0.5}}}
      ],
      "available": true
    },
    {
      "device_id": "device_kitchen_oven",
      "room_id": "room_kitchen",
      "display_name": "厨房烤箱",
      "kind": "actuator",
      "device_type": "oven",
      "state": {"on": false, "mode": "bake", "target": 180.0},
      "actions": [
        {"action": "turn_on", "params": {}},
        {"action": "turn_off", "params": {}},
        {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["bake", "broil", "keep_warm"]}}},
        {"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 50.0, "maximum": 250.0, "step": 5.0}}}
      ],
      "available": true
    }
  ]
}

这个例子的正确输出：
{"intent":"晚上鼻子容易干，想知道卧室现在湿不湿、热不热","conditions":[],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。不要照抄例子，必须根据本轮 s0 另写一份 T5。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
