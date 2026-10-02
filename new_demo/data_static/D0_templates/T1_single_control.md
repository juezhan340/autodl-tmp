你要干什么：
你是数据辅助生成器。根据本轮 s0 写一份 T1 单设备控制的 task JSON。画像只借口吻，题面跟本轮房间和设备走，没有的不要写。
只改一台可控设备的一个字段。keep 和 required_observations 必须是空数组。outcome 必须是 completed。不要 facts，不要 answered。只输出一个 JSON 对象。

operator 只有三种：eq、ge、le。本轮只选其中一种，写在那一条 condition 里。

eq
  用在开关、模式、写死的数字上。
  value 就是目标本身：false、dim、22、30。
  intent 把目标说死：关掉、调到二十二度、主灯调到暗档、台灯调到百分之三十。

ge
  用在连续量上，表示比现在高。
  连续量只有这些字段：空调、热水器、冰箱、烤箱的 target，台灯、电视、风扇的 level。
  value 填 s0 里该字段的当前值，不要另编二十六、八十。
  intent 只写方向：调高一点、再暖和一点、声音大一点，不要出现数字。

le
  用在同一批连续量上，表示比现在低。
  value 同样填当前值。
  intent 只写方向：调低一点、暗一点、声音小一点，不要出现数字。

对齐
  intent 的说法必须和选中的 operator 同型：eq 不说「调低一点」，ge / le 不说「调到二十六度」。
  主灯用 on 或 mode（dim / bright），不能写 level。台灯才能写 level。夜灯、廊灯、厨灯、浴灯、阳台灯只有 on。加湿器只有 on，只能 eq。
  没有的房间、设备不要写。

小例子（卧室空调当前 target=27，电视音量 40）

对  eq   想把客厅电视关掉
        on eq false
对  le   想把卧室空调调低一点
        target le，value=27.0
对  ge   屋里有点冷，想调高一点
        target ge，value=27.0
错  le 的 value 写成 26
错  le 的 intent 写成调到二十六度
错  eq 的 intent 写成调低一点
错  本轮没有书房却写书房台灯

先看一个完整例子。下面两份输出共用同一套家，A 是 eq，B 是 le。本轮选了哪种 operator，就按哪份的口吻写，不要照抄设备。

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

例子 A 的画像：
{"persona_id":"p02","name":"张强","age":35,"occupation":"销售","habits":"家里有幼儿，十点后客厅电视必须关、走廊灯不要亮；脏衣服隔天丢进洗衣机开快洗"}

例子 A 的正确输出：
{"intent":"十点后幼儿要休息，想把客厅电视关掉","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

例子 B 的画像：
{"persona_id":"p08","name":"周凯","age":31,"occupation":"快递员","habits":"夏天在外面暴晒，进门先要凉快、灯马上亮；脏衣服丢进洗衣机快洗，洗澡热水器要热"}

例子 B 的正确输出：
{"intent":"进门还是热，想把卧室空调调低一点","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。必须根据下面这份新的画像和 s0 另写一份 T1，不要照抄例子。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
