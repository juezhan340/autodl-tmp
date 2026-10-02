功能
代用户写一句家里的口语请求。本轮是模糊意图，必要信息是感受，不是控制指令。
不要点设备名，不要说调、关、开、关掉、调低、调到。
感受方向和 task 一致：task 是加湿器关掉就写潮、黏；task 是空调调低就写热、闷；task 是主灯调暗就写刺眼、太亮。
intent 里若有两种感受，只写和 task 同向的那一种，不要写「又闷又潮」。
可以加与设备无关的闲话。只输出这一句话。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
对  屋里像蒸笼           task 是空调 le      写到一半了，屋里闷得慌，睡不着
对  身上黏糊糊的         task 是加湿器关掉   身上黏糊糊的，翻来覆去睡不踏实
错  「把卧室空调调低一点」
错  点名加湿器
错  同时写「屋里闷」和「身上发潮」

完整例子
intent：熬夜写到一半，屋里像蒸笼
task：{"intent":"熬夜写到一半，屋里像蒸笼","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
可用显示名：卧室主灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视
正确输出：写到一半了，屋里闷得慌，睡不着。

本轮输入
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮可用显示名（display_name）：{{display_names}}
