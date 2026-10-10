# 04 新增字段放哪：并入 task，还是独立成一块

> 背景：TC6 / TC7 引入了一批新字段（at_expr、at_expected、offset_minutes、base_time、memory_initial、memory_expected、session_turns、due_state 等）。
> 现有管线的每条记录是 s0（家）/ 画像 / task / user_request 这几个部分；本文只讨论"新字段接在哪里"，
> 不改任何已有结论（静止时间、影子执行、掉线不处理、轮数 12）。

## 0 一屏

```text
推荐：三层拆分（方案 C）

  判定真值（C / D6 要用）    → 并入 task（扩展 TaskSpec，字段可选）
                              例：at_expected、steps、memory_expected、forbidden_actions

  世界初值（B reset 要用）    → 独立成一块（scenario.tc）
                              例：base_time、memory_initial、session_turns、due_state

  生成元数据（只有 D 用）      → 只留在蓝图 / 草稿，不进 scenario
                              例：time_type、at_expr、offset_minutes

一句话：谁消费，就放在谁那一层；一个字段只放一处，不做冗余。
```

## 1 先把字段和消费者盘清

```text
字段              谁产生   谁消费                放哪（方案 C）
time_type         D 出题   D（统计/复现）         蓝图
at_expr           D 出题   D（审计）             蓝图
offset_minutes    D 出题   D（算 at_expected）    蓝图
base_time         D 抽样   B reset（→ now）       scenario.tc
horizon_minutes   常量     B / C 校验             scenario.tc（或常量）
at_expected       D 出题   C / D6 判定            task
steps             D 出题   C 判定（部分分依据）     task
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
  time_type, at_expr, offset_minutes, base_time, at_expected,
  steps, memory_initial, memory_expected, session_turns, due_state
}
```

```text
优点   一条记录只翻一个箱子；数据集自含；C/D6 只读 task
缺点   task 现在的语义是"隐藏目标，只给 C 看"；把 base_time、memory_initial
       这类"世界初值"混进去以后，B 的 reset 也要读 task，语义变模糊；
       TaskSpec 必须扩展，而且它同时被 D6、评测、统计脚本引用，改动面最大；
       生成元数据（at_expr / offset）也进 task 的话，判定侧会看到用不到的字段
```

### 2.2 方案 B：全部独立成 scenario.tc（task 完全不动）

```text
task: { intent, conditions, keep, required_observations, expected_finish }   ← 原样
tc:   { kind, time_type, at_expr, offset_minutes, base_time, at_expected,
        steps, memory_initial, memory_expected, session_turns, due_state }
```

```text
优点   完全不动老 TaskSpec、老数据、老判定；B 只读 tc；隔离最彻底
缺点   "判定真值"和"任务目标"被拆到两个箱子：C/D6 要同时读 task（conditions）
       和 tc（at_expected / memory_expected），漏读一个就判错；
       task 的概念被拆散，后续 T1~T5 若也要扩展会冒出第二套模式
```

### 2.3 方案 C：三层拆分（推荐）

```text
task: {
  intent, conditions, keep, required_observations, expected_finish,   ← 老字段不动
  at_expected, steps, memory_expected, forbidden_actions, required_effects   ← 新增可选字段
}

scenario.tc: {
  kind, base_time, horizon_minutes, memory_initial, session_turns, due_state
}

蓝图 / 草稿（不进 scenario）: { time_type, at_expr, offset_minutes }
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
  新增可选字段：at_expected、steps、memory_expected、forbidden_actions、required_effects
  to_dict 只在字段有值时输出新键 → 老 task 的 JSON 与指纹保持逐字不变
  from_dict 缺省为空 → 老数据读取路径不受影响

scenario.tc
  B.reset 只读：base_time、memory_initial、session_turns
  C 判定读：at_expected / steps / memory_expected（在 task 里）
  due_state 给结算用；没有就按当前状态影子执行（掉线不处理）

蓝图 / 草稿
  保留 time_type、at_expr、offset_minutes 与 memory 的生成理由，
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
3  task 里的新字段是平铺（at_expected 直接放在 task 下）还是再套一层 tc_truth？
   建议平铺，字段少、读取直接；如果以后字段多了再考虑分组
4  steps 是否作为判定真值参与部分分（比对模型写的 steps），还是只用于影子执行？
   影响 steps 是否必须进 task
```
