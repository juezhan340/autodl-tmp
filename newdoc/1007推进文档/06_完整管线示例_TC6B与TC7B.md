# 06 完整管线示例：TC6B 相对时间调度 与 TC7B 单轮读写记忆

> 依据：05 现行版（instant_conditions / due_conditions；C-2"即时终态 + 定时终态"双分支；
> C-5 任务族独有分支；required_calls 收敛在 base_task；TC6A/TC7A 不做 D6 复判；
> base_time 在 s0 里；due_state 已删；设备变更待落地）。
> 本文只走两类：TC6B（相对时间一次性预约，模型须写出绝对时刻）
> 与 TC7B（单轮读写记忆：写偏好 + 做动作），从提示词到轨迹到数据集完整呈现。
> 起草日期：2026-10-13。

## 0 一屏

```text
管线主链（两类共用，只有提示词与判定不同）

  静态库 D0_templates_tc/ + D0_homes / D0_devices / D0_personas
        ↓
  D1 造家 + 抽样（户型、设备、画像、base_time 写入 s0；TC7B 记忆开局置空）
        ↓
  D2-1 写 task（外部模型；隐藏真值）
        ↓
  D2-2 写用户话（外部模型；只写用户那句话）
        ↓
  D3 审用户话（程序扫描 + 模型审查；防泄露/漏说）
        ↓
  D4 Oracle（不调模型：时间算术/窗口 + 本地试答 + 影子试答；TC7B 查记忆一致性）
        ↓
  D5 跑轨迹（C 与 A 交互；结束时 C 自动打标签 C-1~C-5）
        ↓
  D6 复核（TC6B：规则可验证 → 跳过；TC7B：★保留三票记忆审查）
        ↓
TC_dataset.jsonl（行结构：scenario / record / labels / category / d6 / d6_votes）
```

```text
两份示例的固定输入（下面所有阶段都围绕它们展开）

  base_time = 2026-10-10 09:30（写进 s0/home）
  家：卧室加湿器 device_bedroom_humidifier（初态 on=true）、
      客厅主灯 device_living_light（初态 on=true）、卧室空调 device_bedroom_climate
  画像：p21，花粉过敏，晚上容易鼻塞

  TC6B  用户话："40 分钟后帮我把卧室加湿器关掉。"
        任务真值：offset_minutes=40 → at_time_expected=2026-10-10 10:10
  TC7B  用户话："记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。"
        开局记忆为空；一句话里同时给"要记住的偏好"和"现在就做的动作"
```

## 1 公共部分

### 1.1 D1 抽样与生成

```text
抽样   户型（D0_homes）、设备（D0_devices）、画像（D0_personas）——同 05
抽样   时间 base_time：D1 从时间池抽（早/午/晚/深夜，工作日/周末），写入 s0（home）
生成   TC7B 的记忆：开局置空（memory_initial = ""）；
        "要记住的内容"由 D2 从请求语境写出，落进 task.memory_task.memory_expected
约束   同一任务只冻结一个 base_time
```

### 1.2 蓝图与运行时结构（沿用 05 的三块 + world）

```text
task 三块（键与 05 完全一致）
  base_task     intent / instant_conditions / keep / required_calls / expected_finish
  time_task     TC6B：time_mention / offset_minutes / at_time_expected / due_steps / due_conditions
                TC7B：{}（不用时间调度）
  memory_task   TC7B：memory_initial / memory_expected / forbidden_actions / turns
                TC6B：{}（不用记忆）
world            horizon_minutes / session_turns（TC7B 运行时另有 memory_initial）
base_time        在 home（s0）里；B reset 从 home 读

TC6B 的 at_time_expected 由程序补算：TC2 收到 offset_minutes 后算 at = base_time + offset，
写进 task.time_task.at_time_expected（出题模型不做算术；D4 再核对一遍）
```

```json
{
  "blueprint_id": "bp_TC7B_0001",
  "category": "TC7B",
  "tc_schema": "v1",
  "home": {
    "base_time": "2026-10-10 09:30",
    "rooms": [
      {"room_id": "room_living", "display_name": "客厅",
       "device_ids": ["device_living_light"]},
      {"room_id": "room_bedroom", "display_name": "卧室",
       "device_ids": ["device_bedroom_climate"]}
    ],
    "devices": ["..."]
  },
  "task": {
    "base_task": {
      "intent": "记住睡觉空调 25.5 度制冷，并关掉客厅主灯",
      "instant_conditions": [{"device_id": "device_living_light", "field": "on",
                              "operator": "eq", "value": false}],
      "keep": [],
      "required_calls": [{"tool": "memory", "op": "write"}],
      "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}
    },
    "time_task": {},
    "memory_task": {
      "memory_initial": "",
      "memory_expected": "睡觉时空调设 25.5 度、制冷",
      "forbidden_actions": [],
      "turns": []
    }
  },
  "user_request": "记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。",
  "world": {"horizon_minutes": 10080, "session_turns": 0}
}
```

```text
D5 组装运行时 scenario（同 05）：home / user_request / task 原样带，world 新块；
memory_initial 从 task.memory_task 搬到 scenario.world.memory_initial（TC7B 时为空串）；
tc_schema / category 只留在蓝图
```

### 1.3 A 提示词装配

```text
A 提示词 = 老 A_policy.md + TC 附加段（按子类拼）
  TC6B 附加段：相对时间调度（见 2.8）——读时钟 → 做加法 → 写绝对时刻 → 写单
  TC7B 附加段：记忆写入（见 3.8）——出现偏好/精确数值 → 先写记忆 → 再做动作
  工具表：全部 8 个（observe_home / inspect_room / inspect_device / execute_action /
          finish / inspect_time / time_control / memory）
```

### 1.4 C 标签口径（两个任务各自写全）

```text
C-1 协议        finish_requested 为真 且 未 truncated 且 没有一轮多工具（TOO_MANY_TOOL_CALLS）

C-2 终态        两个分支，共用同一套条件检查器（与 05 同一定义）：
                · 即时终态：final_state 满足 instant_conditions + keep（空数组过）
                · 定时终态：影子执行（新的 s0 + 模型 steps）终态满足 due_conditions
                TC6B 走"定时"（instant_conditions 固定为空 → 即时分支恒过）；
                TC7B 走"即时"（定时分支不用）

C-3 必需调用     required_calls 都出现过成功调用（空数组过）：
                TC6B = [{"tool":"inspect_time"}]（必须先读时钟）
                TC7B = [{"tool":"memory","op":"write"}]（必须写入过记忆）

C-4 finish      outcome 与 expected_finish.outcome 对齐；refused 的 reason_code 必须落在
                allowed_reason_codes 里；出现 facts 失败；completed 带 reason_code 失败

C-5（任务族独有分支）
                TC6B = 下单检查：预约单建立 且 at 与 at_time_expected 分钟级相等（place_ok）
                       且 没有"该写单却直接执行"（time_error=false）；
                       明细 place_ok / steps_ok / time_error（steps_ok 仅记录）
                TC7B = 记忆写入检查：轨迹里存在一次成功的 memory.write（行为）；
                       写入内容是否正确归 D6（3.9）
```

## 2 TC6B 完整管线

### 2.1 D0 模板：TC6B_task.md（出题提示词全文）

```text
功能
你是数据辅助生成器。根据本轮 s0、画像与 base_time，写一份 TC6B（相对时间一次性预约）的隐藏 task JSON。
只输出一个 JSON 对象，不要写用户话，不要解释。

TC6B 是什么
用户会在话里说一个相对时间（"40 分钟后""半小时后""两个小时后"），
助手要读当前时间、做加法，算出绝对时刻，再写一张一次性预约单。
本局时间冻结：base_time 就是"现在"，不会流逝。

输出字段（task 三块；intent 与 expected_finish 必填、不能为空）
{"base_task": {"intent":"一句话目标",
               "instant_conditions":[],
               "keep":[], "required_calls":[],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {"time_mention":"用户话里的相对时间说法",
               "offset_minutes": 40,
               "at_time_expected":"",
               "due_steps":[{"device_id":"...","action":"...","params":{}}],
               "due_conditions":[{"device_id":"...","field":"...",
                                  "operator":"eq","value":...}]},
 "memory_task": {}}

硬规则
  offset_minutes 取 5~720 的整数；允许跨午夜（23:40 + 40 分钟 = 次日 00:20）
  time_mention 必须是相对说法（"40分钟后""半个小时以后""两小时后"），不能是绝对时刻
  time_mention 不能是"每天/每晚"这类持久规则；出现直接判废
  at_time_expected 留空字符串——由数据程序按 base_time + offset 补算（出题模型不做算术）
  due_steps 1~3 条，设备与动作只能来自本轮 s0
  due_conditions 描述"到点执行后终态应满足什么"（定时终态的判定对象）
  instant_conditions 固定写空数组；required_calls 固定写空数组
  时间相关字段全部放 time_task；memory_task 固定为 {}（TC6B 不用记忆）
  注意：task JSON 里不写类别；蓝图顶层写 category（如 TC6B）

小例子（base_time = 2026-10-10 09:30）
对  time_mention="40分钟后"   → offset_minutes=40（程序算 at=2026-10-10 10:10）
对  time_mention="两个小时后" → offset_minutes=120（程序算 at=2026-10-10 11:30）
错  time_mention="今晚10点"（绝对时间，不属于 TC6B）
错  time_mention="过一会儿"（没有明确数值，不收录）
错  offset_minutes=1441（超过 720）

完整例子
本轮画像：{"persona_id":"p21","name":"李岚","age":29,"habits":"花粉过敏，晚上容易鼻塞"}
本轮 s0：{"rooms":[{"room_id":"room_bedroom","device_ids":["device_bedroom_humidifier"]}],
          "devices":[...]}
本轮 base_time："2026-10-10 09:30"
正确输出：
{"base_task": {"intent":"40 分钟后关掉卧室加湿器",
               "instant_conditions":[], "keep":[], "required_calls":[],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {"time_mention":"40分钟后","offset_minutes":40,"at_time_expected":"",
               "due_steps":[{"device_id":"device_bedroom_humidifier",
                             "action":"turn_off","params":{}}],
               "due_conditions":[{"device_id":"device_bedroom_humidifier","field":"on",
                                  "operator":"eq","value":false}]},
 "memory_task": {}}

不要照抄例子里的设备与数值；本轮按 {{s0}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 2.2 D2-1 输出 + 程序补算

```json
{"base_task": {"intent": "40 分钟后关掉卧室加湿器",
               "instant_conditions": [], "keep": [], "required_calls": [],
               "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
 "time_task": {"time_mention": "40分钟后", "offset_minutes": 40,
               "at_time_expected": "2026-10-10 10:10",
               "due_steps": [{"device_id": "device_bedroom_humidifier",
                              "action": "turn_off", "params": {}}],
               "due_conditions": [{"device_id": "device_bedroom_humidifier", "field": "on",
                                   "operator": "eq", "value": false}]},
 "memory_task": {}}
```

```text
模型只写 offset_minutes；TC2 收到后补算 at_time_expected = base_time + offset（分钟级），
并写回 task.time_task；base_time / horizon_minutes 来自 D1 与 D4，不由出题模型产出
```

### 2.3 D0 模板：D0_request_TC6B.md（写用户话提示词全文）

```text
功能
把 TC6B 的 task 写成一句自然的用户请求。
请求里只能出现相对时间说法；换算后的绝对时刻不能出现在话里——那是答案。

规则
  相对时间用口语："40 分钟后""半个小时后""两个小时后"
  禁止出现 "YYYY-MM-DD HH:MM" 或 "HH:MM" 形式的时刻
  禁止出现 device_id / room_id / 动作名 / 参数名 / 工具名
  可以加一句生活化铺垫，但不要引入第二个任务
  只说这一句话，不要解释

小例子
对  time_mention="40分钟后"   → "40 分钟后帮我把卧室加湿器关掉。"
对  time_mention="两个小时后" → "两个小时以后把厨房冰箱调低一点。"
错  "10:10 把加湿器关掉"（泄露绝对时刻）
错  "把 device_bedroom_humidifier 关掉"（泄露 id）

完整例子
intent：40 分钟后关掉卧室加湿器
task：{"base_task":{"intent":"40 分钟后关掉卧室加湿器","instant_conditions":[],"keep":[],
                    "required_calls":[],
                    "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
       "time_task":{"time_mention":"40分钟后","offset_minutes":40,
                    "at_time_expected":"2026-10-10 10:10",
                    "due_steps":[{"device_id":"device_bedroom_humidifier",
                                  "action":"turn_off","params":{}}],
                    "due_conditions":[{"device_id":"device_bedroom_humidifier","field":"on",
                                       "operator":"eq","value":false}]},
       "memory_task":{}}
可用显示名：卧室加湿器、客厅主灯、卧室空调
正确输出：40 分钟后帮我把卧室加湿器关掉。

本轮输入
intent：{{intent}}
task：{{task}}
可用显示名：{{display_names}}
当前时间（仅供理解，不要写进用户话）：{{base_time}}
```

### 2.4 D2-2 输出

```text
user_request = "40 分钟后帮我把卧室加湿器关掉。"
```

### 2.5 D0 模板：D3_review_TC6B.md（审查提示词全文）

```text
功能
审查 TC6B 的用户话：必要信息说全没有、有没有泄露绝对时刻。
分两段：先程序扫描，再模型审查。

程序扫描（命中任一 → HARD_LEAKAGE，不用调模型）
  出现 "YYYY-MM-DD HH:MM" 或 "HH:MM:SS" 标准时刻
  出现 device_id / room_id / 动作名（turn_on / turn_off / set_* 等）/ 工具名
  出现 reason_code / OUT_OF_SAFE_RANGE / READ_ONLY_DEVICE
  出现 JSON 片段 {"name":...} / {"arguments":...} / {"device_id":...}

模型审查（只回答 accept 与 codes）
  TARGET_NOT_COVERED  没说到该做的事，或没给出相对时间说法
  EXTRA_INTENT        多说了任务之外的设备或动作
  HARD_LEAKAGE        字面泄露（含绝对时刻）

判例
  用户话 "40 分钟后把加湿器关掉" + task（40 分钟后关加湿器）→ accept
  用户话 "10:10 关加湿器"（说出绝对时刻）→ HARD_LEAKAGE
  用户话 "把空调关掉"（没给时间说法）→ TARGET_NOT_COVERED
  用户话 "40 分钟后关加湿器，顺便开空调"（task 没有空调）→ EXTRA_INTENT

本轮输入
intent：{{intent}}
task：{{task}}
user_request：{{user_request}}
房间名：{{room_names}}
设备名：{{device_names}}
```

### 2.6 D3 审查结果

```text
程序扫描：无命中
模型审查：{"accept": true, "codes": []}
结论：进入 D4
```

### 2.7 D4 Oracle（不调模型）

```text
输入      task + s0 + base_time
步骤
  1  静态检查：due_steps / due_conditions 引用的 device_id / field / action / params
     在 s0 中合法；time_mention 是相对说法；offset_minutes ∈ [5,720]
  2  程序核对：at_time_expected = base_time + offset_minutes（分钟级），
     晚于 base_time 且 ≤ base_time + 10080 分钟
  3  本地试答：instant_conditions 固定为空 → 恒过（保留结构）
  4  影子试答：copy s0 → 应用 due_steps → 影子终态满足 due_conditions
     （不执行 due_steps 序列；自洽性由轨迹端把关）
输出
  {"oracle_ok": true,
   "shadow_state_diff": {"device_bedroom_humidifier": {"on": {"from": true, "to": false}}},
   "reason": "offset/at 合法、本地/到点两段试答通过"}
```

### 2.8 C 与 A 交互（D5 跑轨迹；结束时 C 自动打标签）

```text
A 提示词 = 老 A_policy.md + TC6B 附加段（相对时间调度）

TC6B 附加段内容
  1  先调 inspect_time 读当前时间；时间整局不变
  2  把用户话里的相对说法换算成绝对时刻：at = now + 偏移（分钟级；跨午夜要算日期）
  3  用 time_control.schedule 写单：at = 绝对时刻，steps = 要做的事
  4  schedule 成功后 finish completed，summary 说明已预约哪个时刻做什么
  5  偏移超范围 / 算不出的时间说法 → 说明原因后 refused（reason_code 按契约）
  6  不要自己执行这些动作（现在不做，只写单）
  7  全部 8 个工具都能用；无关工具不要乱调
```

```text
交互循环（C 调度 A 与 B；一次 C.run 完成一局）
  每轮 C 把 context 交给 A；A 输出一个工具调用或 finish；家庭工具走 B.step；
  finish 由 C 收下并结束；一轮最多 1 个工具；跑满 12 轮未 finish → truncated
```

```text
D5 落盘的 record（与现有批次同构；observation = B 的观测视图，落盘时已展开）

{
  "scenario_id": "sc_TC6B_0001",
  "turns": [
    {"turn": 1,
     "tool_calls": [{"name": "inspect_time", "arguments": {}, "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "inspect_time", "arguments": {},
                 "result": {"ok": true,
                            "data": {"now": "2026-10-10 09:30", "clock": "virtual"},
                            "error": null},
                 "state_diff": {}}]},
    {"turn": 2,
     "tool_calls": [{"name": "time_control",
                     "arguments": {"op": "schedule", "at": "2026-10-10 10:10",
                                   "steps": [{"device_id": "device_bedroom_humidifier",
                                              "action": "turn_off", "params": {}}]},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "time_control",
                 "arguments": {"op": "schedule", "at": "2026-10-10 10:10",
                               "steps": [{"device_id": "device_bedroom_humidifier",
                                          "action": "turn_off", "params": {}}]},
                 "result": {"ok": true,
                            "data": {"schedule_id": "sch_01", "at": "2026-10-10 10:10",
                                     "status": "pending"},
                            "error": null},
                 "state_diff": {}}]},
    {"turn": 3,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "已经预约 10:10 关闭卧室加湿器。"},
                     "call_id": "turn_3_0"}],
     "events": [{"call_id": "turn_3_0", "tool_name": "finish",
                 "arguments": {"outcome": "completed",
                               "summary": "已经预约 10:10 关闭卧室加湿器。"},
                 "result": {"ok": true, "data": {"outcome": "completed",
                            "summary": "已经预约 10:10 关闭卧室加湿器。"}, "error": null},
                 "state_diff": {}}]}
  ],
  "final_state": {"device_bedroom_humidifier": {"on": true},
                  "...": "其余设备状态原样"},
  "finish": {"summary": "已经预约 10:10 关闭卧室加湿器。", "outcome": "completed"},
  "protocol": {"terminated": true, "truncated": false,
               "finish_requested": true, "turn_count": 3}
}

record 里新增可选块（仅 TC 任务）：
{"tc_trace": {"clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
              "schedules": [{"schedule_id": "sch_01", "at": "2026-10-10 10:10"}],
              "shadow_result": {"device_bedroom_humidifier": {"on": {"from": true, "to": false}}}}}
```

```text
交互一结束（同一次 C.run 调用内），C 自动打标签（不调模型）。
旧四件套沿用，TC6B 新增的按序追加在 C-4 之后：

C-1 协议        finish_requested 为真 且 未 truncated 且 没有一轮多工具（TOO_MANY_TOOL_CALLS）
C-2 终态        两个分支：即时（空 → 恒过）；定时终态（本任务走这一支）=
                影子执行（新的 s0 + 模型 steps）终态满足 due_conditions
C-3 必需调用     required_calls = [{"tool":"inspect_time"}] → 轨迹里必须有成功的 inspect_time
C-4 finish      outcome 与 expected_finish.outcome 对齐；refused 的 reason_code 必须落在
                allowed_reason_codes 里；出现 facts 失败；completed 带 reason_code 失败
C-5 下单（本任务独有分支）  预约单建立 且 at 与 at_time_expected 分钟级相等（place_ok）
                且 没有"该写单却直接执行"（time_error = false）
                · 明细：place_ok、time_error；steps_ok 仅记录、不挡 C-5（结果导向）

同行落盘：{"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true,
          "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false}
```

### 2.9 D6（TC6B：不做大模型复判 → 跳过）

```text
TC6B 不进 D6 语义复核——和 TC6A 同理，让大模型审这条轨迹没有必要：
  · at 换算对不对 → C-5 的 place_ok（分钟级相等）+ C-2 的定时终态，全是规则
  · 读没读时钟   → C-3 的 required_calls（成功 inspect_time）
  · summary 语义 → 不在管线内校验（C-4 只看 outcome / reason_code / facts）
该行直接记 d6="跳过"、d6_votes=[]，不发任何模型请求。
```

### 2.10 进数据集

```json
{
  "scenario": {
    "scenario_id": "sc_TC6B_0001",
    "blueprint_id": "bp_TC6B_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "40 分钟后帮我把卧室加湿器关掉。",
    "task": {
      "base_task": {"intent": "40 分钟后关掉卧室加湿器",
                    "instant_conditions": [], "keep": [], "required_calls": [],
                    "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
      "time_task": {"time_mention": "40分钟后", "offset_minutes": 40,
                    "at_time_expected": "2026-10-10 10:10",
                    "due_steps": [{"device_id": "device_bedroom_humidifier",
                                   "action": "turn_off", "params": {}}],
                    "due_conditions": [{"device_id": "device_bedroom_humidifier",
                                        "field": "on", "operator": "eq", "value": false}]},
      "memory_task": {}
    },
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"horizon_minutes": 10080, "session_turns": 0}
  },
  "record": {"...": "见 2.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true,
             "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false},
  "category": "TC6B",
  "d6": "跳过",
  "d6_votes": []
}
```

```text
TC6B 进集口径：C-1~C-5 全 true（C-5 已含 place_ok 与 time_error=false；
steps_ok 仅记录）+ d6="跳过" → 复制进数据集
```

## 3 TC7B 完整管线

### 3.1 D0 模板：TC7B_task.md（出题提示词全文）

```text
功能
你是数据辅助生成器。根据本轮 s0 与画像，写一份 TC7B（单轮读写记忆）的隐藏 task JSON。
只输出一个 JSON 对象，不要写用户话，不要解释。

TC7B 是什么
本局开局记忆为空。用户会在一句话里同时给两件事：
  ① 一件"要记住"的偏好或精确数值（"记住：睡觉空调 25.5 度"）；
  ② 一件"现在就做"的动作（"顺便把客厅灯关掉"）。
助手要把①写进记忆、把②做掉，不能把两者混淆。

输出字段（task 三块；intent 与 expected_finish 必填、不能为空）
{"base_task": {"intent":"一句话目标",
               "instant_conditions":[{"device_id":"...","field":"...",
                                      "operator":"eq","value":...}],
               "keep":[], "required_calls":[{"tool":"memory","op":"write"}],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {},
 "memory_task": {"memory_initial":"",
                 "memory_expected":"要记住的内容（一句话）",
                 "forbidden_actions":[],
                 "turns":[]}}

硬规则
  memory_initial 固定为空字符串（开局记忆置空）
  memory_expected ≤200 token，是"可整段替换写入"的偏好/精确值，不能是"现在就做某个动作"
  memory_expected 必须与本轮 s0 吻合（例：家里没有空调就不能写"空调 25.5 度"）
  base_task.instant_conditions 写"现在就做"那个动作的终态；正面约束都写这里
  required_calls 固定含 {"tool":"memory","op":"write"}（必须写入过记忆）
  forbidden_actions 0~2 条（没有禁令就写空数组）；写的话必须是 s0 里真实存在设备的动作
  time_task 固定为 {}（TC7B 不用时间调度）
  注意：task JSON 里不写类别；蓝图顶层写 category（如 TC7B）

小例子
对  memory_expected="睡觉时空调设 25.5 度、制冷"（家里有空调）
    instant_conditions=[{"device_id":"device_living_light","field":"on",
                         "operator":"eq","value":false}]
错  memory_expected="把客厅灯关掉"（这是动作，不是要记住的偏好）
错  s0 里没有空调却写"空调 25.5 度"

完整例子
本轮画像：{"persona_id":"p21","name":"李岚","age":29,"habits":"花粉过敏，晚上容易鼻塞"}
本轮 s0：{"rooms":[{"room_id":"room_bedroom","device_ids":["device_bedroom_climate"]},
          {"room_id":"room_living","device_ids":["device_living_light"]}], "devices":[...]}
正确输出：
{"base_task": {"intent":"记住睡觉空调 25.5 度制冷，并关掉客厅主灯",
               "instant_conditions":[{"device_id":"device_living_light","field":"on",
                                      "operator":"eq","value":false}],
               "keep":[], "required_calls":[{"tool":"memory","op":"write"}],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {},
 "memory_task": {"memory_initial":"",
                 "memory_expected":"睡觉时空调设 25.5 度、制冷",
                 "forbidden_actions":[],
                 "turns":[]}}

不要照抄例子；本轮按 {{s0}} 与 {{persona}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 3.2 D2-1 输出（TC7B task）

```json
{"base_task": {"intent": "记住睡觉空调 25.5 度制冷，并关掉客厅主灯",
               "instant_conditions": [{"device_id": "device_living_light", "field": "on",
                                       "operator": "eq", "value": false}],
               "keep": [], "required_calls": [{"tool": "memory", "op": "write"}],
               "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
 "time_task": {},
 "memory_task": {"memory_initial": "",
                 "memory_expected": "睡觉时空调设 25.5 度、制冷",
                 "forbidden_actions": [],
                 "turns": []}}
```

```text
memory_initial 固定空串；D5 组装时搬到 scenario.world.memory_initial（空串）；
"要记住的内容"只写在 task.memory_task.memory_expected（判定真值）
```

### 3.3 D0 模板：D0_request_TC7B.md（写用户话提示词全文）

```text
功能
把 TC7B 的 task 写成一句自然的用户请求。
请求必须同时包含两件事：
  ① "要记住"的偏好或精确数值（用"记住：…"或等价说法，数值要原样说出）；
  ② "现在就做"的动作。
两件事缺一不可；数值是用户主动告知的内容，允许出现在请求里。

规则
  偏好句用口语："记住：""以后""睡觉时""我习惯"
  精确数值必须出现在请求里
  禁止出现 device_id / room_id / 动作名 / 参数名 / 工具名
  禁止把"要记住的内容"说成"现在就做"的动作
  只说这一句话，不要解释

小例子
对  memory_expected="睡觉时空调设 25.5 度、制冷" + 动作关客厅灯
    → "记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。"
错  "记住睡觉的空调习惯。"（数值丢了）
错  "把客厅主灯关掉。"（没有要记住的内容）
错  "记住：把客厅主灯关掉。"（把动作说成要记住的内容）

完整例子
intent：记住睡觉空调 25.5 度制冷，并关掉客厅主灯
task：{"base_task":{"intent":"记住睡觉空调 25.5 度制冷，并关掉客厅主灯",
                    "instant_conditions":[{"device_id":"device_living_light","field":"on",
                                           "operator":"eq","value":false}],
                    "keep":[],"required_calls":[{"tool":"memory","op":"write"}],
                    "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
       "time_task":{},
       "memory_task":{"memory_initial":"",
                      "memory_expected":"睡觉时空调设 25.5 度、制冷",
                      "forbidden_actions":[],"turns":[]}}
可用显示名：客厅主灯、卧室空调
正确输出：记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。

本轮输入
intent：{{intent}}
task：{{task}}
可用显示名：{{display_names}}
```

### 3.4 D2-2 输出

```text
user_request = "记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。"
```

### 3.5 D0 模板：D3_review_TC7B.md（审查提示词全文）

```text
功能
审查 TC7B 的用户话：两件事是否都说清、有没有泄露 id/动作名、有没有把两件事混淆。

程序扫描（命中任一 → HARD_LEAKAGE）
  动作名 / 工具名 / device_id / room_id / JSON 片段
  （数值本身允许出现——那是要记住的内容）

模型审查（只回答 accept 与 codes）
  TARGET_NOT_COVERED  缺少"要记住的偏好/数值"，或缺少"现在就做的动作"
  EXTRA_INTENT        多说了任务之外的设备或动作
  HARD_LEAKAGE        字面泄露

判例
  "记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。" → accept
  "记住睡觉的空调习惯。"（丢了数值）→ TARGET_NOT_COVERED
  "把客厅主灯关掉。"（没有要记住的内容）→ TARGET_NOT_COVERED
  "记住：把客厅主灯关掉。"（把动作说成要记住的内容）→ TARGET_NOT_COVERED
  "把 device_living_light 关掉。" → HARD_LEAKAGE

本轮输入
intent：{{intent}}
task：{{task}}
user_request：{{user_request}}
房间名：{{room_names}}
设备名：{{device_names}}
```

### 3.6 D3 审查结果

```text
程序扫描：无命中
模型审查：{"accept": true, "codes": []}
结论：进入 D4
```

### 3.7 D4 Oracle（不调模型）

```text
输入      task + s0
步骤
  1  一致性：memory_expected 提到的设备/能力/数值必须与 s0 吻合；
     memory_initial 必须是空串（开局置空）
  2  可行性：base_task.instant_conditions 对应的动作在 s0 中合法
  3  本地试答（老 D4 同一套）：copy s0 → instant_conditions 逐条反推写动作
     （turn_off 客厅主灯）→ 在副本上试打，必须被 B 接受
  4  记忆侧只做静态检查（memory.write 无世界副作用；写入行为由 D5 轨迹验证）
输出
  {"oracle_ok": true, "shadow_state_diff":
   {"device_living_light": {"on": {"from": true, "to": false}}},
   "reason": "记忆与 s0 一致；本地试答通过"}
```

### 3.8 C 与 A 交互（D5 跑轨迹；结束时 C 自动打标签）

```text
A 提示词 = 老 A_policy.md + TC7B 附加段（记忆写入）

TC7B 附加段内容
  1  判断请求里有没有"要记住"的偏好或精确值——触发条件是内容本身（出现偏好、习惯、
     固定数值，如"记住：…""我睡觉时…""我习惯…"），不依赖"记住"两个字
  2  有 → 先 memory.write 整段写入这条偏好（整段替换，不超 200 token）
  3  再做"现在就做"的动作（inspect → execute）；不要把"要记住的"当成本回合动作执行
  4  finish completed，summary 说明"记住了什么 + 做了什么"
  5  全部 8 个工具都能用；无关工具不要乱调
```

```text
D5 落盘的 record（与现有批次同构）

{
  "scenario_id": "sc_TC7B_0001",
  "turns": [
    {"turn": 1,
     "tool_calls": [{"name": "memory",
                     "arguments": {"op": "write", "text": "睡觉时空调设 25.5 度、制冷"},
                     "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "memory",
                 "arguments": {"op": "write", "text": "睡觉时空调设 25.5 度、制冷"},
                 "result": {"ok": true, "data": {"code": "OK"}, "error": null},
                 "state_diff": {}}]},
    {"turn": 2,
     "tool_calls": [{"name": "inspect_device",
                     "arguments": {"device_id": "device_living_light"},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "inspect_device",
                 "arguments": {"device_id": "device_living_light"},
                 "result": {"ok": true,
                            "data": {"device": {"device_id": "device_living_light",
                                                "display_name": "客厅主灯", "kind": "actuator",
                                                "device_type": "light",
                                                "state": {"on": true, "mode": "bright"},
                                                "actions": ["..."]}},
                            "error": null},
                 "state_diff": {}}]},
    {"turn": 3,
     "tool_calls": [{"name": "execute_action",
                     "arguments": {"device_id": "device_living_light",
                                   "action": "turn_off", "params": {}},
                     "call_id": "turn_3_0"}],
     "events": [{"call_id": "turn_3_0", "tool_name": "execute_action",
                 "arguments": {"device_id": "device_living_light",
                               "action": "turn_off", "params": {}},
                 "result": {"ok": true,
                            "data": {"device_id": "device_living_light",
                                     "action": "turn_off",
                                     "state_after": {"on": false, "mode": "bright"},
                                     "verified": true, "changed": true},
                            "error": null},
                 "state_diff": {"on": {"from": true, "to": false}}}]},
    {"turn": 4,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "已经记住睡觉空调 25.5 度制冷；也把客厅主灯关掉了。"},
                     "call_id": "turn_4_0"}],
     "events": [{"call_id": "turn_4_0", "tool_name": "finish",
                 "arguments": {"outcome": "completed",
                               "summary": "已经记住睡觉空调 25.5 度制冷；也把客厅主灯关掉了。"},
                 "result": {"ok": true, "data": {"outcome": "completed",
                            "summary": "已经记住睡觉空调 25.5 度制冷；也把客厅主灯关掉了。"},
                            "error": null},
                 "state_diff": {}}]}
  ],
  "final_state": {"device_living_light": {"on": false, "mode": "bright"},
                  "...": "其余设备状态原样"},
  "finish": {"summary": "已经记住睡觉空调 25.5 度制冷；也把客厅主灯关掉了。",
             "outcome": "completed"},
  "protocol": {"terminated": true, "truncated": false,
               "finish_requested": true, "turn_count": 4}
}

record 里新增可选块（仅 TC 任务）：
{"tc_trace": {"clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
              "memory_before": "",
              "memory_after": "睡觉时空调设 25.5 度、制冷",
              "schedules": []}}
```

```text
交互一结束（同一次 C.run 调用内），C 自动打标签（不调模型）：

C-1 协议        finish_requested 为真 且 未 truncated 且 没有一轮多工具
C-2 终态        两个分支：即时终态（本任务走这一支）——final_state 满足
                instant_conditions + keep（空数组过）；定时分支不用
C-3 必需调用     required_calls = [{"tool":"memory","op":"write"}] → 必须有成功的 memory.write
C-4 finish      outcome 与 expected_finish.outcome 对齐；refused 的 reason_code 必须落在
                allowed_reason_codes 里；出现 facts 失败；completed 带 reason_code 失败
C-5 记忆写入（本任务独有分支）= required_calls 里 write 条目的检查结果（存在成功 write），
                与 C-3 同一份数据、单独汇报；写入内容是否正确归 D6（见 3.9/3.10）

（TC7B 与 TC7A 的关键差别：TC7B 保留 D6 记忆审查——写的内容对不对、有没有误用，
  是自然语言语义判断，规则替代不了；TC7A 只读预置记忆，已确认全规则化。）
```

### 3.9 D0 模板：D6_TC7B.md（记忆审查提示词全文）

```text
功能
复核 TC7B 轨迹：记忆写得对不对、有没有把"要记住的"误当动作、summary 是否如实。
只看工具调用、记忆快照与状态变化，不采信 summary 自述。

输入
  task：memory_task.memory_expected / memory_initial / forbidden_actions +
        base_task.instant_conditions
  轨迹：turns + memory_before / memory_after 快照 + state_diff + finish summary

输出（一票）
  {"write_ok": true/false, "comply_ok": true/false, "summary_ok": true/false, "reason": "..."}

判定规则
  write_ok    轨迹里有成功的 memory.write，且写入内容与 memory_expected 语义一致
              （同义改写算过；数值/设备/方向任何一处写错算不过）
  comply_ok   没有把"要记住的"当成动作执行；forbidden_actions 没出现；
              base_task.instant_conditions 达成（与 C-2 对照，语义再确认）
  summary_ok  summary 与实际动作/记忆内容一致，没有编造

判例
  写对 + 关灯做对 + summary 如实 → 三个 true
  没写记忆（只关了灯）→ write_ok=false
  写错数值（25.5 写成 26）→ write_ok=false
  把"记住睡觉要关灯"当场执行成"现在关灯"→ comply_ok=false
  summary 说"已记住"但轨迹里没有 write → summary_ok=false
```

### 3.10 D6 三票与进数据集

```text
TC7B 保留 D6 三票（这是与 TC6A/TC7A 的关键差别）：

① 读标签：本行 C-1~C-5 全 true 才继续；否则原样返回，不发起复核
② 三票复核（D6_TC7B，role=external，三次互相独立）
   每票给 write_ok / comply_ok / summary_ok + reason；
   该票 verdict = 三项全 true ? "对" : "错"
   d6 = 三票多数决；有效票不足 3 → d6="system_failure"（要重跑，不判错）
   逐项标签（write_ok / comply_ok / summary_ok）按多数票汇总落盘
③ 进集：C-1~C-5 全 true 且 write_ok / comply_ok / summary_ok 全 true 且 d6="对"
```

```json
{
  "scenario": {
    "scenario_id": "sc_TC7B_0001",
    "blueprint_id": "bp_TC7B_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "记住：我睡觉时空调要 25.5 度、制冷；顺便把客厅主灯关掉。",
    "task": {
      "base_task": {"intent": "记住睡觉空调 25.5 度制冷，并关掉客厅主灯",
                    "instant_conditions": [{"device_id": "device_living_light",
                                            "field": "on", "operator": "eq", "value": false}],
                    "keep": [], "required_calls": [{"tool": "memory", "op": "write"}],
                    "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
      "time_task": {},
      "memory_task": {"memory_initial": "",
                      "memory_expected": "睡觉时空调设 25.5 度、制冷",
                      "forbidden_actions": [],
                      "turns": []}
    },
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"horizon_minutes": 10080, "memory_initial": "", "session_turns": 0}
  },
  "record": {"...": "见 3.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true,
             "write_ok": true, "comply_ok": true, "summary_ok": true},
  "category": "TC7B",
  "d6": "对",
  "d6_votes": ["对", "对", "对"]
}
```

```text
说明：蓝图里 memory_initial 在 task.memory_task；D5 组装 scenario 时
移动到 world.memory_initial（TC7B 为空串，上面已是搬运后的运行时视图）。
```

## 4 两条管线的涉及文件清单

```text
目录 new_demo/data_static/D0_templates_tc/
  TC6B_task.md          出题提示词（2.1）
  D0_request_TC6B.md    写用户话提示词（2.3）
  D3_review_TC6B.md     审查提示词（2.5）
  TC7B_task.md          出题提示词（3.1）
  D0_request_TC7B.md    写用户话提示词（3.3）
  D3_review_TC7B.md     审查提示词（3.5）
  D6_TC7B.md            记忆审查提示词（3.9）
  A_policy_tc_sections.md  A 提示词附加段（相对时间调度 + 记忆写入）

代码 new_demo/data_tc/（沿用 05 的 8 件套，按子类加分支与提示词映射）
  TC0_template / TC2_task_writer / TC2_request_writer / TC3_reviewer /
  TC4_oracle / TC5_run / TC6_judge / TC_PIPE_pipeline

产物
  data_raw_tc/、data_processed_tc/TC_dataset.jsonl、TC_trajectories.jsonl、TC_manifest.json
  评测集 eval_sets/TC_20261010_v1/（TC6B / TC7B 各先 30 条起步）
```

## 5 待确认点

```text
1  TC6B 的 required_calls = [{"tool":"inspect_time"}] 是否启用；
   若启用，05 的 TC6A 也应补同一条（现在为空）——两边要一致
2  at_time_expected 改为"程序按 base_time + offset 补算"（旧 03 写"出题模型写"）——确认
3  offset 范围 5~720 分钟、允许跨午夜（与 02/03 一致）——确认
4  TC7B 的记忆触发：按"内容里有偏好/精确数值"触发（不依赖"记住"二字）——确认
5  TC7B 的写入正确性判定：D6 语义（同义改写算过），不做字符串相等——确认
6  TC7B 的 request 必须包含数值（与 TC7A 相反）——D3 按此审——确认
7  memory_initial 固定空串 vs 省略字段：现在写空串——确认
8  TC7B 的 C-5 记忆写入切片是否保留（或并入 C-3 不再单列）——待定
9  D6_TC7B 的 d6 口径：每票"三项全 true 才算对"，三票多数决——确认
10 时间类拒绝（TC6B 的越界 / 模糊表述负例）的 finish reason_code 仍未定义（同 05 §5 第 15 条）
```
