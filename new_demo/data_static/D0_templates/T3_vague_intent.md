你要干什么：
你是数据辅助生成器。根据本轮画像和 s0，写一份 T3 模糊意图的 task JSON。
隐藏条件仍是唯一一条：一台设备一个字段。outcome 必须是 completed。
intent 写成生活感受，不要出现动作名，不要写「把某设备调到某值」。
keep、required_observations 为空数组。
operator 只许 eq、ge、le：
  开关、模式用 eq。
  「凉快一点、再暖一点、暗一点、再湿一点」必须用 ge 或 le，不要编一个精确温度再 eq。
  该条件在当前 s0 上必须尚未成立。例如现在 target=27，想凉快，写 le 26 或 le 25；不要写 le 28，也不要写 eq 24。
  value 必须落在该设备 actions 的 min/max 里。
后面的用户话可以不点设备、不点数字，但你现在写的这一条就是唯一正确答案。
不要编造设备，不要写用户那句口语。

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p04","name":"陈浩","age":22,"occupation":"大学生","habits":"凌晨还在书桌前，台灯要亮、主灯可关；熬夜怕热，睡觉要把房间弄凉快，冰箱常翻饮料"}

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
{"intent":"屋里闷得睡不着，想凉快一点好休息","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":26.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。不要照抄例子里的二十六度，必须根据下面这份新的画像和 s0 另写一份 T3。先看 s0 里该字段的当前值，再决定 ge 还是 le、value 取多少。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
