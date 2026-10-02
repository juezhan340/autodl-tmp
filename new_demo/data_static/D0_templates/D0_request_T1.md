功能
代用户写一句家里的口语请求。这一条 condition 的必要信息必须在话里。
eq 和 ge / le 在说人话时是两套口气：
  eq       是一个精确的点：点名设备，把目标说死——调到二十六度、切到暗档、关掉。
           不能写成「调低一点」这种宽泛话，否则助手落不到那个确定目标。
  ge / le  是一个方向：点名设备，只说往哪边走——调低一点、调高一点、声音小一点。
           不要念出数字；一旦报数，方向题就变成了精确题。
可以加刚下班、阴雨天、想歇一会儿这种闲话；闲话不是第二台要调的设备。
不要出现 device_id、room_id、action 名、field、operator、reason_code、工具 JSON。
不要让 condition 里没有的设备变成要做的事。只输出这一句话。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
对  eq  电视关掉          把客厅电视关掉吧
对  le  空调 value=27     卧室空调调低一点
对  ge  音量 value=40     电视声音再大一点
错  le  说成「调到二十六度」 —— le 只要方向，报数字就把方向题写成了精确题
错  eq  说成「调低一点」 —— eq 要精确目标，模糊话让助手不知道落到哪

完整例子
intent：应酬完只想家里安静
task：{"intent":"应酬完只想家里安静","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
可用显示名：卧室主灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视
正确输出：刚应酬完，有点累，把客厅电视关掉吧。

本轮输入
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮可用显示名（display_name）：{{display_names}}
