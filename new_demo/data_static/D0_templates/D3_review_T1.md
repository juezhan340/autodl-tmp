功能
审查这句 T1 请求是否覆盖那一条 condition。intent 只是背景，闲话不算多、不算漏。
eq 要听得出设备和精确目标；ge / le 要听得出设备和方向，话里念出数字反而错。
第二台要调的设备 → EXTRA_INTENT。
点了本轮没有的房间或设备 → TARGET_NOT_COVERED。
device_id、action 名这类硬泄露由程序先拦，你只判语义。
只输出一个 JSON：{"accept":true,"codes":[]} 或 {"accept":false,"codes":["TARGET_NOT_COVERED"]}。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
过  eq  关掉客厅电视        把客厅电视关掉吧
过  le  空调调低一点        卧室空调调低一点
拒  eq  说成「调低一点」
拒  le  念成「调到二十六度」
拒  多出第二台要调的设备

完整例子
例子 A 该过：intent 应酬完只想家里安静；task {"conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false}],...}；user_request 刚应酬完，有点累，把客厅电视关掉吧。
正确输出 {"accept":true,"codes":[]}
例子 B 该拒：同一份 task；user_request 把客厅电视调低一点。
正确输出 {"accept":false,"codes":["TARGET_NOT_COVERED"]}

本轮输入
本轮房间：{{rooms}}
本轮设备显示名：{{display_names}}
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮 user_request：{{user_request}}
