# 05 完整管线示例：TC6A 绝对时间 与 TC7A 读预置记忆

> 依据：`04_新增字段归属分析` 的字段清单；按**方案 3（写入时分层）**呈现：
> 判定真值写进 task、世界初值写进 world、生成元数据留在 gen（蓝图）。
> 名词按 2026-10-10 定稿：time_mention、at_time_expected、offset_minutes、due_steps、due_state、
> memory_initial、memory_expected、forbidden_actions、required_effects、required_calls（待审）、
> session_turns、turns[]、kind（落盘沿用老键名 category）、tc_schema。
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
TC_dataset.jsonl（沿用现有行结构：scenario / record / labels / category / d6 / d6_votes）
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

### 1.2 蓝图与运行时结构（方案 3：写入时分层，对齐现有蓝图）

```text
现有蓝图（D4_blueprints.jsonl）的真实字段：
  blueprint_id / category / home / task / user_request
  home 就是 s0：房间、设备、每台设备的初始 state 全在里面
  画像不落蓝图（只在 D2 出题时用）

方案 3 在现有蓝图上新增两个块：
  world   世界初值（B reset 用）
  gen     生成元数据（D 审计用）
  判定真值按现有惯例写进 task
```

```json
{
  "blueprint_id": "bp_TC6A_0001",
  "category": "TC6A",
  "home": {
    "rooms": [
      {"room_id": "room_living", "display_name": "客厅",
       "device_ids": ["device_living_light"]},
      {"room_id": "room_bedroom", "display_name": "卧室",
       "device_ids": ["device_bedroom_climate", "device_bedroom_purifier",
                      "device_bedroom_humidifier"]}
    ],
    "devices": [
      {"device_id": "device_living_light", "room_id": "room_living",
       "display_name": "客厅主灯", "kind": "actuator", "device_type": "light",
       "state": {"on": true, "mode": "bright"},
       "actions": [{"action": "turn_on", "params": {}},
                   {"action": "turn_off", "params": {}}],
       "available": true}
    ]
  },
  "task": {
    "intent": "今晚睡前把客厅灯关掉",
    "conditions": [{"device_id": "device_living_light", "field": "on",
                    "operator": "eq", "value": false}],
    "keep": [],
    "required_observations": [],
    "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    "at_time_expected": "2026-10-10 22:00",
    "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
    "memory_expected": "",
    "forbidden_actions": [],
    "required_effects": [],
    "required_calls": [],
    "turns": []
  },
  "user_request": "今晚10点帮我把客厅灯关掉吧。",
  "world": {
    "base_time": "2026-10-10 09:30",
    "horizon_minutes": 10080,
    "memory_initial": "",
    "session_turns": 0,
    "due_state": null
  },
  "gen": {
    "tc_schema": "v1",
    "time_mention": "今晚10点",
    "offset_minutes": null
  }
}
```

```text
D5 组装运行时 scenario（对齐现有 blueprint_to_scenario）：
  scenario_id      D5 新生成
  blueprint_id     ← blueprint.blueprint_id
  home             ← blueprint.home（s0 原样）
  user_request     ← blueprint.user_request
  task             ← blueprint.task（含新增判定真值）
  episode_config   ← {max_turns: 12, max_tool_calls_per_turn: 1}
                     （老代码写死 10，要改）
  world            ← blueprint.world（新增；B reset 只读这块）
  gen / category   只留在蓝图，不传 B
  D5 落盘的一行      ← {scenario, record, labels, category, d6, d6_votes}
                      （record 里是 turns / final_state / finish / protocol，
                        与现有 D5_trajectories.jsonl 同构）

两点对齐说明：
  1  现有蓝图没有 persona；TC7A 的 memory_initial 依赖画像，
     建议蓝图新增 persona_id（或 persona 全量）用于审计——这是新增项，待确认
  2  现有蓝图用 category 键；新文档里叫 kind 的是同一个东西，
     落盘建议沿用 category，避免两套键名
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
{"intent":"一句话目标",
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
  注意：task JSON 里不写类别；类别由模板决定，蓝图顶层写 category（如 TC6A）

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
{"intent":"今晚睡前把客厅灯关掉",
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

### 2.2 D2-1 输出（TC6A 草稿）与 D4 落蓝图时的落位

```json
{"intent": "今晚睡前把客厅灯关掉",
 "time_mention": "今晚10点",
 "at_time_expected": "2026-10-10 22:00",
 "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
 "conditions": [{"device_id": "device_living_light", "field": "on",
                 "operator": "eq", "value": false}],
 "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}}
```

```text
D4 把草稿收进蓝图时要分家（方案 3，写入时分层）：
  task  ← intent / conditions / expected_finish /
          at_time_expected / due_steps
  world ← base_time / horizon_minutes
  gen   ← time_mention（生成元数据，不进运行时）
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
task：{"time_mention":"今晚10点","at_time_expected":"2026-10-10 22:00",
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
D5 落盘的 record（对齐现有 EpisodeRun.record：scenario_id / turns / final_state /
finish / protocol；每个 turn 含 observation_before / tool_calls / events / observation_after）

{
  "scenario_id": "sc_TC6A_0001",
  "turns": [
    {"turn": 1,
     "observation_before": {完整 A 上下文：user_request + 工具表 + 历史},
     "tool_calls": [{"name": "inspect_time", "arguments": {}, "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "inspect_time",
                 "result": {"ok": true,
                            "data": {"now": "2026-10-10 09:30", "clock": "virtual"}}}],
     "observation_after": {同上，追加本次工具结果}},
    {"turn": 2,
     "tool_calls": [{"name": "time_control",
                     "arguments": {"op": "schedule", "at": "2026-10-10 22:00",
                                   "steps": [{"device_id": "device_living_light",
                                              "action": "turn_off", "params": {}}]},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "time_control",
                 "result": {"ok": true,
                            "data": {"schedule_id": "sch_01",
                                     "at": "2026-10-10 22:00", "status": "pending"}}}],
     "observation_after": {同上}},
    {"turn": 3,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "今晚10点关掉客厅灯，已经预约。"},
                     "call_id": "turn_3_0"}],
     "events": [],
     "observation_after": {同上}}
  ],
  "final_state": {"device_living_light": {"on": true, "mode": "bright"},
                  "...": "其余设备状态原样"},
  "finish": {"summary": "今晚10点关掉客厅灯，已经预约。", "outcome": "completed"},
  "protocol": {"terminated": true, "truncated": false,
               "finish_requested": true, "turn_count": 3}
}

record 里新增可选块（仅 TC 任务）：
{"tc_trace": {"clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
              "schedules": [{"schedule_id": "sch_01", "at": "2026-10-10 22:00"}],
              "shadow_result": {"device_living_light": {"on": {"from": true, "to": false}}}}}

注意：final_state 里客厅灯仍是 on=true——静止时间下预约不真正执行；
"到点会不会变成 false"由结算阶段的影子执行判定（见 2.9）。
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
  {"C-1": true, "C-2": true, "C-3": true, "C-4": true,
   "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false}
  · C-1/C-3/C-4 沿用现有口径（协议 / 取证 / finish 契约）
  · C-2 对 TC6A 改为"影子结算结果满足 conditions"，不再看 final_state
  · place_ok / steps_ok / settle_ok 是 TC6A 新增键
D6   TC6A 规则可验证 → d6 = "跳过"，d6_votes = []
```

### 2.10 进数据集

```json
{
  "scenario": {
    "scenario_id": "sc_TC6A_0001",
    "blueprint_id": "bp_TC6A_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "今晚10点帮我把客厅灯关掉吧。",
    "task": {"intent": "今晚睡前把客厅灯关掉",
             "conditions": [{"device_id": "device_living_light", "field": "on",
                             "operator": "eq", "value": false}],
             "keep": [], "required_observations": [],
             "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
             "at_time_expected": "2026-10-10 22:00",
             "due_steps": [{"device_id": "device_living_light",
                            "action": "turn_off", "params": {}}],
             "memory_expected": "", "forbidden_actions": [],
             "required_effects": [], "required_calls": [], "turns": []},
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"base_time": "2026-10-10 09:30", "horizon_minutes": 10080,
              "memory_initial": "", "session_turns": 0, "due_state": null}
  },
  "record": {"...": "见 2.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true,
             "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false},
  "category": "TC6A",
  "d6": "跳过",
  "d6_votes": []
}
```

D_dataset.jsonl 的行结构与 D5_trajectories.jsonl 相同，只收录标签全 true 的行
（沿用现有 D_copy_dataset 口径；TC 新增键也要求为 true）。

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
{"intent":"一句话目标",
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
  注意：task JSON 里不写类别；类别由模板决定，蓝图顶层写 category（如 TC7A）

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
{"intent":"卧室闷，按记忆优先开净化器而不是开窗",
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

### 3.2 D2-1 输出（TC7A 草稿）与 D4 落蓝图时的落位

```json
{"intent": "卧室闷，按记忆优先开净化器而不是开窗",
 "memory_initial": "用户对花粉过敏，别开窗；闷了先开空气净化器",
 "forbidden_actions": ["开窗通风类动作"],
 "required_effects": ["device_bedroom_purifier on=true"],
 "conditions": [{"device_id": "device_bedroom_purifier", "field": "on",
                 "operator": "eq", "value": true}],
 "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}}
```

```text
D4 把草稿收进蓝图时要分家（方案 3，写入时分层）：
  task  ← intent / conditions / expected_finish / memory_expected /
          forbidden_actions / required_effects / required_calls
  world ← base_time / horizon_minutes / memory_initial / session_turns / due_state
  gen   ← tc_schema / 生成元数据（memory 的生成理由）

注意：memory_initial 在 D2-1 草稿里，落蓝图时必须移到 world；
      task 里不保留 memory_initial。
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
task：{"memory_initial":"用户对花粉过敏，别开窗；闷了先开空气净化器", ...}
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
D5 落盘的 record（与现有结构同构）

{
  "scenario_id": "sc_TC7A_0001",
  "turns": [
    {"turn": 1,
     "observation_before": {完整 A 上下文：user_request + 工具表 + 历史},
     "tool_calls": [{"name": "memory", "arguments": {"op": "read"},
                     "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "memory",
                 "result": {"ok": true,
                            "data": {"text": "用户对花粉过敏，别开窗；闷了先开空气净化器"}}}],
     "observation_after": {同上，追加记忆文本}},
    {"turn": 2,
     "tool_calls": [{"name": "inspect_device",
                     "arguments": {"device_id": "device_bedroom_purifier"},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "inspect_device",
                 "result": {"ok": true,
                            "data": {"state": {"on": false}, "actions": ["...turn_on..."]}}}],
     "observation_after": {同上}},
    {"turn": 3,
     "tool_calls": [{"name": "execute_action",
                     "arguments": {"device_id": "device_bedroom_purifier",
                                   "action": "turn_on", "params": {}},
                     "call_id": "turn_3_0"}],
     "events": [{"call_id": "turn_3_0", "tool_name": "execute_action",
                 "result": {"ok": true,
                            "data": {"state_after": {"on": true},
                                     "state_diff": {"on": {"from": false, "to": true}},
                                     "verified": true}}}],
     "observation_after": {同上}},
    {"turn": 4,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "卧室闷，按您的习惯开了空气净化器，没有开窗。"},
                     "call_id": "turn_4_0"}],
     "events": [],
     "observation_after": {同上}}
  ],
  "final_state": {"device_bedroom_purifier": {"on": true},
                  "...": "其余设备状态原样"},
  "finish": {"summary": "卧室闷，按您的习惯开了空气净化器，没有开窗。",
             "outcome": "completed"},
  "protocol": {"terminated": true, "truncated": false,
               "finish_requested": true, "turn_count": 4}
}

record 里新增可选块（仅 TC 任务）：
{"tc_trace": {"clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
              "memory_before": "用户对花粉过敏，别开窗；闷了先开空气净化器",
              "memory_after": "用户对花粉过敏，别开窗；闷了先开空气净化器",
              "schedules": []}}
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
{
  "scenario": {
    "scenario_id": "sc_TC7A_0001",
    "blueprint_id": "bp_TC7A_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "卧室有点闷，帮我想想办法。",
    "task": {"intent": "卧室闷，按记忆优先开净化器而不是开窗",
             "conditions": [{"device_id": "device_bedroom_purifier", "field": "on",
                             "operator": "eq", "value": true}],
             "keep": [], "required_observations": [],
             "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
             "memory_expected": "",
             "forbidden_actions": ["开窗通风类动作"],
             "required_effects": ["device_bedroom_purifier on=true"],
             "required_calls": [], "turns": []},
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"base_time": "2026-10-10 09:30", "horizon_minutes": 10080,
              "memory_initial": "用户对花粉过敏，别开窗；闷了先开空气净化器",
              "session_turns": 0, "due_state": null}
  },
  "record": {"...": "见 3.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true,
             "read_ok": true, "comply_ok": true, "summary_ok": true},
  "category": "TC7A",
  "d6": "对",
  "d6_votes": ["对", "对", "对"]
}
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
2  方案 3 的落位确认：真值进 task、初值进 world、元数据进 gen；
   world 块名是否用 world；tc_schema 放顶层还是 gen
3  TC7A 的 forbidden_actions / required_effects 数据结构（现在例子是字符串列表）
4  空气净化器落地（设备目录 + B_schema + A 提示词设备常识）
5  轮数上限 12 的代码改动（B_models / B_schema / D4 / D5 / A_policy / 评测 runner）
6  蓝图是否新增 persona_id（TC7A 的 memory_initial 依赖画像，现有蓝图不存画像）
7  kind 与 category 统一用哪个键（现有蓝图用 category，新文档用 kind）
8  record 里新增的 tc_trace 块（clock / memory_before / memory_after /
   schedules / shadow_result）字段与容器名确认
9  TC6A 的 C-2 判定源：现有 C-2 看 final_state，TC6A 需要改成
   "影子结算结果满足 conditions"，请在 evaluator 里单独分支
```
