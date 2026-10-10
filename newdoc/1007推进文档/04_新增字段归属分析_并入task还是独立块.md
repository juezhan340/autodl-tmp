# 04 新增字段放哪：并入 task，还是独立成一块

> 背景：TC6 / TC7 引入了一批新字段（time_mention、at_time_expected、offset_minutes、base_time、memory_initial、memory_expected、session_turns、due_state 等）。
> 现有管线的每条记录是 s0（家）/ 画像 / task / user_request 这几个部分；本文只讨论"新字段接在哪里"，
> 不改任何已有结论（静止时间、影子执行、掉线不处理、轮数 12）。

## 0 一屏

```text
2026-10-10 决定：采用方案 3（写入时分层）。
下面保留五方案对比，方案 4 的写法留作备选参考。

方案 3 的落位（写入时就分好）：
  task            判定真值（at_time_expected、due_steps、memory_expected、
                  forbidden_actions、required_effects、required_calls、turns 真值）
  world           世界初值（base_time、memory_initial、session_turns、
                  due_state、horizon_minutes）
  gen（蓝图）      生成元数据（kind、tc_schema、time_mention、offset_minutes）
  轨迹（D5 出）     session_id、turn_index、clock、memory 快照、schedules

一句话：写的时候就把字段放进对应层，D5 只搬运与校验，不做拆分。
```

## 1 先盘清：新东西分四类，存储视角和运行时视角要分开看

```text
类别            例子                                                  谁用
判定真值        at_time_expected、due_steps、memory_expected、        C / D6 判定
                forbidden_actions、required_effects、required_calls、
                turns[] 里的逐轮真值
世界初值        base_time、memory_initial、session_turns、            B reset / C 结算
                due_state、horizon_minutes（常量）
生成元数据      time_type、time_mention、offset_minutes、             D 审计 / 复现
                memory 生成理由、kind（标签）
轨迹产物        session_id、turn_index、clock、memory_before/after、   D5 落盘 / 分析
                schedules、影子结果
```

```text
两个视角要分开看：
  存储视角    数据文件里怎么放（D 写出去、后面读回来）
  运行时视角  D5 跑一局时，B / C / D6 各自从哪个对象里读

同一个字段在两个视角里可以放在不同层。例如 base_time：
  存储时放在一条记录的 tc 块里；
  运行时被 D5 展开成 scenario.world.base_time，专门给 B 用。
```

## 2 五种方案（基于完整清单重定）

### 2.1 方案 1：全部并进 task（一个箱子）

```text
task: {
  老 5 个字段,
  time_type, time_mention, offset_minutes, at_time_expected, base_time,
  horizon_minutes, due_steps, due_state, memory_initial, memory_expected,
  forbidden_actions, required_effects, required_calls, session_turns,
  turns[], kind
}
```

```text
优点   一条记录只翻一个箱子；数据集自含；C/D6 只读 task
缺点   task 的语义是"隐藏目标，只给 C 看"；base_time / memory_initial 这类
       世界初值混进来后，B 也要读 task，语义变模糊；TaskSpec 改动最大；
       生成元数据（time_mention / offset）也进 task 的话，判定侧会看到用不到的字段
```

### 2.2 方案 2：全部独立成一块（task 完全不动）

```text
task:  { intent, conditions, keep, required_observations, expected_finish }   ← 原样
ext:   { kind, time_type, time_mention, offset_minutes, base_time, at_time_expected,
         due_steps, due_state, memory_initial, memory_expected, forbidden_actions,
         required_effects, required_calls, session_turns, turns[] }
```

```text
优点   完全不动老 TaskSpec、老数据、老判定；隔离最彻底
缺点   "判定真值"和"任务目标"被拆到两个箱子：C/D6 要同时读 task（conditions）
       和 ext（at_time_expected / memory_expected / required_calls），漏读就判错；
       task 概念被拆散，以后 T1~T5 想扩展会冒出第二套模式
```

### 2.3 方案 3：按消费者三层（旧方案 C）

```text
task:           判定真值（at_time_expected、due_steps、memory_expected、
                forbidden_actions、required_effects、required_calls、turns 真值）
scenario.world: 世界初值（base_time、memory_initial、session_turns、due_state）
蓝图：          生成元数据（time_type、time_mention、offset_minutes、kind）
```

```text
优点   每个字段只有一个消费者层级：C/D6 读 task；B 读 world；D 读蓝图；
       老数据零影响；B 不需要理解目标，只读世界初值
缺点   覆盖不完整：session_turns / turns[] / kind / due_state 的"家"没写清；
       turns[] 里既有会话结构又有逐轮真值，需要额外规则；
       TaskSpec 仍要做一次可选字段扩展
```

### 2.4 方案 4：存储一体化 + 运行时按消费者拆分（推荐）

```text
存储视角（D 的一条记录）
  一个 tc 块装下全部新字段（判定真值 + 世界初值 + 会话结构 + 生成元数据）
  用 tc_schema 标版本

运行时视角（D5 展开）
  task            ← 判定真值（含 required_calls、turns 的逐轮真值）
  scenario.world  ← base_time、memory_initial、session_turns、due_state
  蓝图（不传 B）  ← time_type、time_mention、offset_minutes、kind
  轨迹（D5 输出） ← session_id、turn_index、clock、memory_before/after、schedules
```

```text
优点
  D 侧只维护一条记录、一个 tc 块，落盘与审计简单
  运行时每个消费者只读自己那层，B 不接触目标，C/D6 不跨箱找真值
  老数据完全不受影响：老记录没有 tc 块，TaskSpec 新字段有值才输出
缺点
  多一层"展开"逻辑：存 tc、跑时拆成 task/world；展开代码是唯一真源，必须配测试
  tc_schema 版本与两套视图的映射要写进文档（就是本文第 1 节与第 4 节）
```

### 2.5 方案 5：会话拆成"每轮一个任务"（TC7C 变体）

```text
存储    一个 session 记录 + N 条 turn 记录，session_id / turn_index 关联
判定    每条 turn 记录独立判定，会话级约束（记忆保留）放在 session 记录
```

```text
优点   每轮独立计分、独立部分分；和多轮 runner 天然对齐；
       失败归因直接落到某一轮，不用在 turns[] 数组里找
缺点   数据集行数变多；会话级统计要 join；session 与 turn 的一致性要额外校验
建议   作为二期可选：TC7C 规模变大、或要求每轮独立训练信号时再切；
       本期先用方案 4 的 turns[] 放 task
```

## 3 对比表（五方案 × 八个维度）

```text
维度              方案1 全并task     方案2 全独立块    方案3 三层       方案4 存储一体化+运行时拆（推荐） 方案5 每轮一任务
老数据兼容        差（大改TaskSpec）  最好（不动）      好（可选扩展）    最好（老数据完全不碰）            中
B 的读取          task               ext              world            world                            world
C/D6 读取         task               task + ext       task             task                             task（每轮）
存储复杂度        低（一箱）          低（一箱）        中（三处）        低（一条 tc 块）                  高（session+turn 两表）
运行时清晰度      差（语义混杂）      差（跨箱找真值）   好               最好（每层单一消费者）             好
会话支持          中                 中               弱（turns 没家）  好（world 里的会话结构）           最好
生成审计          混在 task          混在 ext         干净（蓝图）      干净（蓝图，不传运行时）           干净
落地工作量        大                 小               中               中（多一层展开逻辑）              大
```

## 4 推荐方案 4 的落地细节

### 4.1 存储视图（D 的一条记录）

```json
{
  "scenario_id": "sc_TC6B_007",
  "home": { "...": "..." },
  "user_request": "40 分钟后把加湿器关掉",
  "task": { "intent": "...", "conditions": [], "keep": [],
            "required_observations": [], "expected_finish": {} },
  "episode_config": { "max_turns": 12, "max_tool_calls_per_turn": 1 },
  "tc": {
    "tc_schema": "v1",
    "kind": "TC6B",
    "base_time": "2026-10-10 09:30",
    "horizon_minutes": 10080,
    "time_type": "relative",
    "time_mention": "40分钟后",
    "offset_minutes": 40,
    "at_time_expected": "2026-10-10 10:10",
    "due_steps": [{"device_id": "device_bedroom_humidifier", "action": "turn_off", "params": {}}],
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

### 4.2 运行时视图（D5 展开成三份）

```text
task             += at_time_expected / due_steps / memory_expected /
                    forbidden_actions / required_effects / required_calls /
                    turns 的逐轮真值
scenario.world    = { base_time, memory_initial, session_turns,
                      due_state, horizon_minutes }
蓝图（不进运行时）  = { kind, tc_schema, time_type, time_mention, offset_minutes }
轨迹（D5 写）      = { session_id, turn_index, clock, memory_before/after,
                      schedules, 影子结果 }
```

### 4.3 老数据与非冲突

```text
老记录没有 tc 块 → 展开逻辑直接跳过，行为与现在完全一致
TaskSpec 新字段缺省为空、有值才输出 → 老 task 的 JSON 与指纹逐字不变
tc 块缺失时，B / C / D6 的行为与现在完全一致
```

### 4.4 命名与版本

```text
存储块名       tc（或 ext），带 tc_schema: "v1"
运行时世界块   scenario.world（推荐）；不想改名就沿用 scenario.tc
任务真值       平铺在 task 下（at_time_expected、due_steps…），不再套一层
```

### 4.5 TC7C 的 turns 归属

```text
turns[] 的逐轮真值（memory_expected、conditions、required_calls）→ 放 task
会话结构（轮数、顺序）→ 放 scenario.world 的 session 配置
如果以后要"每轮独立计分、独立训练信号"，再评估方案 5
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
1  方案已定：方案 3（2026-10-10 决定），本条关闭
2  分层命名：真值进 task、初值进 world、元数据进 gen——world / gen 这两个块名采用吗？
3  运行时世界块叫什么：scenario.world（推荐）还是沿用 scenario.tc？
4  task 里的新字段平铺（推荐）还是套一层？套一层的话叫什么？
5  due_steps 是否参与部分分（比对模型写的 steps），还是只用于影子执行？
6  TC7C 先按 turns[] 放 task（推荐），还是直接上方案 5 的"每轮一个任务"？
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
A.13   session_turns      会话轮数                      已写入    scenario.tc
A.14   turns[]            TC7C 逐轮计划                 已写入    task/scenario
A.15   kind               TC6A…TC7C 类别标签（落盘沿用 category） 已写入  蓝图顶层
A.16   轨迹侧新增         session_id / turn_index /      已写入    D5 轨迹
                          clock / memory_before/after / schedules
A.17   required_calls     必须发生过的工具调用          待审      task
```

action_steps 已在 2026-10-10 按审阅决定删除；替代方案是 A.17 required_calls（待审）。

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

### A.13 session_turns

```json
"session_turns": 0     // 单轮任务（TC6A/TC6B/TC7A/TC7B）
"session_turns": 3     // 会话任务（TC7C）：三轮共享环境与记忆
```

```text
是什么    这道题有几个用户轮次；>0 表示 B 只 reset 一次、轮间不重置
例子      session_turns=3 → 轮1写记忆、轮2用记忆、轮3查状态，全程同一份 memory 与设备状态
谁写谁读  D 设计写；C 的 runner 与 B 的会话模式读
```

### A.14 turns[]（TC7C 的逐轮计划）

```json
"turns": [
  {"turn": 1, "goal": "记下睡觉要关客厅灯", "memory_op": "write",
   "memory_expected": "睡觉时要关客厅灯"},
  {"turn": 2, "goal": "用记忆把客厅灯关掉", "memory_op": "read",
   "conditions": [{"device_id": "device_living_light", "field": "on", "operator": "eq", "value": false}]},
  {"turn": 3, "goal": "如实回答客厅灯状态", "memory_op": "read", "conditions": []}
]
```

```text
子字段      turn          第几轮
            goal          这一轮要完成什么（不泄露给模型，判定用）
            memory_op     这一轮预期的记忆操作：write / read / none
            memory_expected / conditions   与前面单轮字段同义
判定        逐轮判：轮1 记忆写对没有；轮2 是否读了记忆并关灯；轮3 回答是否与状态一致
行为检查    第2轮"必须读过记忆"由 A.17 required_calls 承担（待审）
谁写谁读    D 设计写；C / D6 逐轮判定读
```

### A.15 kind

```json
"kind": "TC6B"
```

```text
是什么    这道题的类别标签：TC6A/TC6B/TC7A/TC7B/TC7C
落盘      沿用老蓝图的键名 category（现有蓝图用 category，新文档叫 kind，建议统一 category）
谁写谁读  D 写；D（选模板/账本）与 C（选判定）读；
          B 不按 kind 分支（只管世界初值）
```

### A.16 轨迹侧新增（不是 task 字段，顺带说明）

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
```

### A.17 required_calls（最新提出，待审）

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
状态      待审：确认采用后，用于 TC7A / TC7C 的"必须读过记忆"检查
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

## 附录 C 机制与流程变更（逐项条目）

> 上面的表只是索引；下面每一项都是独立条目，含是什么、例子、影响与状态。

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
C.10   required_calls                 必须发生过的调用（TC7A/TC7C 用）          待审
C.11   tc_schema 版本号               新数据结构带版本（如 "v1"），老数据没有     待审
C.12   B 侧时间转换器                 解析/格式化/比较/7 天窗口；严格拒绝非补零、
                                      带秒、带时区后缀；内部整数分钟；          待审（未建）
                                      建议单模块 B_clock，B 与 D 共用
C.13   scenario.tc 改名候选           改名 scenario.world（语义更直白）          待审
C.14   TaskSpec 可选字段扩展           新字段有值才输出，老 JSON 指纹逐字不变      待审（方案 4 相关）
C.15   新目录与新文件                  data_tc/、D0_templates_tc/、              已写入 03
                                      data_raw_tc/、data_processed_tc/、
                                      eval_sets/TC_20261010_v1/
C.16   13 个新提示词模板               5 任务 + 5 请求 + 2 审查 + 1 评审          已写入 03
C.17   独立账本与数据集                TC_dataset.jsonl、TC_manifest、           已写入 03
                                      后期 collector 合并老数据集
C.18   D3 新泄露规则                   规范时刻不得出现、记忆原文不得照抄、        已写入 03
                                      轮间不泄露后续轮
C.19   D6_TC7 三标签                   读对 / 写对 / 用对                        已写入 03
C.20   记忆一致性校验                  memory_initial 必须与本轮 s0 吻合          已写入 03
                                      （没有窗户就不能写"别开窗"）
C.21   A 提示词装配                    A_policy.md + TC 附加段（不改老提示词）     已写入 03
C.22   影子执行复用规则                 必须复用同一执行内核，禁止另写一套校验器    已写入 02
C.23   立即执行 vs 预约执行判定          TC6 该预约却立即执行 = 时间错误；          已写入 03
                                      TC7B 该立即执行却改成预约 = 方式错误
C.24   评测集规模与负例                 每子类 30 条起步；含过去时间、超 7 天、     已写入 03
                                      跨午夜、模糊表述等负例
C.25   forbidden/required 的 schema    目前只有自然语言示例，数据结构未定          待定
C.26   action_steps 删除               按 2026-10-10 审阅决定删除；             已删除
                                      替代项为 required_calls（待审）
```

### C.1 时间冻结（静止时间）

```text
是什么   整个 episode / 会话里 now 不变；不做推进、不做 tick、环境不自主变化
例子     inspect_time 第一次返回 09:30，之后每次都返回 09:30；预约单在 episode 内不执行
影响     B 只存一个冻结时刻；C 结算时才做影子执行；A 不能推进时间
状态     已写入 02/03
```

### C.2 影子执行 + 结算

```text
是什么   结算时 copy 一份世界状态，把 steps 应用上去，与任务期望比对
例子     "40 分钟后关加湿器"：影子执行后加湿器 on=false → 判成功；真实状态不变
影响     复用 execute_action 的同一套内核，禁止另写一个校验器
状态     已写入 02/03
```

### C.3 掉线不处理

```text
是什么   due_state 不再构造设备掉线，也不再有 DEVICE_UNAVAILABLE 的环境故障分类
例子     "到点时加湿器掉线"这条负例被删除；due_state 只保留"目标已达成、被别人改过"
影响     02 的校验方法、03 的判定与评测口径都同步删掉了掉线例子
状态     已写入 02/03/04
```

### C.4 会话模式（TC7C）

```text
是什么   一个会话 reset 一次，轮与轮之间不重置环境与记忆
例子     轮1 写记忆 → 轮2 读记忆关灯 → 轮3 查状态，三轮共享同一份 memory 与设备状态
影响     C 的 runner 要支持会话；B 要支持"会话内不 reset"
状态     已写入 01/02/03
```

### C.5 时间抽样

```text
是什么   base_time 从时间池抽样，不再固定一个时刻
例子     时间池覆盖早上/下午/晚上/深夜、工作日/周末；同一任务只冻结一个 base_time
影响     D1 多一个抽样维度；任务的时间多样性与跨天天任务都靠它
状态     已写入 03
```

### C.6 记忆按场景生成

```text
是什么   memory_initial 不抽样拼装，由 D2 依据本轮真实 s0 与画像现场生成
例子     画像"花粉过敏" + s0 有净化器 → "别开窗，闷了先开空气净化器"；
         如果 s0 没有窗户设备，就不能写"别开窗"
影响     D2 多一步一致性校验；不存在"记忆池"
状态     已写入 03
```

### C.7 TC6/TC7 全工具下发

```text
是什么   TC6/TC7 的模型看到全部 8 个工具，T1~T5 保持现状
例子     TC6 也会看到 memory；TC7 也会看到 time_control/inspect_time
影响     判定只看任务相关行为；但"该预约却立即执行""该立即执行却预约"要单独判错
状态     已写入 03
```

### C.8 轮数上限 10 → 12

```text
是什么   所有任务的交互轮数上限从 10 提到 12
例子     A 提示词从"最多 10 步"改成"最多 12 步"；runner 上限 12
影响     文档已改；B_models / B_schema / D4 / D5 / A_policy / 评测 runner 还是 10，待改
状态     文档已写入 01~03；代码待改
```

### C.9 新增空气净化器

```text
是什么   设备集新增 air_purifier，只有 turn_on / turn_off，没有 mode/level/target
例子     记忆"花粉过敏" → 模型开空气净化器；TC6 也可以预约它
影响     D0_devices、B_schema、A_policy 的设备常识、D1 造家分配都要加；老设备集不动
状态     文档已写入 01/03；设备目录与 schema 待加
```

### C.10 required_calls

```text
是什么   要求轨迹里必须发生过某类工具调用的行为检查（见 A.17）
例子     TC7C 第 2 轮必须有一次成功的 memory.read，否则即使灯关了也不给行为分
影响     替代已删除的 action_steps；C / D6 判定读，模型看不到
状态     待审
```

### C.11 tc_schema 版本号

```text
是什么   给 TC 数据结构加一个版本键（例如 "tc_schema": "v1"）
例子     新数据带 "tc_schema": "v1"；老数据没有这个键，读取逻辑不变
影响     后续字段演进时可以分辨版本；写入 D 的任务文件（scenario.tc 或 task）
状态     待审
```

### C.12 B 侧时间转换器

```text
是什么   B 内部用来解析/格式化/比较时刻的小模块（建议名 B_clock）
功能     parse("2026-10-10 09:30") → 整数分钟；format 回字符串；比较；算 7 天窗口；
         严格拒绝非补零（2026-10-9）、带秒、带时区后缀
例子     "2026-10-10 09:30" 合法；"2026-10-9 9:30"、"2026-10-10 09:30:00" 都拒绝
影响     B 与 D 侧 Oracle 共用同一份，避免两套实现漂移；B_schema 校验也用它
状态     待审（未建）
```

### C.13 scenario.tc 改名候选

```text
是什么   把承载世界初值的字段块从 scenario.tc 改名 scenario.world
例子     scenario.world = {base_time, memory_initial, session_turns, due_state}
影响     只改名字与文档，语义不变；不改的话继续叫 scenario.tc 也能用
状态     待审
```

### C.14 TaskSpec 可选字段扩展

```text
是什么   task 增加可选字段（at_time_expected、due_steps、memory_expected 等）
例子     新 task 有这些键；老 task 没有，to_dict 不输出，老 JSON 指纹逐字不变
影响     方案 4 的落地前提；改动在 B_models.TaskSpec 与同名 md
状态     待审（方案 4 相关）
```

### C.15 新目录与新文件

```text
是什么   两条新管线走独立路径，不碰老管线
例子     data_tc/（代码）、D0_templates_tc/（模板）、data_raw_tc/、data_processed_tc/、
         eval_sets/TC_20261010_v1/（评测集）
影响     老目录只读不改；新代码按需 import 老模块
状态     已写入 03
```

### C.16 13 个新提示词模板

```text
是什么   TC 管线的出题/写话/审查/评审提示词
例子     5 个 task 模板 + 5 个 request 模板 + 2 个 review 模板 + 1 个 D6 记忆评审
影响     放在 D0_templates_tc/；每份配同名中文 md
状态     已写入 03
```

### C.17 独立账本与数据集

```text
是什么   TC 数据独立落盘，不与老数据集混写
例子     TC_dataset.jsonl、TC_manifest.json；后期由 collector 与 D_dataset.jsonl 合并
影响     配额、成功率、失败码都分开统计；训练配比在合并时决定
状态     已写入 03
```

### C.18 D3 新泄露规则

```text
是什么   用户话审查新增三条硬规则
例子     规范时刻 "2026-10-10 22:00" 不得出现；记忆原文不得整句照抄；
         多轮任务不得泄露后续轮要做什么
影响     程序扫描 + 模型审查两段都要加；命中记 HARD_LEAKAGE
状态     已写入 03
```

### C.19 D6_TC7 三标签

```text
是什么   记忆类轨迹的语义复核输出三个二值标签
例子     读对（用了预置记忆）、写对（memory_expected 一致）、用对（跨轮用上了）
影响     只看工具调用与记忆快照，不采信 summary 自述
状态     已写入 03
```

### C.20 记忆一致性校验

```text
是什么   memory_initial 必须与本轮真实 s0 吻合
例子     s0 没有窗户设备 → 不允许写"别开窗"；s0 没有净化器 → 不允许写"开净化器"
影响     D2 生成记忆后立即校验，不通过就重写或失败
状态     已写入 03
```

### C.21 A 提示词装配

```text
是什么   TC 的 A 提示词 = 老 A_policy.md + TC 附加段（时间调度、记忆、多轮）
例子     老管线继续用原 A_policy.md；TC 管线拼装时追加两节，不改老文件
影响     避免两套提示词分叉；工具表按"全部 8 个"下发
状态     已写入 03
```

### C.22 影子执行复用规则

```text
是什么   影子执行必须复用 execute_action 的同一套执行内核与参数校验
例子     校验用的四道闸门与真实执行完全同源；禁止另写一个"校验专用"实现
影响     防止两套逻辑漂移导致"校验能过、真执行不过"
状态     已写入 02
```

### C.23 立即执行 vs 预约执行判定

```text
是什么   全工具下发后，要区分"现在做"和"到点做"
例子     TC6 该写预约单却直接 execute_action → 时间错误；
         TC7B 该立即执行的调暗动作却改成预约 → 执行方式错误
影响     两条都写进 C 的判定与评测口径
状态     已写入 03
```

### C.24 评测集规模与负例

```text
是什么   新任务评测集起步规模与负例构成
例子     每子类 30 条起步；含过去时间、超 7 天、跨午夜、模糊表述等负例
影响     先验证判定可靠，再决定上量；老 200 条测试做回归
状态     已写入 03
```

### C.25 forbidden/required 的 schema

```text
是什么   forbidden_actions 与 required_effects 目前只有自然语言示例
例子     ["开窗通风类动作"]、["device_bedroom_purifier on=true"]
影响     结构未定：是字符串列表还是 ACTION_CALL 过滤条件，需要拍板
状态     待定
```

### C.26 action_steps 删除

```text
是什么   删除"现在就做的动作序列"这个期望字段
例子     原来的 action_steps=[调暗台灯] 不再存在；动作是否达成改用 conditions 判，
         记忆使用改用 required_calls（待审）
影响     03 的 TC7B/TC7C 模板、04 的附录 A 都已删除该字段
状态     已删除（2026-10-10）
```

## 附录 D 已发生的改名映射（供你核对）

```text
旧名                     新名                 状态
at_expr                  time_mention         已改（01~04）
at_expected              at_time_expected     已改（01~04）
steps（任务侧）           due_steps            已改（01~04）
memory_seed              memory_initial       已改
memory_write_expected    memory_expected      已改（03 里统一）
action_steps             已删除（2026-10-10）     —
接口 time_control.steps  不变                 保留原接口字段名
```
