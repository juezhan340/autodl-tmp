你要干什么：
审查这句 T3 请求。必要信息必须是感受，不能是控制指令。闲话不算多、不算漏。
事实核查：这句话要的方向，不能和 task.condition 相反。
  热、蒸、闷   应对空调 target le（往低调）
  冷           应对空调 target ge（往高调）
  潮、湿       应对加湿器关掉（on eq false）
  干           应对加湿器打开（on eq true）
  刺眼、太亮   应对主灯 mode eq dim
  吵           应对电视或风扇 level le（往低调）
人说潮、task 却是加湿器打开 → TARGET_NOT_COVERED。
人说干、task 却是加湿器关掉 → TARGET_NOT_COVERED。
出现关掉、调低、调到、点名设备 → TARGET_NOT_COVERED。
只输出一个 JSON。

小例子

过  屋里闷得慌           task 是空调 le
拒  把卧室空调调低一点
拒  人说潮，task 却打开加湿器

先看三个完整例子。A 该过，B 是控制指令，C 是方向相反。

例子 A 的 intent：
熬夜写到一半，屋里像蒸笼
例子 A 的 task：
{"intent":"熬夜写到一半，屋里像蒸笼","conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子 A 的 user_request：
写到一半了，屋里闷得慌，睡不着。
例子 A 的正确输出：
{"accept":true,"codes":[]}

例子 B 的 user_request（同一份 task）：
把卧室空调调低一点。
例子 B 的正确输出：
{"accept":false,"codes":["TARGET_NOT_COVERED"]}

例子 C 的 intent：
屋里有点闷，身上发潮
例子 C 的 task：
{"intent":"屋里有点闷，身上发潮","conditions":[{"device_id":"device_living_humidifier","field":"on","operator":"eq","value":true}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子 C 的 user_request：
这屋里闷闷的，身上还有点潮，怪不舒服的。
例子 C 的正确输出：
{"accept":false,"codes":["TARGET_NOT_COVERED"]}

现在轮到你。
本轮房间：
{{rooms}}
本轮设备显示名：
{{display_names}}
本轮 intent：
{{intent}}
本轮 task：
{{task}}
本轮 user_request：
{{user_request}}
