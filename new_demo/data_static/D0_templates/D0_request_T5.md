你要干什么：
代用户写一句家里的口语请求。
必要信息是问家里现在能读到的状态。不要叫人去调设备。
可以加与设备无关的闲话。不要问 task 里没有的量，不要问光线、噪声（除非 task 里就有）。
不要出现 device_id、action 名。
只输出这一句话。

先看一个完整例子。

例子里的 intent：
晚上鼻子容易干，想知道卧室现在湿不湿、热不热
例子里的 task：
{"intent":"晚上鼻子容易干，想知道卧室现在湿不湿、热不热","conditions":[],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子里的显示名：
卧室主灯、卧室台灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视、厨房冰箱、厨房烤箱
这个例子的正确输出：
鼻子有点干，卧室现在湿不湿、热不热？

现在轮到你。
本轮 intent：
{{intent}}
本轮 task：
{{task}}
本轮可用显示名（display_name）：
{{display_names}}
