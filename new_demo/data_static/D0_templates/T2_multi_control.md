你要干什么：
你是数据辅助生成器。根据本轮 s0 写一份 T2 多设备控制的 task JSON。画像只借口吻，不决定动哪几台。没有的房间和设备不要写。required_observations 必须是空数组。outcome 必须是 completed。只输出一个 JSON 对象。

每条 condition 的 operator 只有三种：eq、ge、le。一条只选一种；同一份 task 里可以几种混用。

eq
  用在开关、模式、写死的数字上。
  value 就是目标。intent 里对应那一截把目标说死：关掉、调到暗档、开快洗。

ge
  用在连续量上，表示比现在高。
  连续量：空调、热水器、冰箱、烤箱的 target，台灯、电视、风扇的 level。
  value 填 s0 里该字段的当前值，不要另编二十六、八十。
  intent 里对应那一截只写方向：调高一点、声音大一点。

le
  用在同一批连续量上，表示比现在低。
  value 填当前值。
  intent 里对应那一截只写方向：调低一点、声音小一点。

对齐
  conditions 两条或三条。keep 恰好一台，operator 只能 eq，value 取 s0 当前值，且这台不在 conditions 里。
  intent 里出现的设备 = conditions 的设备 + keep 那一台，不多不少。口吻可以放句首，不占设备。
  每一截说法还要和那条的 operator 同型：eq 不说调低一点，ge / le 不说调到二十六度。
  主灯用 on 或 mode，台灯用 level，加湿器只有 on。

小例子（客厅电视、卧室空调当前 27、厨房冰箱）

对
  conditions  电视 eq 关掉，空调 le 调低一点（value=27.0）
  keep        冰箱 eq 别动
  intent      睡觉前想凉一点，客厅电视关掉，卧室空调调低一点，厨房冰箱别动

错
  intent 里多了客厅主灯，conditions 没有它
  keep 是冰箱，intent 却写厨房灯别动
  本轮没有书房，intent 写了书房台灯
  空调 le 的 value 写成 26
  电视 eq 的那一截写成声音小一点

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p16","name":"唐宁","age":24,"occupation":"实习生","habits":"合租，只动自己卧室的灯、空调和加湿器，客厅电视和厨房设备不要动；睡觉前想凉一点"}

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
{"intent":"睡觉前想凉一点，客厅电视关掉，卧室空调调低一点，厨房冰箱别动","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[{"device_id":"device_kitchen_fridge","field":"target","operator":"eq","value":4.0}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。必须根据下面这份新的 s0 另写，不要照抄电视和二十七度。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
