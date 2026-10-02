功能
你是数据辅助生成器。根据本轮 s0 写一份 T1 单设备控制 task JSON。
T1 只动一台设备的一个字段：intent 一句，conditions 一条，keep 与 required_observations 必须是空数组，
expected_finish 是 {"outcome":"completed","allowed_reason_codes":[]}。
不要写用户那句口语，不要解释，只输出一个 JSON 对象。

一条 condition 的 operator 只有三种：eq、ge、le。
  eq   开关、模式、精确数值；value 就是目标。
       intent 把目标说死：关掉、调到暗档、调到二十二度、调到百分之三十。
  ge   连续量调高；value 填 s0 里该字段的当前值；intent 只说方向：调高一点、再暖和一点。
  le   连续量调低；value 填当前值；intent 只说方向：调低一点、声音小一点。
连续量只有两类字段：target（空调、热水器、烤箱、冰箱）与 level（台灯、电视、风扇）。
on、mode 只能 eq；ge / le 的 value 是 s0 快照，不是门槛，不要另编 26、80 这类数字。

能力对照（设备和字段必须来自本轮 s0）
  主灯用 on 或 mode（dim / bright），没有 level；台灯用 on 或 level；
  夜灯、廊灯、厨灯、浴灯、阳台灯、加湿器只有 on；
  空调、热水器、烤箱、冰箱用 target；风扇、电视用 level。
  本轮没有的房间、设备、字段，不要写。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子（卧室空调 target=27，客厅电视 level=40）
对  eq  客厅电视 on eq false      intent：想把客厅电视关掉
对  ge  客厅电视 level ge 40      intent：声音有点小，想调大一点
对  le  卧室空调 target le 27.0   intent：屋里有点热，想调低一点
错  le 的 value 写成 26
错  le 的 intent 写成「调到二十六度」
错  eq 的 intent 写成「调低一点」
错  intent 里出现本轮没有的书房台灯

完整例子
本轮画像：
{"persona_id":"p08","name":"周凯","age":31,"occupation":"快递员","habits":"夏天在外面暴晒，进门先要凉快，灯马上亮"}
本轮 s0：
{"rooms":[{"room_id":"room_bedroom","display_name":"卧室","device_ids":["device_bedroom_light","device_bedroom_climate","device_bedroom_humidifier","sensor_bedroom_env"]},{"room_id":"room_living","display_name":"客厅","device_ids":["device_living_tv"]}],
"devices":[
{"device_id":"device_bedroom_light","room_id":"room_bedroom","display_name":"卧室主灯","kind":"actuator","device_type":"light","state":{"on":true,"mode":"bright"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["dim","bright"]}}}],"available":true},
{"device_id":"device_bedroom_climate","room_id":"room_bedroom","display_name":"卧室空调","kind":"actuator","device_type":"climate","state":{"on":true,"mode":"cool","target":27.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["off","cool","heat","auto"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":7.0,"maximum":32.0,"step":0.5}}}],"available":true},
{"device_id":"device_bedroom_humidifier","room_id":"room_bedroom","display_name":"卧室加湿器","kind":"actuator","device_type":"humidifier","state":{"on":false},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}],"available":true},
{"device_id":"sensor_bedroom_env","room_id":"room_bedroom","display_name":"卧室温湿度传感器","kind":"sensor","device_type":"environment_sensor","state":{"temperature":30.0,"humidity":35.0},"actions":[],"available":true},
{"device_id":"device_living_tv","room_id":"room_living","display_name":"客厅电视","kind":"actuator","device_type":"tv","state":{"on":true,"mode":"tv","level":40},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["tv","hdmi","av"]}}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}]}

正确输出：
{"intent":"进门还是热，想把卧室空调调低一点","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

同一套房换一条 eq：
{"intent":"睡前想把客厅电视关掉","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子里的设备和数值；本轮按 {{s0}} 另写。

本轮输入
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
