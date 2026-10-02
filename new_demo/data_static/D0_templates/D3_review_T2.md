你要干什么：
审查这句 T2 请求。conditions 有几条就要听得出几处，keep 要听到别动。闲话不算多。
intent 里多写、conditions 没有的设备，用户话没提也不算漏。
eq 说成调低一点、ge 或 le 说成精确数字 → TARGET_NOT_COVERED。
少一截 → TARGET_NOT_COVERED。
多了一台要调的设备 → EXTRA_INTENT。
点了本轮没有的房间或设备 → TARGET_NOT_COVERED。
只输出一个 JSON。

小例子

过  电视关掉，空调调低一点，冰箱别动
拒  只说把客厅电视关掉
拒  空调说成调到二十六度

先看两个完整例子。例子 A 该过，例子 B 该拒。

例子 A 的 intent：
合租生怕动到别人的厨房，自己只想把客厅弄安静、卧室凉快一点
例子 A 的 task：
{"intent":"合租生怕动到别人的厨房，自己只想把客厅弄安静、卧室凉快一点","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[{"device_id":"device_kitchen_fridge","field":"target","operator":"eq","value":4.0}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
例子 A 的 user_request：
我先歇一会儿，把客厅电视关掉，卧室空调调低一点，厨房冰箱别动。
例子 A 的正确输出：
{"accept":true,"codes":[]}

例子 B 的 user_request（同一份 task）：
把客厅电视关掉。
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
