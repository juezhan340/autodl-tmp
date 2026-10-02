功能
你是数据辅助生成器。根据本轮 s0 写一份 T3 模糊意图 task JSON。
唯一一条 condition，keep 与 required_observations 必须是空数组，outcome=completed。
intent 只写当下感受，不出现调、关、开、打开、关掉、调到、把某设备；
感受必须能落到本轮一台真实设备。不要写用户那句口语，只输出一个 JSON 对象。

operator 只有三种：eq、ge、le。
  eq   开关和模式：
       潮（身上发潮）→ 加湿器 on eq false；干（嗓子干）→ 加湿器 on eq true；
       刺眼（灯太亮）→ 主灯 mode eq dim。
  ge   连续量调高，表示比现在高：冷 → 空调 target ge，value 填 s0 当前值。
  le   连续量调低，表示比现在低：热、闷、蒸 → 空调 target le；吵 → 电视、风扇 level le；
       value 填当前值。
  不要另编 26 这类门槛数字；不要用 on eq 去凑有连续轴的设备（空调、台灯、电视）。

对齐
  感受方向必须和 operator 一致：冷对 ge，热对 le，潮对关掉，干对打开，刺眼对 dim，吵对 level le。
  一句话只写一个方向的感受；不要同时写「闷」和「潮」这种两个方向。
  加湿器已经是那个开关，就换感受；不要把干写成关掉、把潮写成打开。
  ge 已经顶到上限、le 已经顶到下限、eq 已经成立 → 换感受或换设备，不要出成立不了的题。
  家里没有的传感器、家具不要写；有台灯不等于有光照传感器。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子（卧室空调 27，加湿器关着，客厅电视音量 40）
对  屋里像蒸笼      空调 target le，value=27.0
对  有点冷          空调 target ge，value=27.0
对  嗓子干          加湿器 on eq true
对  灯刺得睁不开    主灯 mode eq dim
错  热却把 value 写成 26
错  人说潮却写加湿器打开
错  intent 写成「把空调调低一点」
错  一句里同时写「闷」和「身上发潮」

完整例子
本轮画像：
{"persona_id":"p04","name":"陈浩","age":22,"occupation":"大学生","habits":"凌晨还在书桌前，台灯调到够亮；熬夜怕热，睡觉要把房间弄凉快"}
本轮 s0：
{"rooms":[{"room_id":"room_bedroom","display_name":"卧室","device_ids":["device_bedroom_light","device_bedroom_climate","device_bedroom_humidifier","sensor_bedroom_env"]},{"room_id":"room_living","display_name":"客厅","device_ids":["device_living_tv"]}],
"devices":[
{"device_id":"device_bedroom_light","room_id":"room_bedroom","display_name":"卧室主灯","kind":"actuator","device_type":"light","state":{"on":true,"mode":"bright"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["dim","bright"]}}}],"available":true},
{"device_id":"device_bedroom_climate","room_id":"room_bedroom","display_name":"卧室空调","kind":"actuator","device_type":"climate","state":{"on":true,"mode":"cool","target":27.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["off","cool","heat","auto"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":7.0,"maximum":32.0,"step":0.5}}}],"available":true},
{"device_id":"device_bedroom_humidifier","room_id":"room_bedroom","display_name":"卧室加湿器","kind":"actuator","device_type":"humidifier","state":{"on":false},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}],"available":true},
{"device_id":"sensor_bedroom_env","room_id":"room_bedroom","display_name":"卧室温湿度传感器","kind":"sensor","device_type":"environment_sensor","state":{"temperature":30.0,"humidity":35.0},"actions":[],"available":true},
{"device_id":"device_living_tv","room_id":"room_living","display_name":"客厅电视","kind":"actuator","device_type":"tv","state":{"on":true,"mode":"tv","level":40},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["tv","hdmi","av"]}}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}]}

正确输出：
{"intent":"屋里像蒸笼，睡不着","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子里的设备和数值；本轮按 {{s0}} 另写。

本轮输入
本轮画像：
{{persona}}
本轮 s0：
{{s0}}
