# 05 完整管线示例：TC6A 绝对时间 与 TC7A 读预置记忆

> 依据：`04_新增字段归属分析` 的字段清单；按**方案 3（写入时分层）**呈现：
> 判定真值进 task（base_task / time_task / memory_task 三块）、
> 世界初值进 world；time_mention 归 time_task，tc_schema 放蓝图顶层。
> 名词按 2026-10-10 定稿：time_mention、at_time_expected、offset_minutes、due_steps、due_conditions、
> memory_initial、memory_expected、forbidden_actions、required_calls（2026-10-13 起归 base_task，见 1.2）、
> session_turns、turns[]、kind（落盘沿用老键名 category）、tc_schema。
> required_effects 已按 2026-10-11 决定删除。
> 本文只走两类：TC6A（绝对时间一次性预约）与 TC7A（读预置记忆），从提示词到轨迹到数据集完整呈现。
> 2026-10-11 追加调整：base_time 并入 s0（home 顶层键），world 不再带 base_time；
> 同时补全 2.3 / 3.3 的 D2-2 示例——task 三块（base_task / time_task / memory_task）都要进提示词。
> 2026-10-11 决议（TC 判定口径）：
>   1  base_task.conditions 更名 instant_conditions（即时条件；TC6 固定为空数组）；
>      time_task 新增 due_conditions（到点条件，定时终态的判定对象）
>   2  due_state 删除：不再有"到点状态快照"，到点判定直接看 due_conditions
>   3  影子起点：D4 = 出题时的 s0（同一副本先本地试答、再影子试答，顺序叠加）；
>      定时终态判定 = "新的 s0" = episode 结束时的世界（当前时刻执行完的结果；
>      静止时间下就是到点时的世界）
>   4  定时终态对模型实际提交的 steps 跑影子，结果对即过（steps_ok 只记一致性）；
>      due_conditions 的 eq 比 value、ge/le 与 T1~T5 同口径（比 s0 初值严格变向）
>   5  TC6 标签（2026-10-12 调整）：C-2 扩展为"即时终态 + 定时终态"双分支（原"结算"并入 C-2）；
>      新增 C-5 下单；编号到 C-5 为止
>   6  TC6A 不做大模型复判（2026-10-12 定）：规则已钉死（C-1~C-5 全规则判定），
>      d6="跳过"、不发请求；summary 语义不在管线内校验
>   7  TC7A 也不做大模型复判（2026-10-12 定）：read_ok 改为 C-5 规则标签；
>      遵守性由 C-2 承担；summary 不校验；D6_TC7A 模板删除
>   8  required_calls 收敛（2026-10-13 定）：base_task.required_observations 更名并泛化为
>      required_calls（"必须发生过的成功调用"）；memory_task 的 required_calls 删除
> 设备变更（2026-10-12 记）：计划新增空气净化器 air_purifier（id_token=purifier，
> device_id 形如 device_bedroom_purifier），只有 turn_on / turn_off 两个动作，
> state 只有 {on}，没有 mode / level / target；用于 TC6 / TC7 场景（如"花粉过敏 → 开净化器"）。
> 本版文档的案例暂不使用它——全部案例只用现有设备，等设备落地后再进示例。
> 老设备集与老数据不动。待落地：D0_devices.jsonl 加行、B_schema 白名单、D1 挂载、
> A_policy 设备常识（见 §5 第 4 条）。

## 0 一屏

```text
管线主链（两类共用，只有提示词与判定不同）

  静态库（不在跑批环节内）：D0_templates_tc/ 的提示词模板、
  D0_homes / D0_devices / D0_personas
        ↓ 供 D2 使用
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
  D5 跑轨迹（A 提示词 = 老 A_policy + TC 附加段；C 收集 turns 并打 C-1~C-4）
        ↓
  D6 复核（TC6A / TC7A 都不做大模型复判 → 直接跳过；老五类里只有 T3/T4/T5 走三票）
        ↓
TC_dataset.jsonl（沿用现有行结构：scenario / record / labels / category / d6 / d6_votes）
```

```text
两份示例的固定输入（下面所有阶段都围绕它们展开）

  base_time = 2026-10-10 09:30
  家：客厅主灯 device_living_light、卧室空调 device_bedroom_climate、
      卧室加湿器 device_bedroom_humidifier
  画像：p21，花粉过敏，晚上容易鼻塞

  TC6A  用户话："今晚10点帮我把客厅灯关掉"
  TC7A  用户话："卧室有点热，把空调开一下。"（记忆里预置"睡觉时空调固定 25.5 度、制冷"）
```

## 1 公共部分（两类共用）

### 1.1 D1 抽样与生成

```text
抽样   户型（D0_homes）、设备（D0_devices）、画像（D0_personas）
抽样   时间 base_time：D1 从时间池抽（早上/下午/晚上/深夜、工作日/周末）并写入 s0（home）
生成   记忆 memory_initial（仅 TC7A）：由 D2 依据本轮 s0 与画像生成，不抽样拼装
约束   同一任务只冻结一个 base_time；记忆必须与 s0 吻合
```

### 1.2 蓝图与运行时结构（方案 3：写入时分层，对齐现有蓝图）

```text
现有蓝图（D4_blueprints.jsonl）的真实字段：
  blueprint_id / category / home / task / user_request
  home 就是 s0：房间、设备、每台设备的初始 state 全在里面
  画像不落蓝图（只在 D2 出题时用）

方案 3 在新版里这么放：
  task 拆成 base_task / time_task / memory_task 三块（intent 与 expected_finish 必填）
  base_time 并入 s0：作为 home 顶层键随 home 一起走（2026-10-11 调整）
  world 放运行初值（horizon_minutes / session_turns；不含 base_time；due_state 已删）
  tc_schema 放蓝图顶层；time_mention 归 time_task；不再单设 gen 块
```

```json
{
  "blueprint_id": "bp_TC6A_0001",
  "category": "TC6A",
  "tc_schema": "v1",
  "home": {
    "base_time": "2026-10-10 09:30",
    "rooms": [
      {"room_id": "room_living", "display_name": "客厅",
       "device_ids": ["device_living_light"]},
      {"room_id": "room_bedroom", "display_name": "卧室",
       "device_ids": ["device_bedroom_climate",
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
    "base_task": {
      "intent": "今晚睡前把客厅灯关掉",
      "instant_conditions": [],
      "keep": [],
      "required_calls": [],
      "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}
    },
    "time_task": {
      "time_mention": "今晚10点",
      "at_time_expected": "2026-10-10 22:00",
      "due_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
      "due_conditions": [{"device_id": "device_living_light", "field": "on",
                          "operator": "eq", "value": false}]
    },
    "memory_task": {}
  },
  "user_request": "今晚10点帮我把客厅灯关掉吧。",
  "world": {
    "horizon_minutes": 10080,
    "session_turns": 0
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
  world            ← blueprint.world（B reset 只读这块；base_time 已在 home 里，不走这里）
  memory_initial   蓝图里在 task.memory_task.memory_initial；
                   D5 组装时移动到 scenario.world.memory_initial
                   （B 只读 world；scenario.task 里不再保留该键）
  tc_schema / category  只留在蓝图，不传 B
  D5 落盘的一行      ← {scenario, record, labels, category, d6, d6_votes}
                      （record 里是 turns / final_state / finish / protocol，
                        与现有 D5_trajectories.jsonl 同构）

两点对齐说明：
  1  现有蓝图没有 persona；TC7A 的 memory_initial 依赖画像，
     建议蓝图新增 persona_id（或 persona 全量）用于审计——这是新增项，待确认
  2  现有蓝图用 category 键；新文档里叫 kind 的是同一个东西，
     落盘建议沿用 category，避免两套键名

task 的三块：
  base_task    必有；字段：intent / instant_conditions / keep / required_calls /
               expected_finish；intent 与 expected_finish 不能为空
               （conditions 更名为 instant_conditions："写单这一刻"的目标；
                TC6 固定为空数组——现在不做任何事）
               （required_observations 更名为 required_calls：写"必须发生过的成功调用"，
                条目形如 {"tool": "<工具名>", ...定位参数}。例：
                  {"tool":"inspect_device","device_id":"..."}   T4 式：拒绝前必须先查过
                  {"tool":"memory","op":"read"}                 TC7A：必须读过记忆
                  {"tool":"inspect_time"}                       TC6 可选：必须先读时钟
                判定：轨迹里存在一次成功（ok=true）的匹配调用 → 过；空数组过）
  time_task    时间相关：time_mention / at_time_expected / due_steps / due_conditions
               （TC6B 还有 offset_minutes）；非时间任务为 {}
               （due_conditions = "到点执行后"的目标，定时终态判它；
                eq 比 value，ge/le 比 s0 初值严格变向，与 T1~T5 同口径）
  memory_task  记忆相关：memory_initial / memory_expected / forbidden_actions / turns；
               非记忆任务为 {}
               （原 memory_task.required_calls 已删：这类"必须调用"统一放 base_task.required_calls）
  required_effects 已删除，正面约束一律写对应块的 conditions
  （注：老管线 T1~T5 的 task.conditions / required_observations 键不动；
    instant_conditions 与 required_calls 只出现在 TC 三块结构里）
```

### 1.3 A 提示词装配（不改老提示词）

```text
TC 的 A 提示词 = 老 A_policy.md + TC 附加段
  工具表：全部 8 个（observe_home / inspect_room / inspect_device / execute_action /
          finish / inspect_time / time_control / memory）
  TC6A 附加段：时间调度规则（见 2.8）
  TC7A 附加段：记忆规则（见 3.8）
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

输出字段（task 三块；intent 与 expected_finish 必填、不能为空）
{"base_task": {"intent":"一句话目标",
               "instant_conditions":[],
               "keep":[], "required_calls":[],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {"time_mention":"用户话里的时间说法",
               "at_time_expected":"YYYY-MM-DD HH:MM",
               "due_steps":[{"device_id":"...","action":"...","params":{}}],
               "due_conditions":[{"device_id":"...","field":"...",
                                  "operator":"eq","value":...}]},
 "memory_task": {}}

硬规则
  at_time_expected 必须晚于 base_time，且在 7 天（10080 分钟）以内，分钟级
  due_steps 1~3 条，设备与动作只能来自本轮 s0
  time_mention 不能是"每晚/每天"这类持久规则；出现直接判废,不能模糊成今晚睡前，必须准确为某个时间点
  time_mention 时间点准确，但不能直接写标准格式（那是答案，不是题面说法）
  instant_conditions 描述当前时刻要满足的状态；TC6A 固定写空数组
  due_conditions 描述涉及时间任务"到点执行后终态应满足什么"（定时终态的判定对象）
  required_calls 本期固定为空（要"必须先读时钟"这类要求时再写，例 {"tool":"inspect_time"}）
  时间相关字段全部放 time_task；memory_task 固定为 {}（TC6A 不用记忆）
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
           "device_bedroom_humidifier"]}], "devices":[...]}
本轮 base_time："2026-10-10 09:30"
正确输出：
{"base_task": {"intent":"今晚睡前把客厅灯关掉",
               "instant_conditions":[],
               "keep":[], "required_calls":[],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {"time_mention":"今晚10点","at_time_expected":"2026-10-10 22:00",
               "due_steps":[{"device_id":"device_living_light",
                             "action":"turn_off","params":{}}],
               "due_conditions":[{"device_id":"device_living_light","field":"on",
                                  "operator":"eq","value":false}]},
 "memory_task": {}}

不要照抄例子里的设备与数值；本轮按 {{s0}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 2.2 D2-1 输出（TC6A task）

```json
{"base_task": {"intent": "今晚睡前把客厅灯关掉",
               "instant_conditions": [],
               "keep": [], "required_calls": [],
               "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
 "time_task": {"time_mention": "今晚10点",
               "at_time_expected": "2026-10-10 22:00",
               "due_steps": [{"device_id": "device_living_light",
                              "action": "turn_off", "params": {}}],
               "due_conditions": [{"device_id": "device_living_light", "field": "on",
                                   "operator": "eq", "value": false}]},
 "memory_task": {}}
```

```text
base_time 不由出题模型产出：D1 抽样后写入 s0（home）；horizon_minutes 由 D4 组装蓝图时写进 world；
task 三块原样保留。（2026-10-11 调整：base_time 并入 s0）
due_steps / due_conditions 由出题模型一起写；D4 负责验（见 2.7）。
```

### 2.3 D0 模板：D0_request_TC6A.md（写用户话提示词全文）

```text
功能
把 TC6A 的 task 写成一句自然的用户请求。
task 三块都是输入：动作看 time_task 的 due_steps，时间看 time_mention；
请求里必须同时说清这两件事，但不能出现标准时刻、device_id、动作名、工具名。

规则
  请求必须同时覆盖"做什么"（time_task.due_steps 的动作）与"什么时候做"（time_mention）
  两个块都要读；漏掉任何一边都是 TARGET_NOT_COVERED
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
task：{"base_task":{"intent":"今晚睡前把客厅灯关掉",
                    "instant_conditions":[],
                    "keep":[],"required_calls":[],
                    "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
       "time_task":{"time_mention":"今晚10点","at_time_expected":"2026-10-10 22:00",
                    "due_steps":[{"device_id":"device_living_light",
                                  "action":"turn_off","params":{}}],
                    "due_conditions":[{"device_id":"device_living_light","field":"on",
                                       "operator":"eq","value":false}]},
       "memory_task":{}}
可用显示名：客厅主灯、卧室空调、卧室加湿器
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

### 2.7 D4 Oracle（不调模型：两段试答，与 T1~T5 同构）

```text
输入      task + s0 + base_time
结构      一份副本、顺序两段，两段都可以为空（沿用老 D4 的 _check_writes，前后叠加）
  阶段 A 本地试答（老 D4 原样）：instant_conditions 逐条反推写动作，在副本上顺序打，
         必须被 B 接受
         · T1~T5 = 只有这一段；TC6A/B 的 instant_conditions 固定为空 → 空过
         · TC7A/B 走这一段（当下动作的可行性）
  阶段 B 影子试答（接在阶段 A 之后、同一份副本上）：due_conditions 逐条反推写动作，
         继续顺序试打，必须被 B 接受
         · 语义 = "本地该做的做完之后，到点还能不能达成"；两段状态顺序叠加
         · TC6A/B 走这一段（instant 为空 → 阶段 B 直接从 s0 起）
         · 不执行 due_steps 序列；自洽性不在此拦（数据集准入由轨迹端把关）
  另外     静态检查：due_steps 与 due_conditions 引用的 device_id / field / action / params
           在 s0 中合法（due_steps 只做字面体检——写话素材、steps_ok 参考）
           时间检查：at_time_expected 晚于 base_time 且 ≤ base_time + 10080 分钟
  对齐说明 与判定链同构：episode 改变世界 → 定时终态在新 s0 上判 due_conditions；
           D4 换成"本地试答改变副本 → 影子试答判 due_conditions"，两段一一对应
输出
  {"oracle_ok": true,
   "shadow_state_diff": {"device_living_light": {"on": {"from": true, "to": false}}},
   "reason": "at 合法、本地/到点两段试答通过"}
```

### 2.8 C 与 A 交互（D5 跑轨迹；结束时 C 自动打标签）

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
交互循环（C 调度 A 与 B；一次 C.run 完成一局）
  每轮 C 把 context（observation / tools / history / 协议反馈 / 轮次号）交给 A
  A 输出一个工具调用或 finish；家庭工具走 B.step；finish 由 C 收下并结束
  一轮最多 1 个工具；解析失败记 INVALID_ASSISTANT_RESPONSE（消耗一轮）
  跑满 12 轮未 finish → truncated
```

```text
D5 落盘的 record（与现有批次 quota50 / quota200 同构：scenario_id / turns / final_state /
finish / protocol；每个 turn 含 turn / observation_before / tool_calls / events / observation_after。
observation = B 的观测视图 {scenario_id, user_request, tools, last_tool_result}，落盘时已展开；
observation_after 与下一轮 observation_before 同值；TC 增量只有 record.tc_trace）

{
  "scenario_id": "sc_TC6A_0001",
  "turns": [
    {"turn": 1,
     "observation_before": {B 的观测视图：scenario_id / user_request / tools / last_tool_result},
     "tool_calls": [{"name": "inspect_time", "arguments": {}, "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "inspect_time", "arguments": {},
                 "result": {"ok": true,
                            "data": {"now": "2026-10-10 09:30", "clock": "virtual"},
                            "error": null},
                 "state_diff": {}}],
     "observation_after": {同上；last_tool_result 更新为本轮结果}},
    {"turn": 2,
     "tool_calls": [{"name": "time_control",
                     "arguments": {"op": "schedule", "at": "2026-10-10 22:00",
                                   "steps": [{"device_id": "device_living_light",
                                              "action": "turn_off", "params": {}}]},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "time_control",
                 "arguments": {"op": "schedule", "at": "2026-10-10 22:00",
                               "steps": [{"device_id": "device_living_light",
                                          "action": "turn_off", "params": {}}]},
                 "result": {"ok": true,
                            "data": {"schedule_id": "sch_01",
                                     "at": "2026-10-10 22:00", "status": "pending"},
                            "error": null},
                 "state_diff": {}}],
     "observation_after": {同上}},
    {"turn": 3,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "今晚10点关掉客厅灯，已经预约。"},
                     "call_id": "turn_3_0"}],
     "events": [{"call_id": "turn_3_0", "tool_name": "finish",
                 "arguments": {"outcome": "completed",
                               "summary": "今晚10点关掉客厅灯，已经预约。"},
                 "result": {"ok": true,
                            "data": {"outcome": "completed",
                                     "summary": "今晚10点关掉客厅灯，已经预约。"},
                            "error": null},
                 "state_diff": {}}],
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
"到点会不会变成 false"由交互结束时的"定时终态"判定（见下）算。
定时终态影子的起点 = 新的 s0，即本 episode 结束时的世界（当前时刻执行完的结果；
静止时间下这就是"到点时的世界"），不是出题时的旧 s0。

交互一结束（同一次 C.run 调用内），C 自动打标签（不调模型）。
C-2 本次做了调整：原来只有"即时终态"，现在加上"定时终态"，两个分支串成一条线；
TC6 新增的独立标签订为 C-5 下单：

C-1 协议        finish_requested 为真 且 未 truncated 且 没有一轮多工具（TOO_MANY_TOOL_CALLS）
C-2 终态（调整）  两个分支，共用同一套条件检查器：
                · 即时终态：final_state 满足 instant_conditions + keep（空数组过；
                  TC6 中 instant_conditions 固定为空 → 该分支恒过）
                · 定时终态（原"结算"并入）：影子执行——起点 = 新的 s0（episode 结束时的世界
                  = 当前时刻执行完的结果），步骤 = 模型实际提交的 steps（不换成 due_steps；
                  结果对就可以），比对 = 影子终态满足 due_conditions（eq 比 value；
                  ge/le 比 s0 初值严格变向）→ settle_ok（掉线本期不处理）
C-3 必需调用    required_calls 都出现过成功调用（空数组过；TC6A 固定为空 → 恒过）
C-4 finish      outcome 与 expected_finish.outcome 对齐；refused 的 reason_code 必须落在
                expected_finish.allowed_reason_codes 里；出现 facts 失败；
                completed 带 reason_code 失败
C-5 下单（新；本任务独有分支）  预约单建立 且 at 与 at_time_expected 分钟级相等（place_ok）
                且 没有"该写单却直接执行"（time_error = false）
                · 明细：place_ok、time_error；steps_ok 仅记录、不挡 C-5（结果导向）
                · 注：C-5 按任务族取分支——TC6 = 预约单检查；TC7 的 C-5 = 记忆使用（见 3.8）

同行落盘：{"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true,
          "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false}
（明细键保留供分析：C-5 ↔ place_ok / steps_ok / time_error；settle_ok 属 C-2 的定时终态分支；
  time_error = 该写单却直接 execute_action，终态碰巧满足也算错）
```

### 2.9 D6（TC6A：不做大模型复判 → 跳过）

```text
TC6A 不进 D6 语义复核——让大模型审这条轨迹没有意义：
  at / 预约单建立 / steps 一致性 / 影子结算 / C-1~C-5，全部由规则钉死（见 2.8），
  没有需要语言判断的残余。
该行直接记 d6="跳过"、d6_votes=[]，不发任何模型请求；
summary 的语义也不在管线内校验（C-4 只看 outcome / reason_code / facts）。

（对照：老五类里只有 T3/T4/T5 进 D6 三票；T1/T2 与 TC7 同样跳过。）
```

### 2.10 进数据集

```json
{
  "scenario": {
    "scenario_id": "sc_TC6A_0001",
    "blueprint_id": "bp_TC6A_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "今晚10点帮我把客厅灯关掉吧。",
    "task": {
      "base_task": {"intent": "今晚睡前把客厅灯关掉",
                    "instant_conditions": [],
                    "keep": [], "required_calls": [],
                    "expected_finish": {"outcome": "completed",
                                        "allowed_reason_codes": []}},
      "time_task": {"time_mention": "今晚10点",
                    "at_time_expected": "2026-10-10 22:00",
                    "due_steps": [{"device_id": "device_living_light",
                                   "action": "turn_off", "params": {}}],
                    "due_conditions": [{"device_id": "device_living_light",
                                        "field": "on", "operator": "eq",
                                        "value": false}]},
      "memory_task": {}
    },
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"horizon_minutes": 10080,
              "session_turns": 0}
  },
  "record": {"...": "见 2.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true,
             "place_ok": true, "steps_ok": true, "settle_ok": true, "time_error": false},
  "category": "TC6A",
  "d6": "跳过",
  "d6_votes": []
}
```

D_dataset.jsonl 的行结构与 D5_trajectories.jsonl 相同。
TC6 进集口径（结果导向；标签定义见 2.8）：C-1 / C-3 / C-4 / C-5 全 true，
且 C-2 的"定时终态"分支通过（影子终态满足 due_conditions；"即时终态"分支在 TC6 恒过）；
其中 C-5 已含 place_ok 与 time_error = false；steps_ok 仅记录、不单独卡进集
（是否更严见 §5 待确认）。

## 3 TC7A 完整管线

### 3.1 D0 模板：TC7A_task.md（出题提示词全文）

```text
功能
你是数据辅助生成器。根据本轮 s0 与画像，写一份 TC7A（读预置记忆）的隐藏 task JSON。
只输出一个 JSON 对象，不要写用户话，不要解释。

TC7A 是什么
这局的记忆里已经预先写好一段偏好或约束（memory_initial）；
用户请求本身不会复述这段内容，助手要先读记忆，再按记忆约束行动。
本示例走"记忆里有明确数值偏好"这一型：数值只存在记忆里，请求只说动作。

输出字段（task 三块；intent 与 expected_finish 必填、不能为空）
{"base_task": {"intent":"一句话目标",
               "instant_conditions":[{"device_id":"...","field":"...",
                                      "operator":"eq","value":...}],
               "keep":[], "required_calls":[{"tool":"memory","op":"read"}],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {},
 "memory_task": {"memory_initial":"开局记忆里已有的内容",
                 "memory_expected":"",
                 "forbidden_actions":["不许做的动作"]}}

硬规则
  memory_initial ≤200 token，必须是"偏好/约束"，不能是"现在就做某个动作"的指令
  memory_initial 必须与本轮 s0 吻合（本轮没有的设备/能力不许写）；
  例：s0 没有空调，就不能写"空调固定 25.5 度"
  memory_initial 与用户请求相关，但请求不能直接复述它（具体数值尤其不能漏进请求）
  forbidden_actions 0~2 条（没有禁令就写空数组）；写的话必须是 s0 里真实存在设备的动作
  必须发生的调用写进 base_task.required_calls（例：{"tool":"memory","op":"read"}）；
  TC7A 固定要求读过记忆；memory_task 不再有 required_calls
  正面约束（必须达成的效果）写进 base_task.instant_conditions；不再使用 required_effects
  记忆里的数值偏好要原样落成 eq 目标值（例：25.5 → target eq 25.5）
  记忆内容字段（memory_initial / memory_expected / forbidden_actions）放 memory_task；
  time_task 固定为 {}（TC7A 不用时间调度）
  注意：task JSON 里不写类别；类别由模板决定，蓝图顶层写 category（如 TC7A）

小例子
对  memory_initial="睡觉时空调固定 25.5 度、制冷"
    forbidden_actions=[]
    base_task.required_calls=[{"tool":"memory","op":"read"}]
    base_task.instant_conditions=[{"device_id":"device_bedroom_climate","field":"on",
                                   "operator":"eq","value":true},
                                  {"device_id":"device_bedroom_climate","field":"target",
                                   "operator":"eq","value":25.5},
                                  {"device_id":"device_bedroom_climate","field":"mode",
                                   "operator":"eq","value":"cool"}]
错  memory_initial="把客厅灯关掉"（这是动作指令，不是偏好记忆）
错  s0 里没有空调却写"空调固定 25.5 度"

完整例子
本轮画像：{"persona_id":"p21","name":"李岚","age":29,"habits":"花粉过敏，晚上容易鼻塞"}
本轮 s0：{"rooms":[{"room_id":"room_bedroom","device_ids":["device_bedroom_climate",
          "device_bedroom_humidifier"]}], "devices":[...]}
正确输出：
{"base_task": {"intent":"卧室热，按记忆把空调开到 25.5 度制冷",
               "instant_conditions":[{"device_id":"device_bedroom_climate","field":"on",
                                      "operator":"eq","value":true},
                                     {"device_id":"device_bedroom_climate","field":"target",
                                      "operator":"eq","value":25.5},
                                     {"device_id":"device_bedroom_climate","field":"mode",
                                      "operator":"eq","value":"cool"}],
               "keep":[], "required_calls":[{"tool":"memory","op":"read"}],
               "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
 "time_task": {},
 "memory_task": {"memory_initial":"睡觉时空调固定 25.5 度、制冷",
                 "memory_expected":"",
                 "forbidden_actions":[]}}

不要照抄例子；本轮按 {{s0}} 与 {{persona}} 另写。

本轮输入
画像：{{persona}}
s0：{{s0}}
base_time：{{base_time}}
```

### 3.2 D2-1 输出（TC7A task）

```json
{"base_task": {"intent": "卧室热，按记忆把空调开到 25.5 度制冷",
               "instant_conditions": [{"device_id": "device_bedroom_climate", "field": "on",
                                       "operator": "eq", "value": true},
                                      {"device_id": "device_bedroom_climate", "field": "target",
                                       "operator": "eq", "value": 25.5},
                                      {"device_id": "device_bedroom_climate", "field": "mode",
                                       "operator": "eq", "value": "cool"}],
               "keep": [], "required_calls": [{"tool": "memory", "op": "read"}],
               "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}},
 "time_task": {},
 "memory_task": {"memory_initial": "睡觉时空调固定 25.5 度、制冷",
                 "memory_expected": "",
                 "forbidden_actions": []}}
```

```text
base_time 由 D1 抽样写入 s0（home），horizon_minutes 由 D4 写进 world；
两者都不由出题模型产出（2026-10-11 调整：base_time 并入 s0）。
memory_initial 留在 task.memory_task（这是蓝图里的源）；
D5 组装 scenario 时移动到 scenario.world.memory_initial 供 B reset。
TC7A 没有 due_conditions（time_task 为空）；它的动作在当下真执行，判定看终态。
```

### 3.3 D0 模板：D0_request_TC7A.md（写用户话提示词全文）

```text
功能
把 TC7A 的 task 写成一句自然的用户请求。
请求只说需求，不直接复述 memory_initial；要能自然触发"先读记忆"的需求。
记忆里的具体数值（如 25.5 度）不能出现在请求里——那是答案。

规则
  禁止照抄 memory_initial 的句子或连续 8 个字以上
  禁止把记忆里的具体数值/取值写进请求（数值只属于记忆）
  禁止出现 device_id / room_id / 动作名 / 工具名 / 标准时刻
  禁止把记忆内容说成"现在就做"的动作
  只说这一句话，不要解释

小例子
对  memory_initial="睡觉时空调固定 25.5 度、制冷"
    → "卧室有点热，把空调开一下。"
对  memory_initial="用户怕冷，睡觉空调不要低于26度"
    → "卧室有点冷。"
错  "卧室有点热，空调调到 25.5 度"（把记忆里的数值说出来了）
错  "把 device_bedroom_climate 打开"（泄露 id）

完整例子
intent：卧室热，按记忆把空调开到 25.5 度制冷
task：{"base_task":{"intent":"卧室热，按记忆把空调开到 25.5 度制冷",
                    "instant_conditions":[{"device_id":"device_bedroom_climate","field":"on",
                                           "operator":"eq","value":true},
                                          {"device_id":"device_bedroom_climate","field":"target",
                                           "operator":"eq","value":25.5},
                                          {"device_id":"device_bedroom_climate","field":"mode",
                                           "operator":"eq","value":"cool"}],
                    "keep":[],"required_calls":[{"tool":"memory","op":"read"}],
                    "expected_finish":{"outcome":"completed","allowed_reason_codes":[]}},
       "time_task":{},
       "memory_task":{"memory_initial":"睡觉时空调固定 25.5 度、制冷",
                      "memory_expected":"","forbidden_actions":[]}}
可用显示名：卧室空调、卧室加湿器
正确输出：卧室有点热，把空调开一下。

本轮输入
intent：{{intent}}
task：{{task}}
可用显示名：{{display_names}}
```

### 3.4 D2-2 输出

```text
user_request = "卧室有点热，把空调开一下。"
```

### 3.5 D0 模板：D3_review_TC7A.md（审查提示词全文）

```text
功能
审查 TC7A 的用户话：有没有漏说需求、有没有泄露记忆内容（含具体数值）、有没有多说设备。

程序扫描（命中任一 → HARD_LEAKAGE）
  老规则：动作名 / 工具名 / device_id / room_id / JSON 片段
  记忆照抄：与 memory_initial 有连续 8 个字以上相同 → HARD_LEAKAGE

模型审查（只回答 accept 与 codes）
  TARGET_NOT_COVERED  请求完全没有表达出与记忆相关的需求
  EXTRA_INTENT        多说了任务之外的设备或动作
  HARD_LEAKAGE        字面泄露（含照抄记忆）

判例
  用户话 "卧室有点热，把空调开一下。" + 记忆"空调固定 25.5 度" → accept
  用户话 "把空调调到 25.5 度"（把记忆里的数值说出来了）→ HARD_LEAKAGE
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
  2  可行性：base_task.instant_conditions 对应的动作在 s0 中合法
  3  本地试答（老 D4 同一套）：copy s0 → instant_conditions 逐条反推写动作
     （turn_on / set_temperature(25.5) / set_mode(cool)）→ 在副本上试打，必须被 B 接受
     （TC7A 没有阶段 B：没有 due_conditions；动作在 episode 里真执行，无定时终态影子）
输出
  {"oracle_ok": true, "shadow_state_diff":
   {"device_bedroom_climate": {"on": {"from": false, "to": true},
                               "mode": {"from": "auto", "to": "cool"},
                               "target": {"from": 26.0, "to": 25.5}}},
   "reason": "记忆与 s0 一致；按记忆行动可达成 base_task.instant_conditions"}
```

### 3.8 C 与 A 交互（D5 跑轨迹；结束时 C 自动打标签）

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
交互循环（C 调度 A 与 B；一次 C.run 完成一局）
  每轮 C 把 context（observation / tools / history / 协议反馈 / 轮次号）交给 A
  A 输出一个工具调用或 finish；家庭工具走 B.step；finish 由 C 收下并结束
  一轮最多 1 个工具；解析失败记 INVALID_ASSISTANT_RESPONSE（消耗一轮）
  跑满 12 轮未 finish → truncated
```

```text
D5 落盘的 record（与现有批次同构；observation = B 的观测视图，落盘时已展开；
observation_after 与下一轮 observation_before 同值；TC 增量只有 record.tc_trace）

{
  "scenario_id": "sc_TC7A_0001",
  "turns": [
    {"turn": 1,
     "observation_before": {B 的观测视图：scenario_id / user_request / tools / last_tool_result},
     "tool_calls": [{"name": "memory", "arguments": {"op": "read"},
                     "call_id": "turn_1_0"}],
     "events": [{"call_id": "turn_1_0", "tool_name": "memory",
                 "arguments": {"op": "read"},
                 "result": {"ok": true,
                            "data": {"text": "睡觉时空调固定 25.5 度、制冷"},
                            "error": null},
                 "state_diff": {}}],
     "observation_after": {同上；last_tool_result 更新为记忆文本}},
    {"turn": 2,
     "tool_calls": [{"name": "inspect_device",
                     "arguments": {"device_id": "device_bedroom_climate"},
                     "call_id": "turn_2_0"}],
     "events": [{"call_id": "turn_2_0", "tool_name": "inspect_device",
                 "arguments": {"device_id": "device_bedroom_climate"},
                 "result": {"ok": true,
                            "data": {"device": {"device_id": "device_bedroom_climate",
                                                "display_name": "卧室空调", "kind": "actuator",
                                                "device_type": "climate",
                                                "state": {"on": false, "mode": "auto", "target": 26.0},
                                                "actions": ["..."]}},
                            "error": null},
                 "state_diff": {}}],
     "observation_after": {同上}},
    {"turn": 3,
     "tool_calls": [{"name": "execute_action",
                     "arguments": {"device_id": "device_bedroom_climate",
                                   "action": "turn_on", "params": {}},
                     "call_id": "turn_3_0"}],
     "events": [{"call_id": "turn_3_0", "tool_name": "execute_action",
                 "arguments": {"device_id": "device_bedroom_climate",
                               "action": "turn_on", "params": {}},
                 "result": {"ok": true,
                            "data": {"device_id": "device_bedroom_climate",
                                     "action": "turn_on",
                                     "state_after": {"on": true, "mode": "auto", "target": 26.0},
                                     "verified": true, "changed": true},
                            "error": null},
                 "state_diff": {"on": {"from": false, "to": true}}}],
     "observation_after": {同上}},
    {"turn": 4,
     "tool_calls": [{"name": "execute_action",
                     "arguments": {"device_id": "device_bedroom_climate",
                                   "action": "set_mode", "params": {"mode": "cool"}},
                     "call_id": "turn_4_0"}],
     "events": [{"call_id": "turn_4_0", "tool_name": "execute_action",
                 "arguments": {"device_id": "device_bedroom_climate",
                               "action": "set_mode", "params": {"mode": "cool"}},
                 "result": {"ok": true,
                            "data": {"device_id": "device_bedroom_climate",
                                     "action": "set_mode",
                                     "state_after": {"on": true, "mode": "cool", "target": 26.0},
                                     "verified": true, "changed": true},
                            "error": null},
                 "state_diff": {"mode": {"from": "auto", "to": "cool"}}}],
     "observation_after": {同上}},
    {"turn": 5,
     "tool_calls": [{"name": "execute_action",
                     "arguments": {"device_id": "device_bedroom_climate",
                                   "action": "set_temperature", "params": {"value": 25.5}},
                     "call_id": "turn_5_0"}],
     "events": [{"call_id": "turn_5_0", "tool_name": "execute_action",
                 "arguments": {"device_id": "device_bedroom_climate",
                               "action": "set_temperature", "params": {"value": 25.5}},
                 "result": {"ok": true,
                            "data": {"device_id": "device_bedroom_climate",
                                     "action": "set_temperature",
                                     "state_after": {"on": true, "mode": "cool", "target": 25.5},
                                     "verified": true, "changed": true},
                            "error": null},
                 "state_diff": {"target": {"from": 26.0, "to": 25.5}}}],
     "observation_after": {同上}},
    {"turn": 6,
     "tool_calls": [{"name": "finish",
                     "arguments": {"outcome": "completed",
                                   "summary": "卧室热，按您的习惯把空调开到 25.5 度制冷。"},
                     "call_id": "turn_6_0"}],
     "events": [{"call_id": "turn_6_0", "tool_name": "finish",
                 "arguments": {"outcome": "completed",
                               "summary": "卧室热，按您的习惯把空调开到 25.5 度制冷。"},
                 "result": {"ok": true,
                            "data": {"outcome": "completed",
                                     "summary": "卧室热，按您的习惯把空调开到 25.5 度制冷。"},
                            "error": null},
                 "state_diff": {}}],
     "observation_after": {同上}}
  ],
  "final_state": {"device_bedroom_climate": {"on": true, "mode": "cool", "target": 25.5},
                  "...": "其余设备状态原样"},
  "finish": {"summary": "卧室热，按您的习惯把空调开到 25.5 度制冷。",
             "outcome": "completed"},
  "protocol": {"terminated": true, "truncated": false,
               "finish_requested": true, "turn_count": 6}
}

record 里新增可选块（仅 TC 任务）：
{"tc_trace": {"clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
              "memory_before": "睡觉时空调固定 25.5 度、制冷",
              "memory_after": "睡觉时空调固定 25.5 度、制冷",
              "schedules": []}}
```

```text
交互一结束（同一次 C.run 调用内），C 自动打标签（不调模型）：
  ① 打 C 标签（C-1~C-5）
     C-1 协议     finish_requested 为真 且 未 truncated 且 没有一轮多工具（TOO_MANY_TOOL_CALLS）
     C-2 终态     两个分支，共用同一套条件检查器（和 TC6 同一套定义）：
                  · 即时终态：final_state 满足 instant_conditions + keep（空数组过）；
                    eq 比 value；ge/le 比 s0 初值严格变向 —— TC7A 走这一支
                  · 定时终态：影子执行（新的 s0 + 模型 steps）终态满足 due_conditions
                    —— TC7A 不用（time_task 为空、没有 due_conditions）
     C-3 必需调用   required_calls 都出现过成功调用（空数组过）——TC7A 的"必须读过记忆"
                  就是这里的一个条目 {"tool":"memory","op":"read"}
     C-4 finish   outcome 与 expected_finish.outcome 对齐；refused 的 reason_code 必须落在
                  allowed_reason_codes 里；出现 facts 失败；completed 带 reason_code 失败
     C-5 记忆使用（本任务独有分支）  = required_calls 里记忆条目的检查结果（本示例 memory.read），
                  与 C-3 同一份数据、单独汇报（本期只判"读过"；读与做的先后顺序暂不检查）
                  · 注：C-5 按任务族取分支——TC7 = 记忆使用检查；TC6 的 C-5 = 预约单（见 2.8）
  ② 遵守性与 summary
     遵守性 = C-2（instant_conditions 达成即"按记忆做对了"）；
     本期示例 forbidden_actions 为空；日后禁令型记忆落地时，forbidden 需结构化、在此加规则检查；
     summary 语义不在管线内校验。
  （TC7A 动作在 episode 里真执行，判定看 final_state；没有 TC6 那种定时终态影子）
```

### 3.9 D6（TC7A：不做大模型复判 → 跳过）

```text
TC7A 不进 D6 语义复核——和 TC6A 同理，让大模型审这条轨迹没有必要：
  · 读没读记忆 → base_task.required_calls 里的记忆条目（memory.read）：C-3 通用检查、C-5 记忆切片
  · 做得对不对 → C-2 的即时终态分支：instant_conditions + keep 全达成
  · 禁止项     → 本期示例 forbidden_actions 为空；日后禁令型落地改成结构化规则检查
  · summary    → 不在管线内校验（C-4 只看 outcome / reason_code / facts）
该行直接记 d6="跳过"、d6_votes=[]，不发任何模型请求。

（原 D6_TC7A.md 语义复核模板不再需要，从模板清单里删除；
  需要语义复核的老类别只剩 T3/T4/T5。）
```

### 3.10 判定与进数据集（TC7A；按时间顺序）

```text
TC7A 全程零大模型复判：

① C 在 3.8 交互结束时打完标签：C-1~C-5（C-5 = 记忆使用 read_ok，规则判定）
② D6 跳过：d6="跳过"、d6_votes=[]，不发请求（同 TC6A；老五类里只有 T3/T4/T5 走三票）
③ 进集：C-1~C-5 全 true 且 d6="跳过" → 复制进数据集
```

```json
{
  "scenario": {
    "scenario_id": "sc_TC7A_0001",
    "blueprint_id": "bp_TC7A_0001",
    "home": {"...": "s0 全量（与蓝图 home 相同）"},
    "user_request": "卧室有点热，把空调开一下。",
    "task": {
      "base_task": {"intent": "卧室热，按记忆把空调开到 25.5 度制冷",
                    "instant_conditions": [{"device_id": "device_bedroom_climate",
                                            "field": "on", "operator": "eq", "value": true},
                                           {"device_id": "device_bedroom_climate",
                                            "field": "target", "operator": "eq", "value": 25.5},
                                           {"device_id": "device_bedroom_climate",
                                            "field": "mode", "operator": "eq", "value": "cool"}],
                    "keep": [], "required_calls": [{"tool": "memory", "op": "read"}],
                    "expected_finish": {"outcome": "completed",
                                        "allowed_reason_codes": []}},
      "time_task": {},
      "memory_task": {"memory_expected": "",
                      "forbidden_actions": [],
                      "turns": []}
    },
    "episode_config": {"max_turns": 12, "max_tool_calls_per_turn": 1},
    "world": {"horizon_minutes": 10080,
              "memory_initial": "睡觉时空调固定 25.5 度、制冷",
              "session_turns": 0}
  },
  "record": {"...": "见 3.8 的 record"},
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true, "C-5": true},
  "category": "TC7A",
  "d6": "跳过",
  "d6_votes": []
}
```

```text
说明：蓝图里 memory_initial 在 task.memory_task；D5 组装 scenario 时
移动到 world.memory_initial（上面已是搬运后的运行时视图）。
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
  A_policy_tc_sections.md  A 提示词附加段（时间调度 + 记忆）
  （原 D6_TC7A.md 语义复核模板已删：TC7A 不做大模型复判）

代码 new_demo/data_tc/
  TC0_template.py / TC2_task_writer.py / TC2_request_writer.py /
  TC3_reviewer.py / TC4_oracle.py / TC5_run.py / TC6_judge.py / TC_PIPE_pipeline.py

产物
  data_raw_tc/、data_processed_tc/TC_dataset.jsonl、TC_trajectories.jsonl、TC_manifest.json
  评测集 eval_sets/TC_20261010_v1/
```

## 5 待确认点

```text
1  required_calls（2026-10-13 定）：采用，并改放 base_task——替换原 required_observations，
   语义泛化为"必须发生过的成功调用"（条目如 {"tool":"memory","op":"read"}）；
   memory_task 的 required_calls 删除；C-3 做通用检查
2  三块结构与空块约定：base_task 必有且 intent / expected_finish 非空；
   time_task / memory_task 可为 {}——已按此执行，确认即可
3  TC7A 的 forbidden_actions 数据结构（现在例子是字符串列表；
   日后禁令型记忆要用规则检查，需要结构化）
4  空气净化器落地（设备目录 + B_schema + A 提示词设备常识）
5  轮数上限 12 的代码改动（B_models / B_schema / D4 / D5 / A_policy / 评测 runner）
6  蓝图是否新增 persona_id（TC7A 的 memory_initial 依赖画像，现有蓝图不存画像）
7  kind 与 category 统一用哪个键（现有蓝图用 category，新文档用 kind）
8  record 里新增的 tc_trace 块（clock / memory_before / memory_after /
   schedules / shadow_result）字段与容器名确认
9  TC6 标签（2026-10-11 起，2026-10-12 调整）：C-2 扩展为双分支——"即时终态"（final_state）
   + "定时终态"（影子推演终态，原"结算"并入）；TC6 新增独立标签订为 C-5 下单；
   编号到 C-5 为止；明细 place_ok / steps_ok / settle_ok / time_error 保留供分析
10 memory_initial 的搬运口径：蓝图在 task.memory_task、运行时在 world；
   确认按"D5 移动、scenario.task 不再保留"处理
11 base_time 并入 s0（2026-10-11 调整，已定）：home 顶层新增 base_time 键，
   world 不再带 base_time；D1 写入、B reset 从 home 读取，由 B_clock 解析
12 更名（2026-10-11 已定）：base_task.conditions → instant_conditions；
   time_task 新增 due_conditions。老管线 T1~T5 的 conditions 键不动；
   04/03/02/01 需同步本轮决议
13 due_state 已删（2026-10-11）：不再有到点状态快照；world 只留 horizon_minutes / session_turns
14 进集是否更严：现在结果导向（place_ok + settle_ok 即过，steps_ok 仅记录）；
   要不要加"steps_ok 必须 true"，待拍板
15 时间类拒绝（过去 / 超 7 天 / 模糊时间）的 finish reason_code 未定义：
   现有契约只有 OUT_OF_SAFE_RANGE / READ_ONLY_DEVICE，需补码或收窄口径
16 TC7A 记忆形态（2026-10-12）：本版示例只覆盖"明确数值偏好"型；
   禁令型 / 习惯型示例未覆盖，后续按需补
17 TC6A 不做 D6 大模型复判（2026-10-12 定）：C-1~C-5 全规则判定，d6="跳过"、不发请求；
   summary 语义不在管线内校验（要防失实摘要，放 SFT 数据侧抽查）
18 TC7A 也不做大模型复判（2026-10-12 定）：C-5 记忆使用改规则判定（数据来自
   base_task.required_calls 的记忆条目）；遵守性由 C-2 承担；summary 不校验；D6_TC7A.md 模板删除
19 C-5 为任务族独有编号（2026-10-13 记）：TC6 的 C-5 = 预约单检查（下单）；
   TC7 的 C-5 = 记忆使用检查（数据来自 base_task.required_calls 的记忆条目）；
   两侧各自在 2.8 / 3.8 写全，编号相同、语义按类别定义
```
