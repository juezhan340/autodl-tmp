功能
审查这句 T2 请求。conditions 有几条就要听得出几处，keep 要听到「别动」；闲话不算多。
每截和 condition 的 operator 同型，和 task 的写法一一对应：
  eq       要听到精确目标；说成方向话 → TARGET_NOT_COVERED。
  ge / le  要听到方向；念出数字 → TARGET_NOT_COVERED。
少一截 → TARGET_NOT_COVERED；多了一台要调的设备 → EXTRA_INTENT。
intent 里多写、conditions 没有的设备，用户话没提不算漏。
只输出一个 JSON：{"accept":true,"codes":[]} 或 {"accept":false,"codes":[...]}。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
过  电视关掉，空调调低一点，加湿器别动
拒  只说「把客厅电视关掉」 —— 少了一截 condition，必要信息没说全
拒  空调说成「调到二十六度」 —— le 只要方向，报数字就成了精确题
拒  多开一台本轮没让动的设备 —— 话里只能出现 conditions 和 keep 里的设备

完整例子
例子 A 该过：task 两条 condition 加一条 keep；user_request 我先歇一会儿，把客厅电视关掉，卧室空调调低一点，卧室加湿器别动。
正确输出 {"accept":true,"codes":[]}
例子 B 该拒：同一份 task；user_request 把客厅电视关掉。
正确输出 {"accept":false,"codes":["TARGET_NOT_COVERED"]}

本轮输入
本轮房间：{{rooms}}
本轮设备显示名：{{display_names}}
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮 user_request：{{user_request}}
