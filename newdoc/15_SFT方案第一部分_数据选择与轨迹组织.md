# SFT 方案第一部分：数据选择与轨迹组织

> 日期：2026-10-04。
> 范围：只分析学什么、用什么数据、轨迹如何组织，并用现有真实样本解释。暂不写数据转换代码、训练命令、依赖安装、参数配置、LoRA 配置和训练执行步骤。
> 事实来源：读取千条批次的实际 JSONL，核对现行 A / C / D5 代码；通用训练原理参考文末官方资料。
> 本文中的“建议”尚未执行；原始轨迹和数据集没有修改。

## 1 先确定 SFT 要学什么

这轮 SFT 的目标是让小模型接替 A：根据用户请求和已经收到的工具回执，输出下一次合法工具调用，或者输出符合契约的 finish。家庭状态继续由 B 维护，回合调度和成功判定继续由 C 负责。

```text
用户请求 + 已公开的工具能力 + 此前交互历史
                         |
                         v
                    被训练的 A
                         |
                         v
           一次 JSON 工具调用，或一次 finish
                         |
                         v
               C / B 执行，返回观察
                         |
                         v
                   A 再做下一步
```

要监督的是工具选择、设备和参数选择、跨轮任务记忆、根据范围拒绝、根据读数回答，以及正确结束。这里只需要现有轨迹里的助手输出；不要求模型生成隐藏 task，不要求模型预测全屋终态，也不要求模型模仿环境写工具回执。

三种本地模型可以学习同一套业务消息：Qwen3-0.6B、Qwen2.5-1.5B-Instruct、Qwen3.5-2B。训练侧使用已有的 HF 原始权重，GGUF 留给推理评测。Qwen3.5-2B 的原始包有视觉部分，但当前任务和数据都是文本，不增加图像样本；模型加载和参数更新方式留到后续讨论。

## 2 现在实际有哪些数据

主候选池是 `new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl`。本次直接读取这个文件及同批轨迹总表，统计如下。

| 类别 | 合格轨迹 | 助手决策轮数 | 每条轨迹轮数 | 有错误回执的合格轨迹 |
|---|---:|---:|---|---:|
| T1 单设备控制 | 200 | 1022 | 4–7 | 0 |
| T2 多设备控制 | 200 | 1793 | 6–10 | 0 |
| T3 模糊意图 | 200 | 1230 | 5–10 | 0 |
| T4 危险拒绝 | 200 | 806 | 4–5 | 6 |
| T5 环境查询 | 200 | 767 | 3–9 | 0 |
| 合计 | 1000 | 5618 | 3–10 | 6 |

1000 行的 C-1 到 C-4 均为 true；T1 / T2 的 D6 均为“跳过”，T3 / T4 / T5 均为“对”。同批 `D5_trajectories.jsonl` 有 1268 行，其中 268 行未进集，不能把总表全部当成正确示范。

轮数包含最后的 finish。T2 有 100 条恰好在第 10 轮结束；它们有 finish、没有 truncated，不能仅因为达到轮数上限就删除。

另外，1000 条数据只有 850 种不同的用户请求文字，但按“家庭状态 + 用户话 + 隐藏 task”联合比较，有 1000 个不同场景。同一句“卧室现在多少度”落在不同家庭和不同传感器读数上，是不同的训练问题。仅按用户话去重会误删这些样本。

### 2.1 第一轮主 SFT 建议用哪些

建议先把“程序和 D6 判合格”与“适合作为直接模仿的行为”分开，再选择训练候选池。

```text
千条 D_dataset：1000 条，5618 个助手决策轮
  |
  +-- 无错误回执：994 条，5588 个助手决策轮
  |      -> 第一轮主 SFT 的候选池
  |      -> 再从中按完整场景划分训练 / 验证
  |
  +-- 出错后恢复：6 条，全部为 T4
         -> 单独保留，暂不按整条正例混入主 SFT

同批轨迹总表另外 268 条未进集
  -> 用于失败分析，不直接监督它们的原始动作
```

994 条候选池的类别数量是 T1 / T2 / T3 / T5 各 200，T4 为 194。这个数字是划分训练 / 验证之前的规模，不能同时把全部 994 条用于训练，又声称其中一部分是未见过的验证集。

六条恢复轨迹的编号是 `sc_T4_016`、`sc_T4_041`、`sc_T4_052`、`sc_T4_077`、`sc_T4_151`、`sc_T4_201`。每条都有 5 轮，包含一次被 B 拒绝的 `BAD_REQUEST`。

以 `sc_T4_016` 为例：用户要求主卧空调设到 34 度，助手已经 inspect 到最高 32 度，却仍然执行了 `set_temperature(34)`；B 拒绝且未改状态，助手随后给出正确拒绝，所以最终标签仍然全过。

```text
这条轨迹的原始过程
  发现房间 -> 找到空调 -> 读到上限 32
  -> 试写 34，被 B 拒绝
  -> finish refused，说明不能设到 34

若整条都作为正例监督
  读到上限后仍试写 34，也会成为模型要模仿的目标

第一轮希望建立的习惯
  读到上限 32 -> 直接拒绝 34，不试写越界值
```

这六条可以在后续用于“见到错误反馈以后如何纠正”的专项数据。但那需要重新定义哪些输出受监督；不能删掉错误动作、保留它引出的错误回执，再假装这是原本的正常交互。本篇不做这种改造。

994 条只能称为“无错误成功候选池”。没有错误回执并不证明策略最短，也不证明所有额外动作都符合用户意图；C-2 只检查 conditions 和 keep。后续仍应抽查冗余动作、未请求的写入和总结是否准确，不在这里宣布数据已经最优。

### 2.2 其他现有文件怎么用

```text
D4_blueprints.jsonl
  有家庭、用户话、隐藏目标；没有助手示范
  -> 不能直接充当这轮行为 SFT 的回答数据

D5_trajectories.jsonl
  成功和失败混在一起
  -> 审计与失败分析；主训练候选优先从 D_dataset 取

data_static/D0_templates/A_policy.md
  助手的公开规则
  -> 用来恢复 system；公开工具表填入其中

eval_sets/quota50_20261002_v2/
  已有 250 条评测任务及独立真值文件
  -> 保留做原有对照，不把参考答案并入主训练

fewshot_by_task/
  过去用于评测提示的示例
  -> 不默认塞进每条训练样本，避免重复示例占据监督内容
```

本次还核对了千条候选池与这 250 条评测数据：按房间 / 设备排序后，联合比较家庭状态、用户话和隐藏 task，精确重叠为 0；两边共有 29 种相同的用户话文字。这个检查不包含语义近重复，因此只支持“未找到完整场景的精确重复”，不支持“评测数据完全独立于训练分布”。

若按轮切分，必须先按完整场景划分训练 / 验证，再在各自集合内切分。同一条轨迹的前半段进入训练、后半段进入验证，会让验证条件中出现已经训练过的交互，不能算独立场景的验证。

## 3 原始轨迹哪些字段能进入 SFT

当前数据的一行是审计包，结构如下。这里画的是实际字段层级，不是已经转换好的训练文件。

```text
一行 D_dataset
  scenario
    scenario_id / blueprint_id
    home                  完整 s0
    user_request          用户原话
    task                  隐藏目标
    episode_config
  record
    scenario_id
    turns[]
      turn
      observation_before
      tool_calls[]        name / arguments / call_id
      events[]            call_id / tool_name / arguments / result / state_diff
      observation_after
    final_state
    finish
    protocol
  labels                  C-1..C-4
  category
  d6 / d6_votes
```

SFT 消息必须按 A 在当时真正能看到的内容组织。整包序列化给模型，会把隐藏目标和未发现设备一起暴露出去。

| 原始内容 | 在 SFT 中的用途 | 是否进入模型对话 |
|---|---|---|
| `scenario.user_request` | 第一条 user 消息 | 是 |
| 公开 A 提示词和工具表 | system 消息 | 是，开头一次 |
| `turns[].tool_calls` 的 `name / arguments` | 下一次助手输出 | 是，写成 JSON 文本 |
| 当时给 A 的工具回执 | 后续 `user` 观察消息 | 是，按时间顺序 |
| `scenario.home` | 重放、分组、查重、审计 | 不整体加入；只保留实际观察公开的部分 |
| `scenario.task` | 资格判断和审计 | 否，包括 intent、conditions、keep 等全部隐藏字段 |
| `record.final_state` | 终态审计 | 否；实际执行回执中的 state_after 可以保留 |
| `labels / category / d6 / d6_votes` | 筛选、分层统计、追溯 | 不作为模型输入或回答 |
| `call_id / scenario_id / blueprint_id` | 追溯关联 | 不作为模型需要生成的正文 |

例如，某个设备在 `scenario.home` 中存在，但到第 3 轮才被 inspect 出来，就不能从第 1 轮起把它的状态和参数范围放进输入。隐藏 `keep` 也不能直接喂给助手；需要保持哪个设备，应当从用户那句“某某别动”里学习。

### 3.1 沿用当前实际消息协议

`A_policy.py` 的真实请求是 system、用户原话、助手 JSON 文本，再追加 `user` 角色的 `observation:` 文本。C 记录中的 `tool_calls` 字段不等于训练数据也必须使用 API 原生 `tool_calls` 字段。

```text
system     现行 A_policy 正文 + 公开工具 schema
user       用户请求
assistant  {"name":"observe_home","arguments":{}}
user       observation: {"ok":true,"data":{...},"error":null}
assistant  {"name":"inspect_room","arguments":{"room_id":"..."}}
user       observation: ...
...
assistant  {"name":"finish","arguments":{...}}
结束
```

assistant 的 `content` 是 JSON 字符串；里面只需要 `name`、`arguments`。不要把审计用的 `call_id` 一起变成生成目标，也不要要求模型复述整个 event。

成功回执取当前 A 会接收的 `last_tool_result` 内容。错误时 A 接收 C 整理的 protocol_feedback，即 `ok / code / message / hint`，未必是完整原始错误 event。需要恢复的是这套可见反馈，不是把所有 events 和 observation 整包重复追加。

finish 由 C 收下后直接结束，不会再进行下一次 A 调用。因此训练对话也应停在最后的 assistant finish，不添加一条虚构的“环境确认 finish 成功”。

根目录旧文档 `21_回合记录如何变成SFT与RL训练数据.md` 提出了逐轮监督的正确方向，但其 SFT 示例采用 `role=tool` 和消息级 `tool_calls`。本轮先沿用现行运行代码的 JSON 文本协议。若以后改成模型原生工具协议，需要同时改训练和推理接口，那是另一项设计。

## 4 整条轨迹可以直接成为多轮 SFT 样本

建议以一条完整轨迹为一个多轮样本，system、用户请求和全部按时间排列的交互都保留，监督其中每一条 assistant 输出。这里的“整条”指完整对话，环境和用户部分只作为条件，不要求模型生成。

### 4.1 真实例子：冰箱调高一点

以下来自 `sc_T1_001`。用户话、动作、初始读数和 finish 正文取自真实轨迹；观察清单为方便阅读做了节选，`...` 不代表训练时要删除那些内容。

```text
system
  现行智能家居助手规则 + 五个公开工具

user
  冰箱不用太冷，把厨房冰箱温度调高一点吧。

assistant 1
  {"name":"observe_home","arguments":{}}
user 观察 1
  observation: {"ok":true,"data":{"rooms":[厨房、卧室、客厅等房间]},"error":null}

assistant 2
  {"name":"inspect_room","arguments":{"room_id":"room_kitchen"}}
user 观察 2
  observation: 厨房设备清单，包含 device_kitchen_fridge 等

assistant 3
  {"name":"inspect_device","arguments":{"device_id":"device_kitchen_fridge"}}
user 观察 3
  observation: 冰箱 state={on:false,target:7.5}；
               set_temperature 的范围 2.0–8.0，step=0.5；其余公开能力保留

assistant 4
  {"name":"execute_action","arguments":{"device_id":"device_kitchen_fridge","action":"set_temperature","params":{"value":8.0}}}
user 观察 4
  observation: {"ok":true,"data":{"device_id":"device_kitchen_fridge","action":"set_temperature","state_after":{"on":false,"target":8.0},"verified":true,"changed":true},"error":null}

assistant 5
  {"name":"finish","arguments":{"summary":"已把厨房冰箱温度从 7.5 调高到 8.0（上限）。","outcome":"completed"}}
```

这里有 1 个家庭任务、1 条训练对话、5 个助手决策目标。用户没有说“设到 8.0”，这个数字来自先前 inspect 的当前值、范围和步长，正是模型需要学会的条件化行为。

输入与监督的关系可以这样看：

```text
对话位置       system   用户话   A1   O1   A2   O2   A3   O3   A4   O4   A5
作为上下文        是       是     是   是   是   是   是   是   是   是   是
预测目标          否       否     是   否   是   否   是   否   是   否   是

A = assistant 输出；O = 环境观察
“不作为预测目标”仍然允许后续助手读取该位置
```

SFT 的基本目标可以写成：让每个 `a_t` 的文本，在公开规则、用户请求和此前 `a / observation` 历史条件下具有更高概率。框架中的 assistant-only supervision 和 completion-only supervision 是实现这类目标的通用形式，相关官方说明见参考 [R1]。

### 4.2 整条对话放在一个样本中，会提前看见后面的回执吗

使用因果语言模型时，每个位置只读取它前面的内容，后面的回执不能被前面的助手输出看到 [R2]。上例训练 A4 时，它能读取 O3 中的 7.5、8.0 和 0.5，但不能读取 O4 里“执行成功”的结果。

所以，整条多轮样本仍然在学习逐次决策。推理时模型每次只生成一条 JSON，环境执行后再把回执追加回来；不让模型在一次回答里凭空生成完整工具链和环境结果。

训练阶段提供正确历史作为上下文，这通常称为 teacher forcing。它不能保证模型在推理时出现偏离后也能恢复，因为那时历史可能已经不同于示范。这个差异是后续环境评测要检查的风险，不应靠向训练输入提前塞 final_state 来消除。

## 5 按轮切分也可以，但每一轮必须带完整前缀

“按轮切分”有两种差别很大的含义：一种只保留最后一次观察，另一种保留本轮之前的完整对话。这里推荐的备选只指后者。

### 5.1 正确的切法：完整历史条件，当前一步答案

把上面的 5 轮改成 5 个前缀样本时：

```text
样本 1
  条件：system + 用户话
  目标：A1 observe_home

样本 2
  条件：system + 用户话 + A1 + O1
  目标：A2 inspect_room

样本 3
  条件：system + 用户话 + A1 + O1 + A2 + O2
  目标：A3 inspect_device

样本 4
  条件：system + 用户话 + A1 + O1 + A2 + O2 + A3 + O3
  目标：A4 execute_action

样本 5
  条件：system + 用户话 + A1 + O1 + A2 + O2 + A3 + O3 + A4 + O4
  目标：A5 finish
```

前缀里的旧 assistant 消息仍然是上下文，但在这个前缀样本中不再次作为预测目标。否则 A1 会在样本 1 到 5 中被重复监督，A5 却只被监督一次，较早的发现动作被人为加重。

从条件与目标的内容看，整条多轮与完整前缀切分都能覆盖同一组逐步监督。保持相同目标 token 权重和归一化方式时，二者才可以视为同一个监督目标的不同组织方式；若改成按轮平均或按样本平均，权重也会改变。

### 5.2 只留最后一次观察，为什么不够

真实 T2 样本 `sc_T2_002` 的用户话是：

> 晚上我在书房看材料，把卧室电视关掉，客厅空调调低一点，书房加湿器别动。

它的 8 轮顺序如下：

```text
1  observe_home
2  inspect_room(卧室)
3  inspect_room(客厅)
4  inspect_device(卧室电视)：on=true
5  inspect_device(客厅空调)：target=31.0，范围 7–32，step=0.5
6  execute_action(卧室电视 turn_off)
7  execute_action(客厅空调 set_temperature 30.5)
8  finish：电视已关，空调调低一档，加湿器未动
```

第 7 轮之前，最新回执来自第 6 轮，只说明电视关了。如果切分时只保留这条最新回执，就丢掉第 5 轮的空调初值和步长，也丢掉用户对加湿器“别动”的要求；这样的输入不能解释 30.5 是如何得出的。

完整历史还区分“哪个子任务已经做完”。只给用户话和当前设备状态，模型可能再次去关电视，或者处理空调后忘记交 finish。因此不能把每个动作摘出来，组成互不相关的“设备 JSON -> 动作 JSON”训练对。

### 5.3 本轮优先选哪种

| 组织方式 | 上下文与监督是否完整 | 主要代价 | 本轮建议 |
|---|---|---|---|
| 整条多轮对话，监督全部 assistant 输出 | 完整 | 长轨迹的整段长度需要核对 | 优先 |
| 按助手轮切分，保留完整前缀，只监督当前轮 | 完整 | 较早上下文重复，后几轮样本仍然很长 | 备选 |
| 只拿最后一个 observation 配动作 | 常常不完整 | 丢失用户要求、能力信息和任务进度 | 不采用 |
| 把整条轨迹连环境回执都放进一次 assistant 回答 | 与当前交互不一致 | 模型学会自编环境结果 | 不采用 |

目前轨迹最多 10 轮，但轮数不等于 token 长度；设备能力表和工具 schema 也会占长度。本次没有按三个模型的 tokenizer 统计 token 分布，不能据此宣称整条都放得下某个上下文上限。

若后续发现长样本有问题，完整前缀切分能够去掉某一目标之后的未来消息，但最后一轮的前缀仍接近整条对话长度，不能保证单靠切分就解决长度问题。不要先把末尾截掉：那样容易丢掉 finish，恰好破坏要学习的结束行为。

## 6 五类任务分别提供什么监督

五类都要保留，它们覆盖的行为不同。SFT 的目标不仅是输出格式合法，也包括从公开信息得到正确动作和正确结束。

```text
T1：明确或方向性的单设备控制
  sc_T1_001：冰箱调高一点
  -> 读当前 7.5、step 0.5、上限 8.0 -> 合法设置 8.0 -> completed

T2：记住多设备目标，以及明确要求不动的对象
  sc_T2_002：电视关掉、空调调低、加湿器别动
  -> 跨房间发现 -> 分别执行 -> 汇总已完成的子任务

T3：从口语意图选择合理设备行为
  sc_T3_009：“嗓子干得难受，翻来覆去睡不踏实。”
  -> 找到卧室加湿器 -> turn_on -> completed
  -> 输入不包含隐藏 intent 或 condition，让模型根据用户话和观察学习

T4：先读能力范围，再直接拒绝
  sc_T4_006：热水器调到九十度
  -> inspect 得到上限 75 -> 不 execute -> refused + OUT_OF_SAFE_RANGE

T5：读到什么，再回答什么
  sc_T5_008：书房现在温度多少、湿度多少
  -> inspect_room 得到 temperature=23.4、humidity=68.8
  -> finish summary 回答 23.4 度、68.8%，不写设备
```

T5 的 `required_observations` 是空数组，但这不意味着训练时可以删掉观察。真实回答里的数值来自工具回执，D6 判断的是它有没有根据读数回答完整；D6 标签只用于选择示范，不需要模型输出“对”。

T4 的拒绝也是一条正常的 assistant JSON。`outcome=refused` 和 `reason_code` 应当和 summary 一起被监督，不能只留下“不能这样做”的自然语言。其余完成任务也要监督 `outcome=completed`；仅教 summary 会重复出现“动作做对，finish 契约没过”的旧问题。

虽然每类都有 200 条，T2 已占全部助手决策轮的 31.92%，T4 为 14.35%。这只是轮数比例，不是实际目标 token 的比例；finish 的文字长度也不同。所以“每类任务条数均衡”不能直接等同于“训练损失权重均衡”。本篇先保留这个差异，不擅自通过重复 T4 或砍短 T2 来改变分布。

## 7 消息格式与停止行为需要保持一致

业务层统一使用 `role / content`，content 内保持现有 JSON 调用格式。token 层则由各模型自己的聊天模板表示角色和消息边界；官方 tokenizer 接口也把角色消息与 token 序列转换、助手区域识别区分开来 [R3]。不能把某个模型的特殊 token 当成所有模型通用的正文。

本轮不加“思考过程”标签。当前记录只有解析后的工具调用和回执，没有对应的教师思维链；训练和实际推理都应保持每轮一个 JSON 的业务契约。模型自身的非思考模板与停止边界怎样对齐，留给后续执行设计确认。

finish 是“结束整个家庭任务”的业务动作；每条 assistant 消息的结束边界是“这次输出结束，等待工具”的对话边界。两者都要保留正确语义，不能把单轮结束理解成家庭任务已经完成。

“只监督助手”也不是看到 messages 里有 `role=assistant` 就自动成立。官方训练说明要求模板能够识别助手生成区域 [R1 / R3]。后续必须检查真实监督位置；本篇确定的是哪些内容应该被预测，不宣称三个模型的现成模板已经验证过。

## 8 第一部分的建议与未确认边界

```text
数据来源
  千条 D_dataset -> 994 条无错误成功候选 -> 场景级训练 / 验证划分
  6 条 T4 出错恢复单独保留，268 条未进集轨迹用于分析

学习对象
  下一次 assistant JSON：工具选择、参数、总结和 finish 契约
  系统规则、用户请求、工具回执提供条件，不让模型生成环境

样本组织
  首选：一条轨迹 = 一条完整多轮对话；监督各 assistant 输出
  备选：每个助手轮 = 完整前缀 + 当前目标；只监督当前目标

信息边界
  公开观察按发生顺序进入；隐藏 task、整屋 s0、最终真值不喂给 A
```

已核实的是数据数量、字段、代表样本、错误回执和联合精确重复情况；994 条主候选池与整条多轮组织是设计建议。token 长度、模板的助手区域、实际监督权重，以及无错误轨迹中是否还有不理想行为，仍需后续确认。

这份数据足够提出一个行为 SFT 基线，但当前检查不能证明 994 条一定足以训练出稳定策略。模型在环境里的成功率、拒绝行为和跨轮完成能力，最终还需要用未参与训练的任务观察；不能用训练 loss 下降替代这些结论。

## 9 依据与可核对位置

本地依据：

```text
实际样本与计数
  new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl
  new_demo/runs/quota200_20261004_v2/data_processed/D5_trajectories.jsonl
  new_demo/runs/quota200_20261004_v2/data_processed/D_manifest.json

消息与回合的真实实现
  new_demo/agents/A_policy.py
  new_demo/eval/C_episode_runner.py
  new_demo/data/D5_run.py
  new_demo/data/D_copy_dataset.py
  new_demo/data_static/D0_templates/A_policy.md

评测数据与既有讨论
  new_demo/eval_sets/quota50_20261002_v2/tasks.jsonl
  new_demo/eval_sets/quota50_20261002_v2/ground_truth.jsonl
  21_回合记录如何变成SFT与RL训练数据.md
  newdoc/10_数据合成管线_全流程.md
  newdoc/11_模块功能与输入输出示例.md
  newdoc/13_千条批次T2T3失败对比与样例.md
  source_server.md
```

外部只参考官方资料，核对日期为 2026-10-04。这里只引用数据形式、监督范围和因果可见性，不据此锁定训练框架版本或执行配置。

```text
[R1] Hugging Face TRL，SFT Trainer
     https://huggingface.co/docs/trl/main/sft_trainer
     参考：会话数据、助手区域监督、prompt / completion 的监督边界。

[R2] Hugging Face Transformers，Causal language modeling
     https://huggingface.co/docs/transformers/v4.48.2/en/tasks/language_modeling
     参考：预测下一 token 时只读取左侧历史。

[R3] Hugging Face Transformers，tokenizer 源码与接口说明
     https://github.com/huggingface/transformers/blob/main/src/transformers/tokenization_utils_base.py
     参考：角色消息经聊天模板变成 token 序列；助手区域需要可识别的模板标记。
```
