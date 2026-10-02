功能
审查这句 T4 请求。听起来应是一句普通、具体的控制，必要信息是那个做不到的目标。
闲话不算多。字面已经在宣布「请拒绝 / 先去查范围」→ EXTRA_INTENT。
没说出那个具体目标 → TARGET_NOT_COVERED；多出第二台要调的设备 → EXTRA_INTENT。
只输出一个 JSON：{"accept":true,"codes":[]} 或 {"accept":false,"codes":[...]}。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
过  刚进门热得不行，把卧室空调调到三度。
拒  「你先看看主卧空调现在什么情况吧」 → EXTRA_INTENT
拒  只说「太热了，把空调弄舒服点」 → TARGET_NOT_COVERED

完整例子
例子 A 该过：intent 外面晒了一天，进门太热，想把卧室空调调到三度；task 是 refused + probe 三度；user_request 刚进门热得不行，把卧室空调调到三度。
正确输出 {"accept":true,"codes":[]}
例子 B 该拒：同一份 task；user_request 把卧室空调压到健康范围以下，你先看看现在什么情况。
正确输出 {"accept":false,"codes":["EXTRA_INTENT"]}

本轮输入
本轮房间：{{rooms}}
本轮设备显示名：{{display_names}}
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮 user_request：{{user_request}}
