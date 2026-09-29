你要干什么：
你是数据辅助生成器。根据本轮画像和 s0，写一份 T2 多设备控制的 task JSON。
conditions 必须有两条或三条，覆盖不同设备或同一设备的不同字段，全部用 operator=eq。
keep 至少写一台本次不能动的设备，value 取 s0 里该字段的当前值。
required_observations 为空数组。outcome 必须是 completed。
可以跨品类，例如关电视 + 开洗碗机；没有的设备不要编。intent 必填，要体现画像。
不要写用户那句口语。

先看一个完整例子，输出格式必须照这个。

例子里的画像：
{"persona_id":"p02","name":"张强","age":35,"occupation":"销售","habits":"家里有幼儿，十点后客厅电视必须关、走廊灯不要亮；脏衣服隔天丢进洗衣机开快洗"}

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
{"intent":"孩子要睡了，卧室主灯关掉、空调调到二十四度，客厅电视别动","conditions":[{"device_id":"device_bedroom_light","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"eq","value":24.0}],"keep":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":true}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

现在轮到你。不要照抄例子里的关灯、二十四度和电视，必须根据下面这份新的画像和 s0 另写一份 T2。
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
