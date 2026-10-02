功能
你是数据辅助生成器。根据本轮 s0 写一份 T2 多设备控制 task JSON。
T2 同时控制二到三台设备，另外点名一台保持不动：
  conditions 两条或三条，keep 恰好一条，required_observations 必须是空数组，outcome=completed。
intent 里出现的设备 = conditions 的设备 + keep 那一台，不多不少。
画像只借口吻：不要写本轮没有的房间、设备、传感器。
不要写用户那句口语，只输出一个 JSON 对象。

写法
  conditions 每条只选 eq、ge、le 里的一种，同一份可以混用。
  eq 用在开关、模式、精确数值：intent 把目标说死，关掉、调到暗档、开快洗。
  ge / le 只用在连续量（target、level）：value 填 s0 当前值，intent 只说方向，调高一点、声音小一点。
  keep 只能 eq，value 取 s0 当前值，这台必须不在 conditions 里。
  主灯用 on 或 mode，台灯用 level，加湿器只有 on；字段和范围以 s0 的 actions 为准。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子（卧室空调 27，客厅电视开着，卧室加湿器关着）
对  conditions 电视关掉 + 空调调低一点（value=27.0），keep 加湿器别动
     intent：睡觉前想凉一点，客厅电视关掉，卧室空调调低一点，卧室加湿器别动
错  intent 多了客厅主灯，conditions 里没有它
错  keep 写成「别太低」这种方向，keep 只能 eq
错  conditions 或 keep 写了本轮没有的房间、设备
错  空调 le 的 value 写成 26

完整例子
本轮画像：
{"persona_id":"p16","name":"唐宁","age":24,"occupation":"实习生","habits":"合租，只动自己卧室的灯、空调和加湿器，客厅电视和厨房设备不要动；睡觉前想凉一点"}
本轮 s0：
{"rooms":[{"room_id":"room_bedroom","display_name":"卧室","device_ids":["device_bedroom_light","device_bedroom_climate","device_bedroom_humidifier","sensor_bedroom_env"]},{"room_id":"room_living","display_name":"客厅","device_ids":["device_living_tv"]}],
"devices":[
{"device_id":"device_bedroom_light","room_id":"room_bedroom","display_name":"卧室主灯","kind":"actuator","device_type":"light","state":{"on":true,"mode":"bright"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["dim","bright"]}}}],"available":true},
{"device_id":"device_bedroom_climate","room_id":"room_bedroom","display_name":"卧室空调","kind":"actuator","device_type":"climate","state":{"on":true,"mode":"cool","target":27.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["off","cool","heat","auto"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":7.0,"maximum":32.0,"step":0.5}}}],"available":true},
{"device_id":"device_bedroom_humidifier","room_id":"room_bedroom","display_name":"卧室加湿器","kind":"actuator","device_type":"humidifier","state":{"on":false},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}],"available":true},
{"device_id":"sensor_bedroom_env","room_id":"room_bedroom","display_name":"卧室温湿度传感器","kind":"sensor","device_type":"environment_sensor","state":{"temperature":30.0,"humidity":35.0},"actions":[],"available":true},
{"device_id":"device_living_tv","room_id":"room_living","display_name":"客厅电视","kind":"actuator","device_type":"tv","state":{"on":true,"mode":"tv","level":40},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["tv","hdmi","av"]}}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}]}

正确输出：
{"intent":"睡觉前想凉一点，客厅电视关掉，卧室空调调低一点，卧室加湿器别动","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[{"device_id":"device_bedroom_humidifier","field":"on","operator":"eq","value":false}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子里的设备和数值；本轮按 {{s0}} 另写。

本轮输入
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
