你要干什么：
你是数据辅助生成器。根据本轮 s0 写一份 T3 模糊意图的 task JSON。画像仅供参考。
唯一一条 condition。keep 和 required_observations 必须是空数组。outcome 必须是 completed。
intent 只写当下感受，不要出现调、关、开、打开、关掉、调低、调到、把某设备。感受必须能落到本轮一台真实设备。不要编造设备。只输出一个 JSON 对象。

operator 只有三种：eq、ge、le。本轮只有一条 condition，从三种里选一种。

eq
  用在开关和模式上。
  潮：加湿器 on eq false。干：加湿器 on eq true。刺眼：主灯 mode eq dim。
  value 就是那个开关或档位。intent 只写感受：身上发潮、嗓子干、灯刺得睁不开。

ge
  用在连续量上，表示比现在高。
  连续量：空调、热水器、冰箱、烤箱的 target，台灯、电视、风扇的 level。
  人说冷，空调 target 用 ge。value 填 s0 当前值，不要另编二十六。当前已经是上限就换感受。
  intent 只写感受：屋里有点冷。

le
  用在同一批连续量上，表示比现在低。
  人说热、蒸、闷，空调 target 用 le。人说吵，电视或风扇 level 用 le。value 填当前值。已经是下限就换感受。
  intent 只写感受：屋里像蒸笼、太吵。

对齐
  感受方向必须和 operator 一致：冷对 ge，热对 le，潮对关掉，干对打开。
  加湿器已经是那个开关，就换感受，不要把干写成关掉、把潮写成打开。
  家里没有加湿器就不要写潮或干。空调、台灯、电视、风扇有连续轴，不要用 on eq 去凑热冷吵。

小例子（卧室空调当前 27，加湿器关着，电视音量 40）

对  屋里像蒸笼     空调 target le，value=27.0
对  有点冷         空调 target ge，value=27.0
对  嗓子干         加湿器 on eq true
对  灯刺得睁不开   主灯 mode eq dim
错  热却把 value 写成 26
错  人说潮却写加湿器打开
错  intent 写成把空调调低一点
错  家里没有加湿器却写潮

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p04","name":"陈浩","age":22,"occupation":"大学生","habits":"凌晨还在书桌前，台灯调到够亮、主灯可关；熬夜怕热，睡觉要把房间弄凉快，冰箱常翻饮料"}

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
{"intent":"屋里像蒸笼，睡不着","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。按本轮 s0 的当前值填 value，不要照抄二十七。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
