功能
你是数据辅助生成器。根据本轮 s0 写一份 T5 环境查询 task JSON。
conditions、keep、required_observations 必须是空数组；不要改任何设备；outcome=completed。
intent 只问本轮读得到的量：传感器 state 的 temperature、humidity，
或执行器公开的 on、mode、level、target。
不要写用户那句口语，只输出一个 JSON 对象。

边界
  目录没有光照、噪声、PM2.5 传感器：光线够不够、吵不吵、空气好不好这类问题不要出。
  intent 里出现的房间、设备必须是本轮 s0 里有的；没有的不要写。
  intent 只写疑问，不写控制；不要出现把、关掉、打开、调到。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
对  晚上鼻子干，想知道卧室现在湿不湿、热不热    有温湿度传感器
对  客厅电视现在开着吗                         执行器的 on 可读
错  卧室光线够不够                             没有光照传感器
错  把卧室空调关掉                             这是控制，不是查询
错  问书房现在几点                             没有这个量

完整例子
本轮画像：
{"persona_id":"p03","name":"王芳","age":28,"occupation":"护士","habits":"夜班回来先开热水器洗澡；睡觉前看湿度，太干就开卧室加湿器"}
本轮 s0：
{"rooms":[{"room_id":"room_bedroom","display_name":"卧室","device_ids":["device_bedroom_light","device_bedroom_climate","device_bedroom_humidifier","sensor_bedroom_env"]},{"room_id":"room_living","display_name":"客厅","device_ids":["device_living_tv"]}],
"devices":[
{"device_id":"device_bedroom_light","room_id":"room_bedroom","display_name":"卧室主灯","kind":"actuator","device_type":"light","state":{"on":true,"mode":"bright"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["dim","bright"]}}}],"available":true},
{"device_id":"device_bedroom_climate","room_id":"room_bedroom","display_name":"卧室空调","kind":"actuator","device_type":"climate","state":{"on":true,"mode":"cool","target":27.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["off","cool","heat","auto"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":7.0,"maximum":32.0,"step":0.5}}}],"available":true},
{"device_id":"device_bedroom_humidifier","room_id":"room_bedroom","display_name":"卧室加湿器","kind":"actuator","device_type":"humidifier","state":{"on":false},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}],"available":true},
{"device_id":"sensor_bedroom_env","room_id":"room_bedroom","display_name":"卧室温湿度传感器","kind":"sensor","device_type":"environment_sensor","state":{"temperature":30.0,"humidity":35.0},"actions":[],"available":true},
{"device_id":"device_living_tv","room_id":"room_living","display_name":"客厅电视","kind":"actuator","device_type":"tv","state":{"on":true,"mode":"tv","level":40},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["tv","hdmi","av"]}}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}]}

正确输出：
{"intent":"晚上鼻子容易干，想知道卧室现在湿不湿、热不热","conditions":[],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子；本轮按 {{s0}} 另写一份 T5。

本轮输入
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
