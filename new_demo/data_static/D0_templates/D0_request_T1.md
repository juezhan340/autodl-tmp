功能
代用户写一句家里的口语请求。这一条 condition 的必要信息必须在话里。
eq 点名设备，说出变成什么样；ge / le 点名设备，只说方向，不要念数字。
可以加刚下班、阴雨天、想歇一会儿这种闲话；闲话不是第二台要调的设备。
不要出现 device_id、room_id、action 名、field、operator、reason_code、工具 JSON。
不要让 condition 里没有的设备变成要做的事。只输出这一句话。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
对  eq  电视关掉          把客厅电视关掉吧
对  le  空调 value=27     卧室空调调低一点
对  ge  音量 value=40     电视声音再大一点
错  le  说成「调到二十六度」
错  eq  说成「调低一点」

完整例子
intent：应酬完只想家里安静
task：{"intent":"应酬完只想家里安静","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
可用显示名：卧室主灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视
正确输出：刚应酬完，有点累，把客厅电视关掉吧。

本轮输入
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮可用显示名（display_name）：{{display_names}}
