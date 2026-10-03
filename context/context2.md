# HomeFlow Demo 项目上下文（续）

> 文档用途：接 [context1.md](/root/autodl-tmp/context/context1.md)。供新对话恢复 2026-09-26 至 2026-09-27 这一轮架构讨论。
> 梳理日期：2026-09-27。
> 工作区：`/root/autodl-tmp`。
> 这一轮只改文档，没有改代码。

## 0. 这一轮在干什么

context1 写到 V1.2 能跑、V2 的 20 条 smoke 能跑但不能扩大。当时把下一轮起点定成「冻结 finish 协议」。

这一轮没有继续改 finish。用户把问题改到了数据管线本身：户型和任务语义写死在 Python 里，外部模型只负责改写一句已经写好的中文。当前目标规格在：

```text
doc/17_架构大幅度改动.md
```

17 号文档是目标，不是已实现代码。旧文件名 `17_D管线重排与轨迹评测边界.md` 已不存在。

## 1. 新对话先读什么

```text
先读本文，再按需要打开下面这些。不要从 18、19 的旧建议回改 17。

context/context1.md
  2026-09-25 之前的背景。工程事实仍有效。
  第 10.1、13、14 节「先冻结 finish」已被这一轮搁置。

doc/17_架构大幅度改动.md
  当前目标架构。第 1 节是 B 和 C：C 调用哪些口，用卧室空调走一遍。
  第 2 节是要改的数据管线。
  第 3 节：D4 是 Oracle 检验蓝图可行性；D5 生成 Scenario，调用 C 跑并记录评测。
  条件 2、3、4 才是助手对错。outcome 只留 completed / refused。

doc/14_DeepSeek候选轨迹生成与审查流水线方案.md
  现有 V2 设计。task 字段名以这里为准：
  intent、conditions、keep、required_observations、expected_finish。

doc/15_V2第二轮20条SmokeTest失败原因综合分析.md
  2026-09-24 smoke 的运行记录。

doc/16_V2当前发现问题清单.md
  当时的问题清单。finish 精炼方案写在这里，这一轮没有采纳，也没有写回代码。

doc/18_BC当前接口与接地检查.md
  第 1、2、3 节的接口事实仍可用。
  第 4 节建议的 check_grounding / D3.1 已被用户否掉。

doc/19_D2位置的论文模板与数据类型.md
  论文在 D2 这个位置写什么、之后怎么查。
  文中的 change/keep/query/refusal 是中间稿用词，17 已经改回 14 的 task 字段。
  不要按 19 去改 17 的字段名。

doc/20_SimuHome各任务用户指令五例.md
  六类任务各五句中文用户指令，用来看用户话长什么样。

代码只在需要核对接口时再读。V1、V1.1 不用读。V1.2 与 V2 才是对照对象。
```

## 2. context1 里哪些话不要再当当前任务

```text
不要做
  不要按 16 号文档去改代码里的 finish schema。
  16 写过 status=completed/refused、删 facts/answered，那是当时没采纳的代码改动。
  17 现在自己定了：expected_finish.outcome 只留 completed / refused。
  查询也用 completed，不要 answered，不要 facts。
  字段名仍用 outcome，不改成 16 的 status。代码没让改就不要改。

不要做
  不要实现 doc/18 第 4 节的 check_grounding。
  不要在写用户指令之前做接地。
  不要把 execute_action 当成只读检查。合法调用会写 state。
  发现链不要写进 B 或 C。外部模型要先查，只因为 observe_home 不返回 device_id。
  D4 复制 s0，用副本启动 B，直接 execute_action。
  这不是 18 的 check_grounding 接口。

不要做
  不要把户型库放进 B。
  不要让 DeepSeek 用中文自由句充当隐藏 conditions。
  不要把 DeepSeek 写任务、写用户指令、做指令审查算成 A。
  不要使用 git reset --hard。
```

代码和 17 号文档第 2 节现在本来就不一致。这是故意留着的：目标写在文档里，等用户明确说改代码再动。

## 3. 六个模块，V1.2 完成到哪

doc/12、doc/13 里的六个模块：

```text
A  外部交互。每轮看 context，产出 assistant turn。
B  HomeEnv。房间、设备、状态、四个家庭工具。
C  回合与评测。驱动 A 和 B，记轨迹，读隐藏任务。
D  数据生成与筛选。
E  SFT。未实现。
F  LoRA-GRPO。未实现。

V1.2 已落地 A、B、C、D 的最小闭环。
  A 当时只有 OraclePolicy。
  D 是 ScenarioGenerator 写死场景，再交 Oracle 跑轨迹。
  验收：18 项测试，140 条场景，140 条轨迹重放。
V2 把 DeepSeek 接进了 D 和 rollout，smoke 跑过，没有冻结，不能扩大。
E、F 都还没开始。当前机器是 RTX 5090 32GB，不是早期文档里的 4090。
```

HomeFlow 原文还有 MCTS-Flow。本项目不做。D4 是 Oracle 检验蓝图可行性。D5 仍是一条线性助手轨迹。

## 4. 这一轮认定的结构问题

用户认为当前 D 的最大问题不是 finish 字段，而是语义写死在程序里。

```text
现在的代码
  homeflow_demo/data/scenario_generator.py
    V1.2 户型、设备、中文或英文任务直接写在生成函数里
  homeflow_demo/data/task_blueprints.py
    V2 五类 Blueprint、writer_view、hidden_truth 也写在代码里
  homeflow_demo/data/deepseek_task_writer.py
    模型只看到 writer_view，改写一句用户话
    不负责从户型库和任务族模板里写出 task

目标
  户型目录、人物画像、任务族模板放进 D0 数据文件
  程序只采样和绑定 id，不写死某一句用户请求
  外部模型多参与生成，少把中文句子焊进 Python
```

V1.2 虽然定位是模拟器，里面同样写死了户型和任务语义。设备种类的闭集在 `homeflow_demo/env/schema.py`。具体哪一家、哪几间房，不在 B 里，现在在 D 的生成代码里。

旧 V2 流水线名字和新目标名字不是同一套，读 14、15、16 时要换算：

```text
旧 V2（14 号文档和现有代码）
  D0  代码里的 Blueprint：home、task、writer_view
  D1  DeepSeekTaskWriter，只根据 writer_view 写候选用户话
  D2  static_task_validator，程序查格式、泄露、精确去重
  D3  DeepSeekTaskReviewer，逐候选看是否忠于 Blueprint
  编译 Scenario 后，C 驱动 A 和 B 跑轨迹

新目标（17 号文档）
  D0  静态库
  D1  程序抽样出一份 s0
  D2  DeepSeek 两次：第一次写 task，第二次写用户指令
  D3  第三次 DeepSeek：只校验用户指令
  D4  Oracle 检验蓝图可行性，只看调用报错
  D5  生成 Scenario，调用 C 跑并记录评测
```

## 5. B 保持现在的实现

17 号文档第 1 节是这一轮对 B 的定稿。B 不跟着后面的数据管线改词。

```text
B = HomeEnv
  接收一份已经通过 schema 的 Scenario
  reset 复制 scenario.home
  step 只执行四个家庭工具
  不保存户型库，不读 task，不处理 finish

reset 前 ensure_valid_scenario 做双向 id 检查
  rooms[].device_ids 里的每个 id 必须存在
  该设备的 room_id 必须指回这个房间
  每台设备的 room_id 也必须出现在对应房间的 device_ids 里
  不一致就报错
  B 不补、不改、不把 display_name 翻译成 device_id
  传进来的 home 必须已经配对完成

四个工具
  observe_home
  inspect_room
  inspect_device
  execute_action

observe_home 不返回 device_id，这是观察内容
inspect_room / inspect_device / execute_action 不检查有没有先观察
execute_action 通过后会写 state，不能拿来做只读试跑
未知 id 才 UNKNOWN_ROOM / UNKNOWN_DEVICE

另外给 C，不放进给 A 的 observation
  runtime_state
  snapshot / restore / fork
```

`state` 和 `actions` 分开。当前值在 `state`。范围在 `actions` 的参数说明里。B 能解析 `minimum`、`maximum`、`step`、`enum`。

```text
state 里常见的当前值
  temperature、humidity、on、mode、target、level

actions 里的参数说明
  type、minimum、maximum、step、enum
  例：set_temperature 的 value，minimum 7.0，maximum 32.0，step 0.5

传感器
  actions 是空数组
  不能 execute_action
```

17 号文档里的卧室空调例子就是这个形状。同一份 home 里还有别的房间和设备，例子只摘了一台。

s0 不是另一套结构。s0 就是这一家的 `scenario.home`。D0 的户型目录和 D1 抽出的这一家都用这个格式。

## 6. A 和 C 的运行时关系

```text
A 只做一件事
  respond(context) -> 下一步 assistant turn
  看不见 task
  不写户型，不写 task，不写用户指令，不审查蓝图

  D4 时 Oracle 直接 execute_action，检验蓝图
  D5 时 A = 外部助手模型，C 跑轨迹
    成功轨迹证明蓝图成立，进入数据集
    今天不评测、不做 SFT、不做强化学习

  D2、D3 里的 DeepSeek 不是 A
    那些调用在轨迹开始之前，不走 respond(context)

C 负担 ReAct 循环
  EpisodeRunner.run(scenario)
    env.reset(scenario)
    每轮拼 context：observation、tools、history、protocol_feedback
    A.respond(context)
    parse_assistant_response
    finish：C 自己收下并结束，不传给 B
    其他调用：校验形状，再 env.step
    记下 observation_before、observation_after、tool_events
  轨迹结束后 EpisodeEvaluator 读 scenario.task 和 runtime_state

工具 schema 由 B 和 C 共用一份，不拆
  定义：homeflow_demo/env/tool_schema.py 的 available_tools()
  C 发给 A 时 include_finish=True，finish 由 C 处理
  B 的 observation 带同一份说明，include_finish=False
  A 可见工具是 5 个：四个家庭工具加 finish
```

C 现有评测会读隐藏 `conditions`、`keep`、`required_observations`、`expected_finish`。17 号文档第 3 节把蓝图资格和助手对错拆开了：

```text
D4  Oracle 检验蓝图可行性
  复制 s0，用副本启动 B
  直接 execute_action，不走发现链
  只看 ok / error.code，不看终态满不满足 conditions
  不过：留下失败记录，不进入 D5

D5  生成 Scenario，调用 C 跑并记录评测
  条件 2、3、4 由 C 计算，D5 落盘
  终态、required_observations、finish 契约
  outcome 只留 completed / refused
```

HomeFlow 开跑前也会丢掉解析失败或越界的条件。本项目用 D4 真跑 B 代替纸面解释，不做画像一致性，也不学 SMH 参考动作回放。

## 7. 目标数据管线

17 号文档第 2 节的图是定稿。顺序固定：

```text
D0 -> D1 -> D2 第一次 -> D2 第二次 -> D3 第三次 -> D4 Oracle 检验蓝图可行性 -> D5 生成 Scenario 并调用 C
  D2、D3 三次 DeepSeek 都不是 A
  第一次写 task，第二次写用户指令，第三次校验用户指令
  D4 复制 s0，直接 execute_action
  D5 编 Scenario，C 跑助手轨迹并写下评测
  成功轨迹进入数据集，今天不做 SFT
```

### D0 静态库

三项都落到数据文件，不写进 `_build_home` 或 `_build_blueprint` 的句子里。D0 自己不实例化 s0，不写用户指令，不生成 task。

```text
1. 户型与设备目录
   标准 scenario.home
   房间、设备、display_name、state、actions、可变化的初始状态
   id 事先配对好

2. 人物画像
   年龄、生理、健康、习惯、环境偏好
   只辅助生成，不参与 C 的成功判定
   HomeFlow 也是拿画像帮助写场景和做一致性过滤，不用画像打分

3. 任务族模板
   按 T 存放提示词
   只约束任务族和说法
   不保存「把卧室主灯关掉」这种现成请求
```

### D1 HomeMaker

```text
只读 D0 的 1
不用模型
不读画像
程序抽样并实例化一份 s0
s0 = scenario.home
不能把五间房七台设备写死在 Python 分支里
```

### D2 第一次：DeepSeek 写 task

这次不是 A。加载的是这一份 s0、一份人物画像、该任务族模板。也就是 D0 的 1、2、3，其中 1 用的是 D1 已经抽出的这一家，不是整座户型库。

输出是 14 号文档的 task JSON，外加必填的 `intent`。不写用户那句话。不调用 B。

```text
intent
  必填，不能空
  要体现画像
  例：觉得卧室太热，想睡觉

conditions
  要变成的状态
  设备必须写 device_id，加上 field、operator、value
  可以为空数组

keep
  不能变的状态
  同样是 device_id 上的谓词
  可以为空数组

required_observations
  必须观察的对象
  可以为空数组

expected_finish
  outcome 只留 completed / refused
  不要 answered，不要 facts
  refused 时写 allowed_reason_codes

查询任务
  outcome = completed
  不写 facts
  观察过没过看 required_observations

拒绝任务
  outcome = refused
  allowed_reason_codes 写出原因
  conditions 为空
  另给 Oracle 一份 probe 写入，D4 必须看到 B 报错

控制任务例子
  outcome = completed
  allowed_reason_codes 为空
```

中间稿用过 `change`、`keep`、`query`、`refusal` 四个词，还用过「显示名和动作槽位」。用户认为这两个说法和程序绑定混在一起，看不懂。已经废掉。隐藏目标就是上面这份 JSON。`query` 不是用户的第一句话。`refusal` 也不是一句自然语言，拒绝写在 `expected_finish` 里。

D2 第一次写出的是结构化谓词，不是「卧室空调调到 24 度」这种自由句。用户指令是下一次调用才写的。

### D2 第二次：DeepSeek 写用户指令

这次也不是 A。读 `intent`、这份 task，以及一份用户指令模板。不读户型库，不读整份画像库，不调用 B。

17 号文档里的模板已经写成虚线框，要求是：

```text
要写
  一条口语化的用户请求
  说全 intent
  说全 conditions、keep、required_observations
  设备只用 s0 里的 display_name

不得出现
  device_id、room_id、action 名、reason_code
  field、operator、subject_id
  task 里没有的设备或动作
  工具调用 JSON
```

doc/20 用来看 SimuHome 的用户话长什么样。六类各五句，都已译成中文：QT1 问状态，QT2 只说感受、不点动作名，QT3 点设备和数值，QT4-1 定时，QT4-2 事件完成后再动作，QT4-3 多设备互相等待。那是用户话的语气参考，不是要抄进 D0 的现成请求。

### D3 第三次 DeepSeek：只校验用户指令

没有 D3.1，也没有 D3.2。这是进 D4 前第三次、也是最后一次 DeepSeek。D4 的 Oracle 不是 A。D5 里跑轨迹的助手模型才是 A。

```text
程序
  查用户指令有没有写出 device_id、action 名、reason_code

第三次 DeepSeek
  只读 task、intent 和用户指令
  查有没有说全 task
  查有没有多加设备或动作
  不读 D0，不调用 B，不做接地
```

三步这个词不要再用。早期草稿把「程序绑定、画像一致性、指令覆盖」收成 D3 的三步，后来预接地被取消，程序绑定也不再单列。现在的 D3 就是上面这两项指令校验。

### D4 和 D5

```text
D4 在 D3 之后、D5 之前
  Oracle 检验蓝图可行性
  复制 s0，用副本启动 B
  直接 execute_action
  只看调用报错，不看终态
  不过：留下失败记录，不进入 D5

可跑蓝图 = <s0, 用户指令, task>
D3 不通过或 D4 不通过：留下失败记录，不生成 Scenario
  旧代码没有 task_generation_failed 路由，Blueprint 会静默消失
  新管线要求失败要留下记录

D5
  把可跑蓝图编成 Scenario
  调用 C 驱动 A 和 B
  一条轨迹，不超过 max_turns
  不做 MCTS，失败不分叉
  execute_action 照常真写入
  C 计算条件 2、3、4，D5 写下记录
  成功轨迹证明蓝图成立，进入数据集
  今天不评测、不做 SFT、不做强化学习
```

17 号文档图后面仍留着四段说明：A 的当前文件、B 的当前文件、schema 共用方式、尚未实现。以磁盘上的 17 号文档为准，不要把这四段当成已经被删掉。

尚未实现的是：D0 数据文件、D1 从目录采样、D2 先 task 后指令、D3 第三次 DeepSeek 只校验用户指令、D4 Oracle 检验蓝图可行性、D5 生成 Scenario 并调用 C、失败蓝图的独立记录。V2 现有的 `writer_view` 中文改写不是这条管线的目标。

## 8. 和两篇论文怎么对齐，哪里故意不对齐

doc/19 写于字段还叫 change/keep/query/refusal 的时候。下面只保留仍然有效的论文事实。

```text
HomeFlow
  先有生活场景，再拆原子任务，再写对话里的用户查询
  原子任务的可执行部分是 device(id).属性 的布尔表达式
  查询类型是扰动标签：意图清不清楚、有没有噪声、单设备还是多设备、动与动是否有依赖
  蓝图里的「查询」已经是一句任务话，不是传感器事实
  画像是输入元信息：年龄、性别、生理、健康、习惯、温度和照明偏好

  轨迹开始前，原文会做三次过滤
    条件能解析，设备必须存在，否则丢掉
    数值必须落在硬件范围内，否则丢掉
    GPT-5 看条件、意图、画像是否互相矛盾
  轨迹进行中，每步对当前状态重算这些表达式
  动作审计器另查助手的动作，不改蓝图

SMH-Bench 正文 3.3.2
  先写结构化任务规范，再写用户指令

SMH-Bench 附录 B
  和正文顺序不一致
  实际字段是：家庭状态 -> 模板约束下的用户指令 -> 参考助手 JSON -> 回放抽出标签
  标签是 {设备ID, 属性, 值}，再加一条评判器表达式
  以附录里的字段为准，正文只给了步骤名
  接地方式是把参考动作真执行一遍，看终态

本项目这一轮的取舍
  先写 task，再写用户指令
    这点靠近 HomeFlow 和 SMH 正文，不靠近 SMH 附录「先有用户话再回放标签」
  task 用 14 号文档已有的 JSON 谓词
    不用 HomeFlow 的条件字符串，也不用 change/keep/query/refusal
  画像只进 D2 第一次，帮助写 intent
    不进 D1，不进 C 的成败判定
  D4 复制 s0，直接 execute_action 看报不报错
    报错就丢掉，不进入 D5
    不学 SMH 的参考动作回放抽标签
    也不另做 18 的 check_grounding 接口
  D5 生成 Scenario，调用 C 跑并记录评测
  outcome 只留 completed / refused，查询也用 completed
```

## 9. 旧 V2 审查，这一轮看到的事实

这些是代码和 15、16 号文档里的事实，不是新管线的步骤。

```text
旧 D2 static_task_validator 在精确去重之前做泄露检查
  硬泄露：blueprint_id、room_id、device_id
  内部词：action 名，或 allowed_reason_codes 里的码
  工具 JSON 片段：device_id、room_id、name、arguments 这类调用碎片
  然后把文本做空白压缩和大小写规范化，查 EXACT_DUPLICATE

这三项不是同一件事
  硬泄露看的是实例 id
  内部词看的是动作名和拒绝原因码
  工具 JSON 看的是调用片段，不要求这三个词刚好就是某一台设备的 id
用户看过实现后认为三者有重叠，但不再要求改成两项。

2026-09-24
  60 个候选里 5 个被判 EXACT_DUPLICATE
  去重是跨 Blueprint 的字符串相同，不看隐藏任务是否相同
  语义相近但措辞不同的，这条规则发现不了
  用户的判断：去重之前那些硬检查大多能通过，真正挡掉候选的不是它们

旧 D3 DeepSeekTaskReviewer
  逐候选审查，比较的是候选用户话和 Blueprint 里已经写死的任务
  输出 accept、category_match、target_covered、extra_intent、
  soft_leakage、semantic_duplicate_group、review_codes
  semantic_duplicate_group 只是模型字段
  build_v2_dataset.py 没有拿它做候选间语义去重
  每个 Blueprint 取第一个 accepted 候选
  全部拒绝时不编译 Scenario
  没有单独的 task_generation_failed 路由
  20 条尝试因此可以静默变成 16 条 Scenario

多设备任务的典型失败
  三条候选各说一件事：只关灯、只调空调、只说另一盏灯不动
  没有一条覆盖完整目标，旧 D3 全拒绝

writer_view
  是代码写好后交给模型的改写视图
  模型不根据完整 home 和 task 从零写规范
  这就是用户说的「程序写死，模型只改写」
```

16 号文档后半还有几项这一轮没有重新决定：

```text
seed 和 split 先留着
required_observations 到底是过程约束，还是只要求答案有观察依据
查询的自然语言答案和结构化 facts 各算什么
2026-09-24 的 TrajectoryJudge 大量 finish_reason=length，有效票不足
_route_record 先看 evaluation.success，裁判 system_failure 可能被普通 failed 盖住
candidate.category 检查已经在 context1 记录的那次修改里删掉了
```

## 10. 当前代码入口

和 context1 第 11 节相同，这一轮没有改这些文件。

```text
B
  homeflow_demo/env/home_env.py
  homeflow_demo/env/state_engine.py
  homeflow_demo/env/schema.py
  homeflow_demo/env/models.py
  homeflow_demo/env/tool_schema.py
  homeflow_demo/env/predicates.py

C
  homeflow_demo/eval/episode_runner.py
  homeflow_demo/eval/episode_evaluator.py
  homeflow_demo/eval/deterministic_audit.py
  homeflow_demo/eval/deepseek_trajectory_judge.py

A
  homeflow_demo/agents/oracle_policy.py
  homeflow_demo/agents/deepseek_policy.py
  homeflow_demo/agents/deepseek_client.py

现在的 D，仍是旧 V2
  homeflow_demo/data/scenario_generator.py
  homeflow_demo/data/planner.py
  homeflow_demo/data/task_blueprints.py
  homeflow_demo/data/deepseek_task_writer.py
  homeflow_demo/data/static_task_validator.py
  homeflow_demo/data/deepseek_task_reviewer.py
  homeflow_demo/data/build_v1_2_dataset.py
  homeflow_demo/data/build_v2_dataset.py
```

每个 Python 模块有同名中文 `.md`。改代码时必须一起改。

## 11. 新对话要记住的事实

```text
1. 当前工作是把数据管线改成 17 号文档，不是继续冻结 finish。
2. B 不动。s0 就是 scenario.home。reset 只检查双向 id，不翻译中文名。
3. 范围在 actions，当前值在 state。
4. A 只负责轨迹里的下一步。D2 和 D3 的 DeepSeek 不是 A。
5. C 负责拼 context、派工具、保存观察、处理 finish，并用条件 2、3、4 判对错。D5 调用 C 并写下记录。
6. D0 有三项。D1 只读第 1 项。D2 第一次写 task JSON。D2 第二次按模板写用户指令。
7. D3 是第三次 DeepSeek，只查指令泄露和说全没有。D4 是 Oracle 检验蓝图可行性，不调大模型。
8. 可跑蓝图是 <s0, 用户指令, task>。D3 或 D4 失败要留记录，不进 D5。
   expected_finish.outcome 只留 completed / refused，不要 answered，不要 facts。
9. doc/18 第 4 节和 doc/19 里的 change/keep/query/refusal 是被替换掉的中间稿。
10. 代码还是 V1.2 写死场景加 V2 writer_view 改写。没让改代码就不要改。
```
