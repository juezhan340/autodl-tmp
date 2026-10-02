功能
审查这句 T5 请求。必要信息是问状态，不是叫人调设备。
问了本轮读不到的量（没有的传感器、没有的房间、光线、噪声）→ TARGET_NOT_COVERED。
叫人去调设备 → EXTRA_INTENT。闲话不算多。
只输出一个 JSON：{"accept":true,"codes":[]} 或 {"accept":false,"codes":[...]}。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
过  鼻子有点干，卧室现在湿不湿、热不热？
拒  卧室光线够不够？（没有光照传感器）
拒  把卧室空调关掉（这是控制）

完整例子
例子 A 该过：intent 晚上鼻子容易干，想知道卧室现在湿不湿、热不热；task 空条件；user_request 鼻子有点干，卧室现在湿不湿、热不热？
正确输出 {"accept":true,"codes":[]}
例子 B 该拒：同一份 task；user_request 卧室光线够不够，把灯调亮一点。
正确输出 {"accept":false,"codes":["TARGET_NOT_COVERED"]}

本轮输入
本轮房间：{{rooms}}
本轮设备显示名：{{display_names}}
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮 user_request：{{user_request}}
