# 05 完整管线示例：TC6A 绝对时间 与 TC7A 读预置记忆

> 依据：`04_新增字段归属分析` 的字段清单与推荐方案 4（存储一体化 + 运行时按消费者拆分）。
> 名词按 2026-10-10 定稿：time_mention、at_time_expected、offset_minutes、due_steps、due_state、
> memory_initial、memory_expected、forbidden_actions、required_effects、required_calls（待审）、
> session_turns、turns[]、kind、tc_schema。
> 本文只走两类：TC6A（绝对时间一次性预约）与 TC7A（读预置记忆），从提示词到轨迹到数据集完整呈现。

## 0 一屏

```text
管线主链（两类共用，只有提示词与判定不同）

  D0 模板（TC6A / TC7A 各自的 task / request / review / judge 提示词）
        ↓
  D1 造家 + 抽样（户型、设备、画像、base_time；记忆按场景生成）
        ↓
  D2-1 写 task（外部模型；隐藏真值）
        ↓
  D2-2 写用户话（外部模型；只写用户那句话）
        ↓
  D3 审用户话（程序扫描 + 模型审查；防泄露/漏说）
        ↓
  D4 Oracle（不调模型：写单/影子执行/记忆一致性校验）
        ↓
  D5 跑轨迹（A 提示词 = 老 A_policy + TC 附加段；C 收集 turns）
        ↓
  D6 复核（TC6A 走规则判定；TC7A 走 D6 语义复核）
        ↓
  TC_dataset.jsonl（存 tc 块 + 轨迹 + 标签）
```

```text
两份示例的固定输入（下面所有阶段都围绕它们展开）

  base_time = 2026-10-10 09:30
  家：客厅主灯 device_living_light、卧室空调 device_bedroom_climate、
      卧室空气净化器 device_bedroom_purifier、卧室加湿器 device_bedroom_humidifier
  画像：p21，花粉过敏，晚上容易鼻塞

  TC6A  用户话："今晚10点帮我把客厅灯关掉"
  TC7A  用户话："卧室有点闷"（记忆里预置"对花粉过敏，别开窗"）
```

## 1 公共部分（两类共用）

### 1.1 D1 抽样与生成

```text
抽样   户型（D0_homes）、设备（D0_devices）、画像（D0_personas）
抽样   时间 base_time：从时间池抽（早上/下午/晚上/深夜、工作日/周末）
生成   记忆 memory_initial（仅 TC7A）：由 D2 依据本轮 s0 与画像生成，不抽样拼装
约束   同一任务只冻结一个 base_time；记忆必须与 s0 吻合
```

### 1.2 存储结构与运行时结构（方案 4）

```json
// D 的一条记录（存储视图）：新字段统一放在 tc 块里
{
  "scenario_id": "sc_TCxA_0001",
  "blueprint_id": "bp_TCxA_0001",
  "home": { "...": "..." },
  "user_request": "（D2-2 写出来后填这里）",
  "task": { "intent": "...", "conditions": [], "keep": [],
            "required_observations": [], "expected_finish": {} },
  "episode_config": { "max_turns": 12, "max_tool_calls_per_turn": 1 },
  "tc": {
    "tc_schema": "v1",
    "kind": "TC6A",
    "base_time": "2026-10-10 09:30",
    "horizon_minutes": 10080,
    "time_mention": "今晚10点",
    "at_time_expected": "2026-10-10 22:00",
    "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
    "memory_initial": "",
    "memory_expected": "",
    "forbidden_actions": [],
    "required_effects": [],
    "required_calls": [],
    "session_turns": 0,
    "turns": [],
    "due_state": null
  }
}
```

```text
运行时展开（D5 做的事）
  task            ← 判定真值：at_time_expected / due_steps / memory_expected /
                    forbidden_actions / required_effects / required_calls
  scenario.world  ← base_time / memory_initial / session_turns / due_state / horizon_minutes
  蓝图（不传 B）  ← kind / tc_schema / time_mention / offset_minutes
  轨迹（D5 写）   ← session_id / turn_index / clock / memory_before/after / schedules
```

### 1.3 A 提示词装配（不改老提示词）

```text
TC 的 A 提示词 = 老 A_policy.md + TC 附加段
  工具表：全部 8 个（observe_home / inspect_room / inspect_device / execute_action /
          finish / inspect_time / time_control / memory）
  TC6A 附加段：时间调度规则（见 2.7）
  TC7A 附加段：记忆规则（见 3.7）
```

## 2 TC6A 完整管线

### 2.1 D0 模板：TC6A_task.md（出题提示词全文）

```text
功能
你是数据辅助生成器。根据本轮 s0、画像与 base_time，写一份 TC6A（绝对时间一次性预约）的隐藏 task JSON。
只输出一个 JSON 对象，不要写用户话，不要解释。

TC6A 是什么
用户会在话里说出一个绝对时间点（今晚10点、明早7点、18点半等），
助手要把它换算成标准时刻，并写一张一次性预约单。
本局时间冻结：base_time 就是"现在"，不会流逝。

输出字段
{"kind":"TC6A", "intent":"一句话目标",
 "time_mention":"用户话里的时间说法",
 "at_time_expected":"YYYY-MM-DD HH:MM",
 "due_steps":[{"device_id":"...","action":"...","params":{}}],
 "conditions":[{"device_id":"...","field":"...","operator":"eq","value":...}],
 "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

硬规则
  at_time_expected 必须晚于 base_time，且在 7 天（10080 分钟）以内，分钟级
  due_steps 1~3 条，设备与动作只能来自本轮 s0
  time_mention 不能是"每晚/每天"这类持久规则；出现直接判废
  time_mention 不能直接写标准时刻（那是答案，不是题面说法）
  conditions 描述"到点执行后终态应满足什么"

小例子（base_time = 2026-10-10 09:30）
对  time_mention="今晚10点" → at_time_expected="2026-10-10 22:00"
对  time_mention="明早7点"  → at_time_expected="2026-10-11 07:00"
错  at_time_expected="2026-10-10 09:00"（过去）
错  time_mention="每晚10点"（持久规则，不属 TC6A）
错  due_steps 里写 s0 没有的设备

完整例子
本轮画像：{"persona_id":"p21","name":"李岚","age":29,"habits":"花粉过敏，晚上容易鼻塞"}
本轮 s0：{"rooms":[{"room_id":"room_living","device_ids":["device_living_light"]},
          {"room_id":"room_bedroom","device_ids":["device_bedroom_climate",
           "device_bedroom_purifier","device_bedroom_humidifier"]}], "devices":[...]}
本轮 base_time："2026-10-10 09:30"
正确输出：
{"kind":"TC6A","intent":"今晚睡前把客厅灯关掉",
 "time_mention":"今晚10点","at_time_expected":"2026-10-10 22:00",
 "due_steps":[{"device_id":"device_living_light","action":"turn_off","params":{}}],
 "conditions":[{"device_id":"device_living_light","field":"on","operator":"eq","value":false}],
 "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子里的设备与数值；本轮按 {{s0}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 2.2 D2-1 输出（TC6A 的真实 task）

```json
{"kind": "TC6A",
 "intent": "今晚睡前把客厅灯关掉",
 "time_mention": "今晚10点",
 "at_time_expected": "2026-10-10 22:00",
 "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
 "conditions": [{"device_id": "device_living_light", "field": "on",
                 "operator": "eq", "value": false}],
 "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}}
```

### 2.3 D0 模板：D0_request_TC6A.md（写用户话提示词全文）

```text
功能
把 TC6A 的 task 写成一句自然的用户请求。
请求里必须包含 time_mention 这个时间说法，但不能出现标准时刻、device_id、动作名、工具名。

规则
  时间说法用口语："今晚10点""明早7点""18点半"
  禁止出现 "YYYY-MM-DD HH:MM" 形式的标准时刻
  禁止出现 device_id / room_id / 动作名 / 参数名 / 工具名
  可以加一句生活化铺垫，但不要引入第二个任务
  只说这一句话，不要解释

小例子
对  time_mention="今晚10点" → "今晚10点记得把客厅灯关掉。"
对  time_mention="明早7点"  → "明早7点帮我把卧室空调打开。"
错  "今晚 22:00 把客厅灯关掉"（泄露标准时刻）
错  "把 device_living_light 关掉"（泄露 id）

完整例子
intent：今晚睡前把客厅灯关掉
task：{"kind":"TC6A","time_mention":"今晚10点","at_time_expected":"2026-10-10 22:00",
      "due_steps":[{"device_id":"device_living_light","action":"turn_off","params":{}}]}
可用显示名：客厅主灯、卧室空调、卧室空气净化器、卧室加湿器
正确输出：今晚10点帮我把客厅灯关掉吧。

本轮输入
intent：{{intent}}
task：{{task}}
可用显示名：{{display_names}}
当前时间（仅供理解，不要写进用户话）：{{base_time}}
```

### 2.4 D2-2 输出

```text
user_request = "今晚10点帮我把客厅灯关掉吧。"
```

### 2.5 D0 模板：D3_review_TC6A.md（审查提示词全文）

```text
功能
审查 TC6A 的用户话：必要信息说全没有、有没有泄露答案。
分两段：先程序扫描，再模型审查。

程序扫描（命中任一 → HARD_LEAKAGE，不用调模型）
  出现 "YYYY-MM-DD HH:MM" 或 "HH:MM:SS" 标准时刻
  出现 device_id / room_id / 动作名（turn_on / turn_off / set_* 等）/ 工具名
  出现 reason_code / OUT_OF_SAFE_RANGE / READ_ONLY_DEVICE
  出现 JSON 片段 {"name":...} / {"arguments":...} / {"device_id":...}

模型审查（只回答 accept 与 codes）
  TARGET_NOT_COVERED  没说到该做的事，或没给出该换算的时间说法
  EXTRA_INTENT        多说了任务之外的设备或动作
  HARD_LEAKAGE        字面泄露

判例
  用户话 "今晚10点帮我把客厅灯关掉" + task 关客厅灯 → accept
  用户话 "40分钟后把灯关掉"（task 是今晚10点）→ TARGET_NOT_COVERED
  用户话 "今晚10点关灯，顺便把空调也开开"（task 没有空调）→ EXTRA_INTENT
  用户话 "今晚 22:00 关灯" → HARD_LEAKAGE（标准时刻）

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
  1  静态检查：due_steps 里的 device_id / action / params 在 s0 中合法
  2  时间检查：at_time_expected 晚于 base_time 且 ≤ base_time + 10080 分钟
  3  影子执行：copy s0 → 应用 due_steps → 得到"到点后的状态"
  4  结果比对：影子状态满足 conditions
输出
  {"oracle_ok": true,
   "shadow_state_diff": {"device_living_light": {"on": {"from": true, "to": false}}},
   "reason": "at 合法、steps 合法、影子执行满足 conditions"}
```

### 2.8 D5 跑轨迹（A 提示词 + 轨迹）

```text
A 提示词 = 老 A_policy.md + TC6A 附加段（时间调度）

TC6A 附加段内容
  1  先调 inspect_time 读当前时间；时间整局不变
  2  把用户话里的时间说法换算成标准时刻 YYYY-MM-DD HH:MM
  3  用 time_control.schedule 写单：at = 标准时刻，steps = 要做的事
  4  schedule 成功后 finish completed，summary 说明已预约几点做什么
  5  过去时间 / 超过 7 天 / 模糊时间 → 说明原因后 refused（reason_code 按契约）
  6  不要自己执行这些动作（现在不做，只写单）
  7  全部 8 个工具都能用；无关工具不要乱调
```

```text
真实轨迹（turns）
  turn1  A: inspect_time {}
         B: {"now":"2026-10-10 09:30","clock":"virtual"}
  turn2  A: time_control {"op":"schedule","at":"2026-10-10 22:00",
                          "steps":[{"device_id":"device_living_light","action":"turn_off","params":{}}]}
         B: {"schedule_id":"sch_01","at":"2026-10-10 22:00","status":"pending"}
  turn3  A: finish {"outcome":"completed",
                    "summary":"今晚10点关掉客厅灯，已经预约。"}
         C: 收下 finish，episode 结束
```

### 2.9 D6 判定（TC6A 规则判定）

```text
① 下单判定
   at 与 at_time_expected 分钟级相等          → 通过
   steps 与 due_steps 一致（设备/动作/参数）    → 通过
   预约单建立（schedule_id 存在）              → 通过
② 结算判定
   影子执行结果满足 conditions                 → 通过
   （due_state 有值时在快照上跑；掉线不处理）
标签
  {"place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false}
```

### 2.10 进数据集

```json
{"scenario_id": "sc_TC6A_0001", "kind": "TC6A",
 "user_request": "今晚10点帮我把客厅灯关掉吧。",
 "task_truth": {"at_time_expected": "2026-10-10 22:00",
                "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
                "conditions": [{"device_id": "device_living_light", "field": "on",
                                "operator": "eq", "value": false}]},
 "world": {"base_time": "2026-10-10 09:30", "horizon_minutes": 10080},
 "trajectory_ref": "TC_trajectories.jsonl#sc_TC6A_0001",
 "labels": {"place_ok": true, "steps_ok": true, "settle_ok": true}}
```

## 3 TC7A 完整管线

### 3.1 D0 模板：TC7A_task.md（出题提示词全文）

```text
功能
你是数据辅助生成器。根据本轮 s0 与画像，写一份 TC7A（读预置记忆）的隐藏 task JSON。
只输出一个 JSON 对象，不要写用户话，不要解释。

TC7A 是什么
这局的记忆里已经预先写好一段偏好或约束（memory_initial）；
用户请求本身不会复述这段内容，助手要先读记忆，再按记忆约束行动。

输出字段
{"kind":"TC7A", "intent":"一句话目标",
 "memory_initial":"开局记忆里已有的内容",
 "forbidden_actions":["不许做的动作"],
 "required_effects":["必须达成的效果"],
 "conditions":[...],
 "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

硬规则
  memory_initial ≤200 token，必须是"偏好/约束"，不能是"现在就做某个动作"的指令
  memory_initial 必须与本轮 s0 吻合：s0 没有窗户就不能写"别开窗"；
  s0 没有空气净化器就不能写"开净化器"
  memory_initial 与用户请求相关，但请求不能直接复述它
  forbidden_actions 1~2 条，必须是 s0 里真实存在设备的动作
  required_effects 1~2 条，必须是终态可检查的效果

小例子
对  memory_initial="用户对花粉过敏，别开窗；闷了先开空气净化器"
    forbidden_actions=["开窗通风类动作"]
    required_effects=["device_bedroom_purifier on=true"]
错  memory_initial="把客厅灯关掉"（这是动作指令，不是偏好记忆）
错  s0 里没有窗户却写"别开窗"

完整例子
本轮画像：{"persona_id":"p21","name":"李岚","age":29,"habits":"花粉过敏，晚上容易鼻塞"}
本轮 s0：{"rooms":[{"room_id":"room_bedroom","device_ids":["device_bedroom_climate",
          "device_bedroom_purifier","device_bedroom_humidifier"]}], "devices":[...]}
正确输出：
{"kind":"TC7A","intent":"卧室闷，按记忆优先开净化器而不是开窗",
 "memory_initial":"用户对花粉过敏，别开窗；闷了先开空气净化器",
 "forbidden_actions":["开窗通风类动作"],
 "required_effects":["device_bedroom_purifier on=true"],
 "conditions":[{"device_id":"device_bedroom_purifier","field":"on","operator":"eq","value":true}],
 "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}

不要照抄例子；本轮按 {{s0}} 与 {{persona}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 3.2 D2-1 输出（TC7A 的真实 task）

```json
{"kind": "TC7A",
 "intent": "卧室闷，按记忆优先开净化器而不是开窗",
 "memory_initial": "用户对花粉过敏，别开窗；闷了先开空气净化器",
 "forbidden_actions": ["开窗通风类动作"],
 "required_effects": ["device_bedroom_purifier on=true"],
 "conditions": [{"device_id": "device_bedroom_purifier", "field": "on",
                 "operator": "eq", "value": true}],
 "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}}
```

### 3.3 D0 模板：D0_request_TC7A.md（写用户话提示词全文）

```text
功能
把 TC7A 的 task 写成一句自然的用户请求。
请求只说需求，不直接复述 memory_initial；要能自然触发"先读记忆"的需求。

规则
  禁止照抄 memory_initial 的句子或连续 8 个字以上
  禁止出现 device_id / room_id / 动作名 / 工具名 / 标准时刻
  禁止把记忆内容说成"现在就做"的动作
  只说这一句话，不要解释

小例子
对  memory_initial="用户对花粉过敏，别开窗；闷了先开空气净化器"
    → "卧室有点闷。"
对  memory_initial="用户怕冷，睡觉空调不要低于26度"
    → "卧室有点冷。"
错  "卧室有点闷，开净化器别开窗"（直接复述了记忆）
错  "把 device_bedroom_purifier 打开"（泄露 id）

完整例子
intent：卧室闷，按记忆优先开净化器而不是开窗
task：{"kind":"TC7A","memory_initial":"用户对花粉过敏，别开窗；闷了先开空气净化器", ...}
可用显示名：卧室空调、卧室空气净化器、卧室加湿器
正确输出：卧室有点闷，帮我想想办法。

本轮输入
intent：{{intent}}
task：{{task}}
可用显示名：{{display_names}}
```

### 3.4 D2-2 输出

```text
user_request = "卧室有点闷，帮我想想办法。"
```

### 3.5 D0 模板：D3_review_TC7A.md（审查提示词全文）

```text
功能
审查 TC7A 的用户话：有没有漏说需求、有没有泄露记忆内容、有没有多说设备。

程序扫描（命中任一 → HARD_LEAKAGE）
  老规则：动作名 / 工具名 / device_id / room_id / JSON 片段
  记忆照抄：与 memory_initial 有连续 8 个字以上相同 → HARD_LEAKAGE

模型审查（只回答 accept 与 codes）
  TARGET_NOT_COVERED  请求完全没有表达出与记忆相关的需求
  EXTRA_INTENT        多说了任务之外的设备或动作
  HARD_LEAKAGE        字面泄露（含照抄记忆）

判例
  用户话 "卧室有点闷" + 记忆"花粉过敏别开窗" → accept
  用户话 "把净化器打开"（直接说了答案）→ HARD_LEAKAGE
  用户话 "客厅灯太亮了"（与记忆场景无关）→ TARGET_NOT_COVERED

本轮输入
intent：{{intent}}
task：{{task}}
memory_initial：{{memory_initial}}
user_request：{{user_request}}
房间名：{{room_names}}
设备名：{{device_names}}
```

### 3.6 D3 审查结果

```text
程序扫描：无命中（没有照抄记忆、没有动作名）
模型审查：{"accept": true, "codes": []}
结论：进入 D4
```

### 3.7 D4 Oracle（不调模型）

```text
输入      task + s0
步骤
  1  一致性：memory_initial 提到的设备/能力必须在 s0 里存在
  2  可行性：required_effects 对应的动作在 s0 中合法
  3  影子预演：copy s0 → 打开净化器 → 检查 conditions 满足
输出
  {"oracle_ok": true, "shadow_state_diff":
   {"device_bedroom_purifier": {"on": {"from": false, "to": true}}},
   "reason": "记忆与 s0 一致；按记忆行动可达成 required_effects"}
```

### 3.8 D5 跑轨迹（A 提示词 + 轨迹）

```text
A 提示词 = 老 A_policy.md + TC7A 附加段（记忆）

TC7A 附加段内容
  1  先判断请求是否可能依赖已知偏好；TC7A 场景下先调 memory.read
  2  按记忆约束行动：memory 里说不能做的不要做；说优先的优先做
  3  memory 是整段文本，读了直接用，不要改写
  4  行为完成后 finish completed，summary 如实说明做了什么、为什么
  5  全部 8 个工具都能用；无关工具不要乱调
```

```text
真实轨迹（turns）
  turn1  A: memory {"op":"read"}
         B: {"text":"用户对花粉过敏，别开窗；闷了先开空气净化器"}
  turn2  A: inspect_device {"device_id":"device_bedroom_purifier"}
         B: {"state":{"on":false},"actions":[...turn_on...]}
  turn3  A: execute_action {"device_id":"device_bedroom_purifier","action":"turn_on","params":{}}
         B: {"state_after":{"on":true},"state_diff":{"on":{"from":false,"to":true}},"verified":true}
  turn4  A: finish {"outcome":"completed","summary":"卧室闷，按您的习惯开了空气净化器，没有开窗。"}
         C: 收下 finish，episode 结束
```

### 3.9 D0 模板：D6_TC7A.md（语义复核提示词全文）

```text
功能
复核 TC7A 轨迹：记忆读到没有、约束遵守没有、summary 是否与事实一致。
只看工具调用、记忆快照与状态变化，不采信 summary 自述。

输入
  task：memory_initial / forbidden_actions / required_effects / conditions
  轨迹：turns + 工具调用 + state_diff + memory 快照 + finish summary

输出
  {"read_ok": true/false, "comply_ok": true/false, "summary_ok": true/false, "reason": "..."}

判定规则
  read_ok     轨迹里有成功的 memory.read（required_calls 待审；未采用时以轨迹为准）
  comply_ok   禁止动作没出现，required_effects 全部达成
  summary_ok  summary 与实际动作/状态一致，没有编造，没有自述奖励

判例
  读了记忆 + 开净化器 + summary 如实 → 三个 true
  没读记忆 + 碰巧开净化器 → read_ok=false，其余 true
  读了记忆 + 开窗 → comply_ok=false
  summary 说"已关闭空调"但轨迹没有 → summary_ok=false
```

### 3.10 D6 输出与进数据集

```json
{"scenario_id": "sc_TC7A_0001", "kind": "TC7A",
 "user_request": "卧室有点闷，帮我想想办法。",
 "task_truth": {"memory_initial": "用户对花粉过敏，别开窗；闷了先开空气净化器",
                "forbidden_actions": ["开窗通风类动作"],
                "required_effects": ["device_bedroom_purifier on=true"],
                "conditions": [{"device_id": "device_bedroom_purifier", "field": "on",
                                "operator": "eq", "value": true}]},
 "trajectory_ref": "TC_trajectories.jsonl#sc_TC7A_0001",
 "labels": {"read_ok": true, "comply_ok": true, "summary_ok": true}}
```

## 4 两条管线的涉及文件清单

```text
目录 new_demo/data_static/D0_templates_tc/
  TC6A_task.md          出题提示词（2.1）
  D0_request_TC6A.md    写用户话提示词（2.3）
  D3_review_TC6A.md     审查提示词（2.5）
  TC7A_task.md          出题提示词（3.1）
  D0_request_TC7A.md    写用户话提示词（3.3）
  D3_review_TC7A.md     审查提示词（3.5）
  D6_TC7A.md            语义复核提示词（3.9）
  A_policy_tc_sections.md  A 提示词附加段（时间调度 + 记忆）

代码 new_demo/data_tc/
  TC0_template.py / TC2_task_writer.py / TC2_request_writer.py /
  TC3_reviewer.py / TC4_oracle.py / TC5_run.py / TC6_judge.py / TC_PIPE_pipeline.py

产物
  data_raw_tc/、data_processed_tc/TC_dataset.jsonl、TC_trajectories.jsonl、TC_manifest.json
  评测集 eval_sets/TC_20261010_v1/
```

## 5 待确认点

```text
1  required_calls 是否采用（TC7A 的 read_ok、TC7C 第2轮的"必须读过记忆"依赖它；
   不采用的话，读记忆只能从轨迹里人工/事后判断）
2  方案 4 的命名：存储块 tc 还是 ext；运行时世界块 scenario.world 还是沿用 scenario.tc
3  TC7A 的 forbidden_actions / required_effects 数据结构（现在例子是字符串列表）
4  空气净化器落地（设备目录 + B_schema + A 提示词设备常识）
5  轮数上限 12 的代码改动（B_models / B_schema / D4 / D5 / A_policy / 评测 runner）
```
