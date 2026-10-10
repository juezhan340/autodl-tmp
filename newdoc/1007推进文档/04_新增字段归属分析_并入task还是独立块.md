# 04 新增字段放哪：并入 task，还是独立成一块

> 背景：TC6 / TC7 引入了一批新字段（time_mention、at_time_expected、offset_minutes、base_time、memory_initial、memory_expected、session_turns、due_state 等）。
> 现有管线的每条记录是 s0（家）/ 画像 / task / user_request 这几个部分；本文只讨论"新字段接在哪里"，
> 不改任何已有结论（静止时间、影子执行、掉线不处理、轮数 12）。

## 0 一屏

```text
推荐：三层拆分（方案 C）

  判定真值（C / D6 要用）    → 并入 task（扩展 TaskSpec，字段可选）
  例：at_time_expected、due_steps、memory_expected、forbidden_actions

  世界初值（B reset 要用）    → 独立成一块（scenario.tc）
                              例：base_time、memory_initial、session_turns、due_state

  生成元数据（只有 D 用）      → 只留在蓝图 / 草稿，不进 scenario
                              例：time_type、time_mention、offset_minutes

一句话：谁消费，就放在谁那一层；一个字段只放一处，不做冗余。
```

## 1 先把字段和消费者盘清

```text
字段              谁产生   谁消费                放哪（方案 C）
time_type         D 出题   D（统计/复现）         蓝图
time_mention           D 出题   D（审计）             蓝图
offset_minutes    D 出题   D（算 at_time_expected）    蓝图
base_time         D 抽样   B reset（→ now）       scenario.tc
horizon_minutes   常量     B / C 校验             scenario.tc（或常量）
at_time_expected       D 出题   C / D6 判定            task
due_steps         D 出题   C 判定（部分分依据）     task
memory_initial    D 生成   B reset（→ memory）    scenario.tc
memory_expected   D 出题   C / D6 判定            task
session_turns     D 设计   C runner / B 会话模式   scenario.tc
due_state         D 出题   C 结算（影子执行）      scenario.tc
forbidden/required D 出题  C 判定（TC7A 约束）     task
```

判断规则：字段被 C/D6 用来"判对错"→ 进 task；被 B 用来"初始化世界"→ 进 scenario.tc；
只用来记录"这题是怎么造出来的"→ 留在蓝图。

## 2 三种方案

### 2.1 方案 A：全部并入 task

```text
task: {
  intent, conditions, keep, required_observations, expected_finish,
time_type, time_mention, offset_minutes, base_time, at_time_expected,
due_steps, memory_initial, memory_expected, session_turns, due_state
}
```

```text
优点   一条记录只翻一个箱子；数据集自含；C/D6 只读 task
缺点   task 现在的语义是"隐藏目标，只给 C 看"；把 base_time、memory_initial
       这类"世界初值"混进去以后，B 的 reset 也要读 task，语义变模糊；
       TaskSpec 必须扩展，而且它同时被 D6、评测、统计脚本引用，改动面最大；
       生成元数据（time_mention / offset）也进 task 的话，判定侧会看到用不到的字段
```

### 2.2 方案 B：全部独立成 scenario.tc（task 完全不动）

```text
task: { intent, conditions, keep, required_observations, expected_finish }   ← 原样
tc:   { kind, time_type, time_mention, offset_minutes, base_time, at_time_expected,
        due_steps, memory_initial, memory_expected, session_turns, due_state }
```

```text
优点   完全不动老 TaskSpec、老数据、老判定；B 只读 tc；隔离最彻底
缺点   "判定真值"和"任务目标"被拆到两个箱子：C/D6 要同时读 task（conditions）
       和 tc（at_time_expected / memory_expected），漏读一个就判错；
       task 的概念被拆散，后续 T1~T5 若也要扩展会冒出第二套模式
```

### 2.3 方案 C：三层拆分（推荐）

```text
task: {
  intent, conditions, keep, required_observations, expected_finish,   ← 老字段不动
  at_time_expected, due_steps, memory_expected, forbidden_actions, required_effects   ← 新增可选字段
}

scenario.tc: {
  kind, base_time, horizon_minutes, memory_initial, session_turns, due_state
}

蓝图 / 草稿（不进 scenario）: { time_type, time_mention, offset_minutes }
```

```text
优点
  每个字段只有一个消费者层级：C/D6 读 task；B 读 tc；D 读蓝图
  老数据零影响：新字段是可选的，老 task 照旧 without 新键
  B 不需要理解"目标"，只需要读世界初值；task 不需要掺杂运行参数
  判定真值和目标条件都在 task 里，C/D6 不用跨箱找
缺点
  TaskSpec 要做一次"可选字段"扩展（向后兼容）；
  文档要写清三层的映射表（就是本文第 1 节）
```

### 2.4 方案 C 的命名建议

```text
scenario.tc 这个名字里"tc"是任务族标签，放在"世界初值"这个用途上略绕。
两个选择：
  C1  沿用 scenario.tc（不再改名，语义按本文第 1 节的表）
  C2  改名 scenario.world（世界初值），文档里 tc 只保留 TC6/TC7 类别含义
建议 C2；如果你不想再动名字，C1 也能用，只是看的人要记住"tc=世界初值"。
```

## 3 对比表

```text
维度              方案 A 全并 task        方案 B 全独立 tc        方案 C 三层拆分
老数据兼容        需要 TaskSpec 扩展       完全不动                 TaskSpec 加可选字段，老数据不变
B 的读取          B 要读 task              B 只读 tc               B 只读 tc
C/D6 读取         只读 task                同时读 task + tc        只读 task（真值全在 task）
语义清晰度        task 混杂三类语义        "任务"被拆成两半        每层单一职责
生成元数据       也进 task（冗余）        也进 tc（冗余）          留在蓝图，不进运行数据
改动面           最大（TaskSpec 多处引用） 最小                    中等（TaskSpec 一次扩展）
后续扩展性        容易继续堆字段           新老两套模式            新字段按消费者归位
```

## 4 落地细节（方案 C）

```text
TaskSpec 扩展
  新增可选字段：at_time_expected、due_steps、memory_expected、forbidden_actions、required_effects
  to_dict 只在字段有值时输出新键 → 老 task 的 JSON 与指纹保持逐字不变
  from_dict 缺省为空 → 老数据读取路径不受影响

scenario.tc
  B.reset 只读：base_time、memory_initial、session_turns
  C 判定读：at_time_expected / due_steps / memory_expected（在 task 里）
  due_state 给结算用；没有就按当前状态影子执行（掉线不处理）

蓝图 / 草稿
  保留 time_type、time_mention、offset_minutes 与 memory 的生成理由，
  用于复现、审计与失败重放；D5 之后的轨迹与数据集不再带这些生成元数据

版本与指纹
  TC 数据结构加一个版本号（例如 tc_schema: "v1"），
  老数据没有该键，指纹逻辑不变；新老数据可以共存
```

## 5 和 due_state、记忆生成的关系

```text
due_state  只保留"目标已达成 / 被别人改过"两种情况；掉线不处理，
           也不再构造掉线负例（对应上一轮修订）
记忆       memory_initial 由 D2 依据真实 s0 与画像现场生成（不抽样拼装），
           放进 scenario.tc；memory_expected 是判定真值，放进 task
```

## 6 待拍板

```text
1  采用方案 C 吗？还是选 A / B？
2  scenario.tc 是否改名为 scenario.world（推荐改，语义更直白）？
3  task 里的新字段是平铺（at_time_expected 直接放在 task 下）还是再套一层 tc_truth？
   建议平铺，字段少、读取直接；如果以后字段多了再考虑分组
4  due_steps 是否作为判定真值参与部分分（比对模型写的 steps），还是只用于影子执行？
   影响 due_steps 是否必须进 task
```

---

## 附录 A 新增字段逐项举例

> 本附录只解释"每一项是什么"，不讨论放 task 还是放独立块。
> 固定示例环境（后面反复用）：
> ```text
> now = 2026-10-10 09:30（周六）
> 卧室：空调 device_bedroom_climate、空气净化器 device_bedroom_purifier、
>       台灯 device_bedroom_lamp、加湿器 device_bedroom_humidifier
> 客厅：主灯 device_living_light
> ```

### A.0 清单总表（含最新提出项，先审这个）

```text
状态说明
  已写入   01~03 文档里已经有了
  待审     最近讨论新提出，还没写进 01~03 正文，只在本表与后面小节里
  建议删   提出删除，等你确认

编号   名称               一句话                        状态      属于哪一层
A.1    time_type          绝对/相对时间类型             已写入    task/蓝图
A.2    time_mention       用户话里的时间说法            已写入    蓝图
A.3    at_time_expected   标准答案时刻                  已写入    task
A.4    offset_minutes     相对偏移分钟数                已写入    蓝图
A.5    base_time          冻结的场景起始时间            已写入    scenario.tc
A.6    horizon_minutes    7 天窗口上限                  已写入    scenario.tc
A.7    due_steps          TC6 期望的预约动作序列        已写入    task
A.8    due_state          到点状态快照（不含掉线）       已写入    scenario.tc
A.9    memory_initial     开局记忆内容                  已写入    scenario.tc
A.10   memory_expected    应该写进记忆的内容            已写入    task
A.11   forbidden_actions  记忆约束下不许做的动作        已写入    task
A.12   required_effects   记忆驱动必须达成的效果        已写入    task
A.13   action_steps       TC7 现在就做的动作序列        建议删    task
A.14   session_turns      会话轮数                      已写入    scenario.tc
A.15   turns[]            TC7C 逐轮计划                 已写入    task/scenario
A.16   kind               TC6A…TC7C 类别标签           已写入    scenario.tc
A.17   轨迹侧新增         session_id / turn_index /      已写入    D5 轨迹
                          clock / memory_before/after / schedules
A.18   required_calls     必须发生过的工具调用          待审      task
```

### A.1 time_type

```json
"time_type": "absolute"     // 例："今晚 10 点把客厅灯关掉"
"time_type": "relative"     // 例："40 分钟后把加湿器关掉"
```

```text
是什么    这道题属于哪种时间说法，只给数据管线用
谁写谁读  D 写；D 统计与复现读；B、C 不读
反例      "过一会儿" 既不是绝对也不是相对 → 这种题不收录
```

### A.2 time_mention

```json
"time_mention": "今晚10点"
"time_mention": "40分钟后"
"time_mention": "明早7点"
```

```text
是什么    用户话里那个时间说法的原样记录（给审计和回归用）
正例见上；反例：time_mention 里写 "2026-10-10 22:00"（这是答案，不是题面说法）
谁写谁读  D 写；D 审计读；模型看不到这个字段
```

### A.3 at_time_expected

```text
场景      now = 2026-10-10 09:30
```

```json
"time_mention": "今晚10点"   →  "at_time_expected": "2026-10-10 22:00"
"time_mention": "40分钟后"   →  "at_time_expected": "2026-10-10 10:10"
"time_mention": "明早7点"    →  "at_time_expected": "2026-10-11 07:00"
"time_mention": "23:40 说 40 分钟后" → "at_time_expected": "2026-10-11 00:20"
```

```text
是什么    这道题的标准答案时刻，C 判定用；模型写的 at 与它分钟级相等才算对
反例      模型写 "2026-10-10 22:01" → 差 1 分钟，判错或按部分分
谁写谁读  D 算好；C / D6 读；模型看不到
```

### A.4 offset_minutes

```json
"time_mention": "40分钟后"      →  "offset_minutes": 40
"time_mention": "两个小时后"     →  "offset_minutes": 120
"time_mention": "明天同一时间"   →  "offset_minutes": 1440
```

```text
是什么    相对题的偏移量（分钟），D 用它算 at_time_expected、写用户话
谁写谁读  D 写；D 自己读；模型看不到（模型看到的是"40 分钟后"这句话）
反例      "过一会儿" 没有具体数值 → 不收录
```

### A.5 base_time

```json
"base_time": "2026-10-10 09:30"
```

```text
是什么    这一局开始时家里几点；B 在 reset 时解析成 now，整个会话冻结
例子      inspect_time 第一次返回 09:30，之后每次都返回 09:30
反例      同一局中途变成 09:31 → 不允许（冻结时间的不变量）
谁写谁读  D 抽样决定；B reset 读；C 记录读
```

### A.6 horizon_minutes

```json
"horizon_minutes": 10080
```

```text
是什么    预约窗口上限（7 天）；校验 at − now ≤ 10080
边界例子  now=2026-10-10 09:30
          at=2026-10-17 09:30 → 差 10080 → 合法
          at=2026-10-17 09:31 → 差 10081 → INVALID_TIME
谁写谁读  常量；B / C 校验读
```

### A.7 due_steps（TC6 的期望动作序列）

```json
"due_steps": [
  {"device_id": "device_living_light", "action": "turn_off", "params": {}},
  {"device_id": "device_bedroom_purifier", "action": "turn_on", "params": {}}
]
```

```text
是什么    这张预约单"到点应该执行什么"的期望真值
对应关系  due_steps 是参考答案；模型实际提交的 steps 在它的
          time_control.schedule 调用里（接口字段名仍叫 steps），C 拿两者比对
正例      模型写 turn_off 客厅灯 + turn_on 净化器 → 与期望一致
反例      模型只写 turn_off 客厅灯 → 缺一步，按部分分
谁写谁读  D 出题写；C / D6 读
```

### A.8 due_state（到点状态快照，不含掉线）

```json
"due_state": {"device_bedroom_humidifier": {"on": false}}
"due_state": {"device_bedroom_climate": {"target": 26.0}}
```

```text
是什么    假设"到点时世界长这样"，结算时用它替换影子执行的起点状态
例子1     due_state 说加湿器已经关着，预约是"关加湿器"
          → 影子执行 changed=false → 记"目标已达成"
例子2     due_state 说空调已被别人调到 26，预约是"设为 24"
          → 影子执行把它设成 24 → 判成功
不再包含  设备掉线（available=false）不构造、不处理
谁写谁读  D 出题写（可选）；C 结算读
```

### A.9 memory_initial

```json
"memory_initial": "用户对花粉过敏，别开窗；闷了先开空气净化器"
```

```text
是什么    开局时记忆里已经写好的初始文本；B 在 reset 时复制成运行时 memory
来源      不抽样：D2 依据本轮真实 s0（有哪些房间/设备）与画像现场生成
正例      s0 有空气净化器、画像写"花粉过敏" → 上面这句成立
反例      s0 没有窗户设备，却写"别开窗" → 一致性校验不过
谁写谁读  D 写；B reset 读；会话结束 B 丢弃
```

### A.10 memory_expected

```json
用户话： "记住：我睡觉要关客厅灯"
"memory_expected": "睡觉时要关客厅灯"
```

```text
是什么    模型应该写进记忆的内容（判定真值）
正例      模型 memory.write("睡觉时要关客厅灯") → 一致
反例      模型 write("睡觉时要关卧室灯") → 设备写错，判错
          模型 write("") 或根本没写 → 判错
谁写谁读  D 出题写；C / D6 读（同义改写算不算对，口径待定）
```

### A.11 forbidden_actions

```json
记忆："用户对花粉过敏，别开窗"
"forbidden_actions": ["开窗通风类动作"]
```

```text
是什么    受记忆约束、这道题里不许出现的动作
判定      轨迹里出现这类动作 → 约束违反（即使最后目标达成也扣分）
前提      只有 s0 里真的有对应设备，D 才能写这条；
          没有窗户设备就换别的约束（例如"不许把空调调到 24 度以下"）
谁写谁读  D 出题写；C 判定读
```

### A.12 required_effects

```json
记忆："闷了先开空气净化器"
"required_effects": ["device_bedroom_purifier on=true"]
```

```text
是什么    受记忆驱动、必须达成的效果
判定      终态或影子结果里必须为真；没做 → 违反
正例      模型开了净化器 → 满足
反例      模型开了加湿器 → 不满足（设备选错）
谁写谁读  D 出题写；C 判定读
```

### A.13 action_steps（TC7B / TC7C 的"现在就做"）

```text
状态：建议删除，待你确认（替代方案见 A.18 required_calls）
理由：它要求完整动作路线，和"终态达标即可"的判定口径冲突；
      部分分可以用 conditions 进度（ΔΦ）算，行为要求可以用窄字段表达。
```

```json
用户话："记住：我睡觉要关客厅灯；顺便把卧室灯调暗一点"
"memory_expected": "睡觉时要关客厅灯"
"action_steps": [{"device_id": "device_bedroom_lamp", "action": "set_percentage",
                  "params": {"value": 30}}]
```

```text
是什么    这一轮里"现在就执行"的动作序列，和记忆写入分开记账
正例见上：关客厅灯进 memory_expected，调暗卧室灯进 action_steps
反例      模型把"关客厅灯"现在就执行了 → 执行了不该现在做的事，判错
          模型把"调暗台灯"写进记忆、不执行 → 漏了真实动作，判错
谁写谁读  D 出题写；C 判定读
```

### A.14 session_turns

```json
"session_turns": 0     // 单轮任务（TC6A/TC6B/TC7A/TC7B）
"session_turns": 3     // 会话任务（TC7C）：三轮共享环境与记忆
```

```text
是什么    这道题有几个用户轮次；>0 表示 B 只 reset 一次、轮间不重置
例子      session_turns=3 → 轮1写记忆、轮2用记忆、轮3查状态，全程同一份 memory 与设备状态
谁写谁读  D 设计写；C 的 runner 与 B 的会话模式读
```

### A.15 turns[]（TC7C 的逐轮计划）

```json
"turns": [
  {"turn": 1, "goal": "记下睡觉要关客厅灯", "memory_op": "write",
   "memory_expected": "睡觉时要关客厅灯", "action_steps": []},
  {"turn": 2, "goal": "用记忆把客厅灯关掉", "memory_op": "read",
   "action_steps": [{"device_id": "device_living_light", "action": "turn_off", "params": {}}],
   "conditions": [{"device_id": "device_living_light", "field": "on", "operator": "eq", "value": false}]},
  {"turn": 3, "goal": "如实回答客厅灯状态", "memory_op": "read",
   "action_steps": [], "conditions": []}
]
```

```text
子字段      turn          第几轮
            goal          这一轮要完成什么（不泄露给模型，判定用）
            memory_op     这一轮预期的记忆操作：write / read / none
            memory_expected / action_steps / conditions   与前面单轮字段同义
判定        逐轮判：轮1 记忆写对没有；轮2 是否读了记忆并关灯；轮3 回答是否与状态一致
谁写谁读    D 设计写；C / D6 逐轮判定读
```

### A.16 kind

```json
"kind": "TC6B"
```

```text
是什么    这道题的类别标签：TC6A/TC6B/TC7A/TC7B/TC7C
谁写谁读  D 写；D（选模板/账本）与 C（选判定）读；
          B 不按 kind 分支（只管世界初值）
```

### A.17 轨迹侧新增（不是 task 字段，顺带说明）

```json
{"session_id": "sess_0007", "turn_index": 2,
 "clock": {"base_time": "2026-10-10 09:30", "now": "2026-10-10 09:30"},
 "memory_before": "睡觉时要关客厅灯", "memory_after": "睡觉时要关客厅灯",
 "schedules": [{"schedule_id": "sch_01", "at": "2026-10-10 10:10"}]}
```

```text
session_id    会话编号（TC7C 才有）
turn_index    这条记录属于第几轮
clock         这局的时间口径（冻结的 base_time / now）
memory_before / memory_after   一次记忆读写前后的内容
schedules     当前预约单快照
这些都是 D5 落盘的轨迹字段，不进 task、不进 scenario
### A.18 required_calls（最新提出，待审）

```json
{"tool": "memory", "op": "read"}                    // 必须成功读过记忆
{"tool": "inspect_device", "device_id": "device_bedroom_climate"}  // 必须查过某台设备
```

```text
是什么    要求轨迹里"必须发生过某类工具调用"的行为检查，
          是老管线 required_observations（T4 必须先查设备）的推广
用在 TC7A  必须读过预置记忆（否则"符合记忆约束"可能只是碰巧）
用在 TC7C  第 2 轮必须读过第 1 轮写的记忆（否则测不到跨轮使用）
不用在 TC7B  memory_expected 已能直接验证写入内容
判定      出现至少一次成功调用 → 该检查通过；没出现 → 即使终态达标，
          也只给结果分、不给"行为分"
谁写谁读  D 出题写；C / D6 判定读；模型看不到
状态      待审：确认采用后，替换 A.13 action_steps 的作用
```

## 附录 B 老字段速查（不是新增，读例子时会用到）

```json
"intent": "进门还是热，想把卧室空调调低一点"
"conditions": [{"device_id": "device_bedroom_climate", "field": "target",
                "operator": "le", "value": 27.0}]
"keep": [{"device_id": "device_living_light", "field": "on", "operator": "eq", "value": false}]
"required_observations": [{"device_id": "device_bedroom_climate"}]
"expected_finish": {"outcome": "completed", "allowed_reason_codes": []}
```

```text
intent                出题人写的一句话目标（给评审看，不判分）
conditions            目标条件：eq 精确值 / ge 比初值高 / le 比初值低
keep                  不该动的设备（保持原样）
required_observations 必须先查过的设备（T4 用）
expected_finish       finish 契约：completed / refused + 允许的 reason_code
probe                 T4 专用的"必须被拒绝的尝试"，不进蓝图
```

## 附录 C 机制与流程变更总表（不是字段，但都是新加的，待你过一遍）

```text
编号   变更                          说明                                      状态
C.1    时间冻结（静止时间）            now 全会话不变，不做推进、不做 tick        已写入 02/03
C.2    影子执行 + 结算                copy 状态应用 steps，与期望比对            已写入 02/03
C.3    掉线不处理                     due_state 不再构造掉线，不记环境故障       已写入 02/03/04
C.4    会话模式（TC7C）               reset 一次，轮与轮之间不重置               已写入 01/02/03
C.5    时间抽样                       base_time 从时间池抽（时段/工作日周末）     已写入 03
C.6    记忆按场景生成                 依据本轮 s0 与画像生成 memory_initial，     已写入 03
                                      不做记忆池抽样
C.7    TC6/TC7 全工具下发             模型看到全部 8 个工具                      已写入 03
C.8    轮数上限 10 → 12               全部新任务按 12 轮                         已写入 01~03
                                      （代码与 A_policy 的 10 还未改）
C.9    新增空气净化器                 只有 turn_on / turn_off，无档位            已写入 01/03
                                      （设备目录与 schema 还未加）
C.10   required_calls                 替代 action_steps 的行为检查               待审
```

## 附录 D 已发生的改名映射（供你核对）

```text
旧名                     新名                 状态
at_expr                  time_mention         已改（01~04）
at_expected              at_time_expected     已改（01~04）
steps（任务侧）           due_steps            已改（01~04）
memory_seed              memory_initial       已改
memory_write_expected    memory_expected      已改（03 里统一）
action_steps             待定（建议删除）       待审
接口 time_control.steps  不变                 保留原接口字段名
```
