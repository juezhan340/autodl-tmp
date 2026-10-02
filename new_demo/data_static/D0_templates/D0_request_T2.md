你要干什么：
代用户写一句家里的口语请求。conditions 有几条，话里就要有几处对得上的必要信息。keep 再带一句别动。
eq 说精确目标。ge 和 le 只说方向，不要念出数字。
可以加与设备无关的闲话，让句子自然。闲话不是多出来要调的设备。
不要出现 device_id、action 名、field、operator。
不要让 conditions 或 keep 里没有的设备变成要做的事。只输出这一句话。

小例子

对  电视关掉 + 空调调低一点 + 冰箱别动
错  少说冰箱别动
错  空调 le 说成调到二十六度
错  电视 eq 说成声音小一点

先看一个完整例子。

例子里的 intent：
合租生怕动到别人的厨房，自己只想把客厅弄安静、卧室凉快一点
例子里的 task：
{"intent":"合租生怕动到别人的厨房，自己只想把客厅弄安静、卧室凉快一点","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[{"device_id":"device_kitchen_fridge","field":"target","operator":"eq","value":4.0}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子里的显示名：
卧室主灯、卧室台灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视、厨房冰箱、厨房烤箱
这个例子的正确输出：
我先歇一会儿，把客厅电视关掉，卧室空调调低一点，厨房冰箱别动。

现在轮到你。
本轮 intent：
{{intent}}
本轮 task：
{{task}}
本轮可用显示名（display_name）：
{{display_names}}
