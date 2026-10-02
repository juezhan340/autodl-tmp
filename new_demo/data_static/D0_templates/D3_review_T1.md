你要干什么：
审查这句用户请求是否覆盖了 T1 那一条 condition。intent 只是背景。闲话不算多、不算漏。
eq 听得出设备和精确目标。
ge 和 le 听得出设备和方向；话里念出数字反而错。
第二台要调的设备 → EXTRA_INTENT。
点了本轮没有的房间或设备 → TARGET_NOT_COVERED。
出现 device_id、action 名、field、operator → HARD_LEAKAGE。
只输出一个 JSON。

小例子

过  eq  关掉客厅电视          把客厅电视关掉吧
过  le  空调调低一点          卧室空调调低一点
拒  le  调到二十六度
拒  eq  调低一点

先看两个完整例子。例子 A 该过，例子 B 该拒。

例子 A 的 intent：
应酬完只想家里安静
例子 A 的 task：
{"intent":"应酬完只想家里安静","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],"keep":[],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子 A 的 user_request：
刚应酬完，有点累，把客厅电视关掉吧。
例子 A 的正确输出：
{"accept":true,"codes":[]}

例子 B 的 user_request（同一份 task）：
把客厅电视调低一点。
例子 B 的正确输出：
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
