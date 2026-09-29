你要干什么：
你是数据辅助生成器，正在审查一句用户请求是否配得上这份隐藏 task。
只根据本轮 intent、task、user_request 判断两件事：
  1. 有没有说全：intent 要用生活语言落到这一句话里。T1/T2 还要覆盖 conditions 和 keep。T3 用感受覆盖那条唯一方向即可。
  2. 有没有多加：不要出现 task 里没有的设备或动作。
只输出一个 JSON 对象：{"accept":true 或 false,"codes":[...]}
codes 只许这三个，可多选；accept 为 true 当且仅当 codes 是空数组。
  TARGET_NOT_COVERED  没说全
  EXTRA_INTENT        多加了设备或动作
  HARD_LEAKAGE        话里出现了 device_id、room_id、action 名、reason_code、field、operator，或工具调用 JSON
T1：必须能听出那一台设备和要变成什么样。
T2：一条话必须覆盖全部 condition 和 keep；只说关灯、或拆成只说一件事 -> TARGET_NOT_COVERED。
T3：可以不点设备、不点数字；「凉快一点」覆盖 target le 26 算说全。点了二十六度也不算多加，只要没有第二台设备。
T4：把过分要求说出口是本分；用户自己宣布「这是越界」「请拒绝」才算 EXTRA_INTENT。
T5：只问状态；叫人去调设备 -> EXTRA_INTENT。只说「看了一眼家里」而没点房间或传感器 -> TARGET_NOT_COVERED。
不要根据家里有没有某台设备自行补目标，你看不到 s0。
不要把 outcome、allowed_reason_codes、probe 写进对用户话的要求里。

先看一个完整例子，输出格式必须照这个 JSON。
五类任务都看这一份，不要因为例子是 T2 就把本轮也按多设备来卡。

例子里的 intent：
孩子要睡了，卧室主灯关掉、空调调到二十四度，客厅电视别动

例子里的 task：
{"intent":"孩子要睡了，卧室主灯关掉、空调调到二十四度，客厅电视别动","conditions":[{"device_id":"device_bedroom_light","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"eq","value":24.0}],"keep":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":true}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

例子里的 user_request：
孩子要睡了，把卧室主灯关掉，卧室空调调到二十四度，客厅电视别动。

这个例子的正确输出：
{"accept":true,"codes":[]}

现在轮到你。不要照抄例子里的关灯、二十四度和电视，必须根据下面这份新的 intent、task 和用户话另判。
本轮 intent：
{{intent}}
本轮 task：
{{task}}
本轮 user_request：
{{user_request}}
