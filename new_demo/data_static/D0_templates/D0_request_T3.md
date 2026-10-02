你要干什么：
代用户写一句家里的口语请求。本轮是模糊意图。必要信息是感受，不是控制指令：闷、热、冷、刺眼、潮、吵。
不要点设备名，不要说调、关、开、关掉、调低、调到。
可以加与设备无关的闲话。不要出现 device_id、action 名。只输出这一句话。

小例子

对  屋里像蒸笼     写到一半了，屋里闷得慌，睡不着
错  把卧室空调调低一点
错  点名加湿器

先看一个完整例子。

例子里的 intent：
熬夜写到一半，屋里像蒸笼
例子里的 task：
{"intent":"熬夜写到一半，屋里像蒸笼","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子里的显示名：
卧室主灯、卧室台灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视、厨房冰箱、厨房烤箱
这个例子的正确输出：
写到一半了，屋里闷得慌，睡不着。

现在轮到你。
本轮 intent：
{{intent}}
本轮 task：
{{task}}
本轮可用显示名（display_name）：
{{display_names}}
