你要干什么：
审查这句 T5 请求。必要信息是问状态。闲话不算多。
叫人去调设备 → EXTRA_INTENT。
问了本轮读不到的量（没有的传感器、没有的房间、光线、噪声）→ TARGET_NOT_COVERED。
只输出一个 JSON。

先看一个完整例子。

例子里的 intent：
晚上鼻子容易干，想知道卧室现在湿不湿、热不热
例子里的 task：
{"intent":"晚上鼻子容易干，想知道卧室现在湿不湿、热不热","conditions":[],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子里的 user_request：
鼻子有点干，卧室现在湿不湿、热不热？
这个例子的正确输出：
{"accept":true,"codes":[]}

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
