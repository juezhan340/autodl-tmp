你要干什么：
你是数据辅助生成器。根据本轮画像和 s0，写一份 T1 单设备控制的 task JSON。
只改一台可控设备的一个字段。开关、模式、精确数值都用 operator=eq。
数值必须落在该设备 actions 的范围内。灯能不能调光看它有没有 set_percentage：有才能写 level，夜灯只能写 on。
keep、required_observations 为空数组。outcome 必须是 completed。不要 answered，不要 facts。
设备必须用 s0 里已有的 device_id。intent 必填，要体现画像的年龄、职业或习惯。
本轮 s0 里若有电视、冰箱、洗衣机、加湿器、烤箱，可以选它们；没有就不要编。
不要编造设备，不要写成拒绝任务，不要写用户那句口语。

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p18","name":"冯洁","age":42,"occupation":"会计","habits":"月底加班，书房台灯要亮、空调不要太冷；离开书房灯必须关，冰箱保持四五度，客厅保持原样"}

例子里的 s0：
{
  "rooms": [
    {
      "room_id": "room_bedroom",
      "display_name": "卧室",
      "device_ids": [
        "device_bedroom_light",
        "device_bedroom_climate",
        "device_bedroom_humidifier",
        "sensor_bedroom_env"
      ]
    },
    {
      "room_id": "room_living",
      "display_name": "客厅",
      "device_ids": [
        "device_living_tv"
      ]
    },
    {
      "room_id": "room_kitchen",
      "display_name": "厨房",
      "device_ids": [
        "device_kitchen_fridge",
        "device_kitchen_oven"
      ]
    }
  ],
  "devices": [
    {
      "device_id": "device_bedroom_light",
      "room_id": "room_bedroom",
      "display_name": "卧室主灯",
      "kind": "actuator",
      "device_type": "light",
      "state": {
        "on": true,
        "level": 80
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_percentage",
          "params": {
            "value": {
              "type": "integer",
              "minimum": 0,
              "maximum": 100,
              "step": 1
            }
          }
        }
      ],
      "available": true
    },
    {
      "device_id": "device_bedroom_climate",
      "room_id": "room_bedroom",
      "display_name": "卧室空调",
      "kind": "actuator",
      "device_type": "climate",
      "state": {
        "on": true,
        "mode": "cool",
        "target": 27.0
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_mode",
          "params": {
            "mode": {
              "type": "string",
              "enum": [
                "off",
                "cool",
                "heat",
                "auto"
              ]
            }
          }
        },
        {
          "action": "set_temperature",
          "params": {
            "value": {
              "type": "number",
              "minimum": 7.0,
              "maximum": 32.0,
              "step": 0.5
            }
          }
        }
      ],
      "available": true
    },
    {
      "device_id": "device_bedroom_humidifier",
      "room_id": "room_bedroom",
      "display_name": "卧室加湿器",
      "kind": "actuator",
      "device_type": "humidifier",
      "state": {
        "on": false,
        "level": 40
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_percentage",
          "params": {
            "value": {
              "type": "integer",
              "minimum": 0,
              "maximum": 100,
              "step": 1
            }
          }
        }
      ],
      "available": true
    },
    {
      "device_id": "sensor_bedroom_env",
      "room_id": "room_bedroom",
      "display_name": "卧室温湿度传感器",
      "kind": "sensor",
      "device_type": "environment_sensor",
      "state": {
        "temperature": 30.0,
        "humidity": 35.0
      },
      "actions": [],
      "available": true
    },
    {
      "device_id": "device_living_tv",
      "room_id": "room_living",
      "display_name": "客厅电视",
      "kind": "actuator",
      "device_type": "tv",
      "state": {
        "on": true,
        "mode": "tv",
        "level": 40
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_mode",
          "params": {
            "mode": {
              "type": "string",
              "enum": [
                "tv",
                "hdmi",
                "av"
              ]
            }
          }
        },
        {
          "action": "set_percentage",
          "params": {
            "value": {
              "type": "integer",
              "minimum": 0,
              "maximum": 100,
              "step": 1
            }
          }
        }
      ],
      "available": true
    },
    {
      "device_id": "device_kitchen_fridge",
      "room_id": "room_kitchen",
      "display_name": "厨房冰箱",
      "kind": "actuator",
      "device_type": "refrigerator",
      "state": {
        "on": true,
        "target": 4.0
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_temperature",
          "params": {
            "value": {
              "type": "number",
              "minimum": 2.0,
              "maximum": 8.0,
              "step": 0.5
            }
          }
        }
      ],
      "available": true
    },
    {
      "device_id": "device_kitchen_oven",
      "room_id": "room_kitchen",
      "display_name": "厨房烤箱",
      "kind": "actuator",
      "device_type": "oven",
      "state": {
        "on": false,
        "mode": "bake",
        "target": 180.0
      },
      "actions": [
        {
          "action": "turn_on",
          "params": {}
        },
        {
          "action": "turn_off",
          "params": {}
        },
        {
          "action": "set_mode",
          "params": {
            "mode": {
              "type": "string",
              "enum": [
                "bake",
                "broil",
                "keep_warm"
              ]
            }
          }
        },
        {
          "action": "set_temperature",
          "params": {
            "value": {
              "type": "number",
              "minimum": 50.0,
              "maximum": 250.0,
              "step": 5.0
            }
          }
        }
      ],
      "available": true
    }
  ]
}

这个例子的正确输出：
{"intent":"月底加班结束要离开，眼睛累了，想把卧室主灯关掉","conditions":[{"device_id":"device_bedroom_light","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。不要照抄例子里的关灯，必须根据下面这份新的画像和 s0 另写一份 T1。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
