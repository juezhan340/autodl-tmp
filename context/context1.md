# HomeFlow Demo 项目上下文

> 文档用途：供新对话快速恢复项目背景、设计脉络、代码状态和下一步工作。
> 梳理日期：2026-09-25。
> 当前工作区：`/root/autodl-tmp`。

## 0. 一句话概括

本项目不是要完整复刻 HomeFlow 论文的大规模训练系统，而是从 SMH-Bench、HomeFlow 和 SimuHome 中提取一条可验证、可重放、能支持 SFT 与 LoRA-GRPO 的最小智能家居实验闭环：

```text
程序生成家庭状态和隐藏任务
        -> 模型或 Oracle 通过工具与 HomeEnv 交互
        -> C 管理 assistant turn、工具执行、结束和评测
        -> 生成可审计成功轨迹
        -> SFT
        -> 再以模型作为 A 进入 C，使用环境 reward 做 LoRA-GRPO
```

当前已经完成的是环境、回合管理、确定性评测、Oracle 数据和第一版 DeepSeek 数据流水线；真正的 1.5B SFT、在线 rollout 和 LoRA-GRPO 尚未开始。

## 1. 最初研究目的

项目最初有三个相互关联的目标。

```text
目标 A：理解并拆解 SMH-Bench / HomeFlow 的实验架构
目标 B：实现一个规模受控、结构清楚的 HomeEnv Demo
目标 C：验证小模型能否通过高质量工具轨迹进行 SFT，并继续进行环境强化学习
```

更具体的研究问题是：

```text
在一个轻量、符号状态、确定性反馈的智能家居环境中，
经过 SFT 的 1.5B 级模型能否学会：
  发现房间和设备
  阅读公开动作能力
  按参数边界执行控制
  处理多设备目标和模糊意图
  拒绝越界或只读设备写入
  在有限 turn 内正确结束任务
并在环境 reward 下继续提升？
```

项目从一开始就限定为 Demo 和科研入门规模，不追求 HomeFlow 论文中的 MCTS-Flow、96 张 H20 级别训练资源或完整 SmartHome-Bench 数值复现。

## 2. 论文和外部源码分析形成的判断

### 2.1 SMH-Bench 与 HomeFlow 的关系

早期分析记录在：

```text
doc/01_SMH-Bench与HomeFlow实验架构复现分析.md
doc/02_HomeEnv核心谱系与两篇论文模拟器分析.md
doc/03_HomeFlow中HomeEnv面向SFT与强化学习的调整分析.md
```

核心判断是：两篇论文很可能属于同一套 HomeEnv 核心谱系，但没有公开代码、commit 或版本号能够证明它们使用完全相同的模拟器实现。

这里的“核心谱系”指共同继承的工程思想：

```text
家庭 / 房间 / 设备 / 组件 / 属性 / 当前值
        -> 公开设备能力和动作参数
        -> 状态转移
        -> 目标条件或谓词验证
        -> 状态差分、完成度和最终成功
```

SMH-Bench 更偏向评测 harness：给定家庭状态、用户请求和模型输出，准确判断是否完成任务。它需要可靠的状态容器、动作执行器、查询接口、快照/差分和任务验证器。

HomeFlow 更偏向训练环境底座：在符号状态上批量生成 Blueprint、执行多轮策略、计算每步目标完成度、审计动作、提供奖励，并支持多条 rollout 或 MCTS 分支。

因此，HomeFlow 看起来在物理仿真上更轻量，但训练生命周期反而更复杂。它的“简化”主要是：

```text
连续物理 -> 符号状态
真实时间等待 -> 确定性即时反馈或语义时间校验
开放生活目标 -> 可计算条件集合
完整设备世界 -> 可控任务范围和明确边界
```

这样做的根本目的，是让 SFT 数据可验证、RL reward 可计算、失败原因可归因，而不是单纯追求功能少。

### 2.2 Gym 风格是否必要

分析结论写在：

```text
doc/04_HomeFlow中HomeEnv简化复现方案.md
doc/09_HomeFlow模型决策步与HomeEnv修改方案.md
```

Gymnasium 包本身不是必要条件，但 episode/step 语义是必要条件。当前采用：

```text
核心 HomeEnv：框架无关
  reset()
  step(工具调用或模型 turn)
  snapshot()
  restore()
  fork()

GymHomeEnvAdapter：薄适配层
  将核心环境接入传统 Gym/Gymnasium 或训练框架
```

原因是 LLM 的动作不是传统的离散动作编号，而是文本和工具调用；同时又必须形成稳定的 transition：

```text
observation_t
  -> assistant turn_t
  -> tool events_t
  -> observation_{t+1}, reward_t
```

一个 assistant 输出对应一个模型决策步。一个 turn 内可以包含多个工具事件，但不能把一个模型 completion 事后拆成多个不存在的策略步。

### 2.3 SimuHome 吸收的内容

参考来源包括本地 SimuHome 源码和：

```text
doc/10_SimuHome时间机制简化与强化学习方案.md
```

项目只吸收以下思想：

```text
先发现房间，再发现房间内设备，再读取设备结构，最后执行动作
每个模型响应作为一次 action / turn
解析错误返回下一轮可见反馈，不静默丢弃
任务真值由程序构造，自然语言由外部模型改写
```

不复制 SimuHome 的 Matter 层级、完整工作流、真实时间推进、后台线程和复杂服务依赖。时间任务若以后加入，也优先采用固定时间和结构化 TemporalIntent 的语义校验，不在 RL 内循环真实等待。

### 2.4 统一语义接口方向

参考文件：

```text
14_接口交接-八个工具与统一语义.md
doc/11_HomeEnv统一语义接口与只读传感器设计讨论稿.md
```

目标是让训练用 Fake/HomeEnv 与以后接入 Home Assistant 的适配器共享一套通用语义：房间发现、设备查询、能力展示、动作执行和统一错误外壳。

当前 Demo 不复制 HA/MCP 的运行时复杂度，但保留迁移所需的思想：

```text
observe_home
  -> inspect_room
  -> inspect_device
  -> execute_action
```

传感器被建模为设备，只读设备通过 `actions=[]` 表达，不能被 `execute_action` 写入。`capabilities` 在当前设计统一改名为 `actions`。`fields` 暂不进入模型可见协议，当前设备规模很小，完整返回状态和动作 schema 更容易学习和审计。

## 3. 本机和训练框架判断

### 3.1 当前真实机器

本轮实际执行 `nvidia-smi` 得到：

```text
GPU：NVIDIA GeForce RTX 5090
显存：32607 MiB，约 32GB
驱动：580.76.05
当前显存占用：0 MiB
Python：3.12.3
```

需要注意：

```text
doc/06、doc/07、doc/08 早期判断仍按单张 RTX 4090 / 24GB 撰写
当前机器已经换成 RTX 5090 / 32GB
旧文档的资源结论不能直接当作当前机器的最终上限
```

后续应重新实测显存峰值和训练吞吐，尤其是 1.5B LoRA-GRPO、reference model、长上下文和多 rollout 的组合。

### 3.2 MiniMind 与标准训练框架的分工

MiniMind 的定位被明确为学习项目和小规模机制实验台。它适合帮助理解 Transformer、SFT、GRPO、reward 和训练循环，但不适合作为 1.5B 外部模型长期实验的主框架。

当前框架判断记录在：

```text
doc/05_端侧模型全量GRPO与LoRA-GRPO提升幅度论文分析.md
doc/06_本机RTX4090端侧模型全量GRPO与LoRA训练资源及规模分析.md
doc/07_1.5B_LoRA-GRPO科研入门框架选型与本机落地方案.md
```

推荐顺序仍是：

```text
1. Transformers + TRL + PEFT + Accelerate
   主线方案，科研可读性和自定义 HomeEnv 能力最好

2. ms-swift
   更强调快速启动和显存配置，适合作为工程效率对照

3. OpenRLHF
   适合后续多轮 Agent、多卡和更复杂 rollout，但单卡排错成本较高
```

LoRA 省显存主要来自 PEFT、gradient checkpointing、序列长度、rollout 方式、reference model 和 logits 处理，不是框架名称自动带来的。当前项目的实际主线应是：

```text
MiniMind：验证小型训练代码和环境 reward 的基本机制
Qwen2.5-1.5B 或同级 HF 模型：TRL + PEFT 做 SFT / LoRA-GRPO
4B：当前机器上做短上下文、小 rollout 的 LoRA/QLoRA 对照
7B：优先推理或极小规模 QLoRA，不作为第一阶段训练目标
```

模型权重、第三方源码和私密配置不进入 Git；具体来源和恢复方式见 `source.md`。

## 4. 版本演进和主要产物

### 4.1 01-08：从论文理解到整体实施方案

这些文档完成了问题定义和资源边界：

```text
01：SMH-Bench / HomeFlow 实验架构对照和复现分层
02：HomeEnv 核心谱系、两个模拟器职责和复杂度差异
03：HomeFlow 对 HomeEnv 的补充/精简为何服务 SFT 与 RL
04：简化 HomeEnv、Gym 语义、reward、SFT、RL 的最小方案
05：1.5B / 4B / 7B 全量 GRPO 与 LoRA-GRPO 论文证据
06：早期 RTX 4090 资源边界和可行模型规模
07：1.5B LoRA-GRPO 框架选择和省显存配置
08：HomeEnv、DeepSeek 数据、SFT、LoRA-GRPO、评测的一体化实施方案
```

这一阶段形成的关键原则：

```text
先有可验证环境，再生成训练数据
先用 Oracle / 规则规划器验证 C/B，再接 DeepSeek
先做 SFT 工具格式对齐，再做在线 RL
训练和评测共享环境真值，但不让模型看到隐藏目标
```

### 4.2 V1：原子动作环境和规则 Oracle

V1 的核心是把家庭状态、设备动作、谓词和 Oracle 轨迹跑通。它主要验证底层状态机，不直接代表 LLM 的自然语言能力。

主要产物：

```text
homeflow_demo/env/
  schema.py
  tool_schema.py
  home_env.py
  state_engine.py
  predicates.py
  gym_adapter.py

homeflow_demo/data/
  scenario_generator.py
  planner.py
  trajectory_format.py
  build_v1_dataset.py
  validate_v1_dataset.py

homeflow_demo/data_processed/v1/
  train / val / eval 场景
  Oracle 轨迹
  manifest.json / manifest.md
```

V1 历史数据为 140 条场景：

```text
train：80
val：20
eval：40
```

V1 原始任务包含单设备控制、多设备控制、查询后控制、亮度/锁控制、越界温度等。后续 V1.2 重写了任务和语义接口，V1 数据保留为历史验收产物，不与新协议混合。

### 4.3 V1.1：模型 turn 与环境 transition 对齐

V1 的动作级 `step(Action)` 对规则规划器没问题，但直接用于 LLM RL 会产生错误信用分配：如果一次模型 completion 包含多个工具调用，不能把它们拆成多个模型决策步。

V1.1 的核心修正：

```text
一次 assistant 输出 = 一次模型 turn = 一条策略 transition
一个 turn 内的多个工具调用 = 多个 tool_events
max_turns = 模型输出次数上限
max_tool_calls_per_turn = 单个输出允许的工具调用数量
```

当前默认：

```text
max_turns = 10
max_tool_calls_per_turn = 4
```

非法 JSON、工具参数错误、合法工具调用和 `finish` 都消耗一个 turn；不能设置“格式错误多次后提前拒绝”的隐式规则。这个逐 turn 反馈思路参考了 SimuHome，但当前项目明确保留完整十轮预算。

V1.1 报告：

```text
homeflow_demo/reports/V1_report.md
```

### 4.4 V1.2：A/B/C 核心框架重写

V1.2 依据：

```text
doc/11_HomeEnv统一语义接口与只读传感器设计讨论稿.md
doc/12_HomeFlow整体实验架构与V1.2-V4详细交付方案.md
doc/13_HomeFlowV1.2当前实现结果梳理.md
homeflow_demo/reports/V1.2_report.md
```

V1.2 没有在旧 V1 代码上继续局部打补丁，而是重写了环境、工具、C 回合和数据接口，以避免旧 `query_device` / `control_device`、旧状态流转和旧评测口径继续混入。

## 5. 当前实验架构：A-F 六个模块

用户最终确认的模块划分是：上面 A/B/C，下面 D/E/F。

```text
┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│ A 外部交互模块          │   │ B HomeEnv 环境模块      │   │ C 回合与评测框架         │
│ 模型 / Oracle           │<->│ 家庭状态与设备执行       │<->│ 管理 turn、读真值、评测   │
│ 输出 assistant turn     │   │ 返回 tool result         │   │ 输出 reward / success     │
└──────────────┬─────────┘   └──────────────┬─────────┘   └──────────────┬─────────┘
               └────────────────────── C 调度 A 与 B ──────────────────────┘

┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│ D 数据生成与审查筛选    │   │ E SFT 训练模块           │   │ F RL 训练模块           │
│ 生成任务、候选、审核    │   │ 读取高质量成功轨迹       │   │ rollout + 环境 reward   │
│ 路由 raw / processed    │   │ 输出 SFT / LoRA 模型     │   │ LoRA-GRPO 更新模型      │
└────────────────────────┘   └────────────────────────┘   └────────────────────────┘
```

模块边界：

```text
A：给定 context 产生一次 assistant 响应；不直接改 HomeEnv
B：只负责房间、设备、状态、动作和统一工具返回；不读 hidden truth，不处理 finish
C：唯一负责回合生命周期、解析 A、调度 B、读取隐藏任务、评测、reward 和终止
D：构造 Blueprint、调用 DeepSeek 生成/审查候选、组织可追溯数据
E：把 D 筛选的成功轨迹转成 SFT 数据并训练
F：让训练策略作为 A 进入 C，复用 C 的 EpisodeEvaluation 作为 reward
```

V1.2 实际落地了 A、B、C 和本地确定性 D 的一部分：

```text
A = OraclePolicy
B = HomeEnv
C = EpisodeRunner + EpisodeEvaluator + trajectory_quality
D = ScenarioGenerator + planner + build/validate_v1_2_dataset
E/F = 只有方案，尚未训练
```

## 6. V1.2 当前环境实现

### 6.1 家庭规模和房间设备关系

当前 V1.2 `ScenarioGenerator` 每个场景包含：

```text
房间：5 个
  卧室、卫生间、客厅、厨房、书房
  其中前 4 个有设备，书房为空，用于缺失设备任务

设备：7 台
  只读传感器 2 台
    sensor_bedroom_env：卧室温湿度传感器
    sensor_bathroom_humidity：卫生间湿度传感器

  可控执行设备 5 台
    device_bedroom_light：卧室主灯
    device_bedroom_climate：卧室空调
    device_bathroom_fan：卫生间排风扇
    device_living_light：客厅主灯
    device_kitchen_switch：厨房插座
```

设备 `kind` 当前只有两种：

```text
sensor
actuator
```

房间关系当前在数据中同时存在两侧：

```text
home.rooms[].device_ids
device.room_id
```

`Home.from_dict()` 会建立按 ID 的索引，`inspect_room` 根据房间内的设备返回摘要。后续若重构数据结构，可以让房间设备列表由 `device.room_id` 派生，避免双向字段漂移；当前 V1.2 两侧仍用于 schema 和工具输出。

### 6.2 设备动作和参数

当前动作由设备公开的 `actions` 提供，`inspect_device` 返回完整动作 schema，`execute_action` 只执行已经发现并检查过的设备。

```text
通用开关动作：turn_on、turn_off、toggle

空调额外动作：
  set_mode(mode: off | cool | heat | auto)
  set_temperature(value: 7.0 .. 32.0，步长 0.5)

排风扇额外动作：
  set_percentage(value: 0 .. 100，整数，步长 1)

传感器：actions=[]，只能 inspect，不能 execute_action 写入
```

### 6.3 模型可见工具

A 当前看到 5 个工具，其中 4 个是 B 的家庭语义工具，`finish` 是 C 的 episode-control 工具：

```text
observe_home()
  返回房间目录、房间级环境摘要和设备数量，不直接返回逐设备 ID

inspect_room(room_id)
  返回该房间的设备摘要，帮助模型得到 device_id

inspect_device(device_id)
  返回设备完整公开状态和 actions 参数范围

execute_action(device_id, action, params)
  唯一的家庭写入口；返回 state_after、verified、state_diff 等结果

finish(...)
  由 C 处理并结束 episode，不发送给 B
```

发现链强制为：

```text
observe_home -> inspect_room -> inspect_device -> execute_action
```

模型不能凭空猜测设备 ID 绕过发现。B 当前维护 `home_observed`、`discovered_device_ids` 和 `inspected_device_ids`。如果直接控制未发现或未检查的设备，会得到 `UNKNOWN_DEVICE` 或 `BAD_REQUEST`，并由 C 归入策略错误。

### 6.4 错误和责任边界

当前错误分类：

```text
策略 / 协议错误：UNKNOWN_ROOM、UNKNOWN_DEVICE、UNSUPPORTED_ACTION、BAD_REQUEST、INVALID_ASSISTANT_RESPONSE、TOO_MANY_TOOL_CALLS
环境错误：DEVICE_UNAVAILABLE、BACKEND_UNREACHABLE
未决错误：SERVICE_ERROR
```

策略错误会计入轨迹质量和 reward 惩罚；环境错误标记环境失败，不与模型策略失误混算；解析错误也消耗一个 turn。

## 7. V1.2 当前任务与数据结果

V1.2 保留了一个确定性、本地可生成的八类任务集：

```text
single_control        单设备控制
multi_control         多设备控制
query_then_control    先查后控
temperature_threshold 温度阈值控制或 no-op
humidity_threshold    湿度阈值控制或 no-op
correct_no_op         已满足目标时保持不动
sensor_readonly       对只读传感器写入，预期失败
missing_device        目标房间没有目标设备，预期失败
```

V1.2 数据产物：

```text
homeflow_demo/data_processed/v1.2/
  scenarios_train.jsonl             80
  scenarios_val.jsonl               20
  scenarios_eval.jsonl              40
  oracle_trajectories_train.jsonl    80
  oracle_trajectories_val.jsonl      20
  oracle_trajectories_eval.jsonl     40
  manifest.json
  manifest.md
```

历史验证结果：

```text
V1.2 单元测试：18 / 18 通过
V1.2 场景 schema：140 / 140 通过
V1.2 轨迹确定性重放：140 / 140 通过
V1.2 重复构建结果一致：140 / 140 通过
V1 历史数据 ID 对齐检查：140 / 140 通过
Python compileall：通过
```

当前 V1.2 已经证明：环境状态、工具发现、动作边界、Oracle 轨迹、turn-level 数据格式和本地确定性评测可以独立闭环。

## 8. V2 数据合成路线

V2 放弃 V1.2 的八类任务，转为更适合训练小模型和验证语义能力的五类：

```text
T1 single_control       单设备控制
T2 multi_control        多设备控制
T3 vague_intent         模糊意图理解
T4 dangerous_refusal    危险动作拒绝
T5 environment_query    环境基础查询
```

`query_then_control` 不再单独作为类别，因为查询房间、发现设备、读取能力本来就是控制任务的必要过程。

### 8.1 D0 Blueprint

程序先构造家庭、任务和隐藏真值，形成 `TaskBlueprint`：

```text
blueprint_id / split / category / home / task / writer_view / hidden_truth / seed
```

其中：

```text
task / hidden_truth：供 C 和评测读取的隐藏目标
writer_view：给 TaskWriter 的有限语义输入
category：任务元数据，属于 D0，不要求 D1 回填
seed：用于场景可复现
split：当前用于标记数据归属和输出，正式大规模数据应审查后再切分
```

`writer_view` 典型内容：

```json
{
  "category": "dangerous_refusal",
  "semantic_goal": "用户要求把卧室空调设为5度；查看能力后拒绝越界写入",
  "display_names": ["卧室空调"],
  "language_constraints": [
    "只输出用户自然语言请求",
    "不要出现 device_id、room_id、action 名、reason_code",
    "不要添加蓝图没有的设备目标"
  ]
}
```

### 8.2 D1 TaskWriter

当前实现是：一个 Blueprint 调用一次 DeepSeek API，一次返回一个 JSON 响应，通常包含三个候选。

```text
1 Blueprint
  -> 1 次 TaskWriter API
  -> candidates = [{"text": ...}, {"text": ...}, {"text": ...}]
```

最新协议修正后，`category` 只作为输入语义提示，候选输出只应包含：

```json
{
  "candidates": [
    {"text": "把卧室空调调到5度。"},
    {"text": "帮我把卧室空调设成5度。"}
  ]
}
```

`text` 就是 DeepSeek 改写出来的自然语言用户请求。D1 不负责产生工具调用，不负责判断 HomeEnv 是否成功。

### 8.3 D2 StaticTaskValidator

D2 不调用 DeepSeek，只做代码能够稳定判断的硬检查。它从 D0 读取：

```text
blueprint_id、home.rooms[].room_id、home.devices[].device_id、
home.devices[].actions[].action、task.expected_finish.allowed_reason_codes
```

逐条检查：

```text
候选是否为对象
候选是否只包含 text 字段
text 是否为非空字符串
规范化 text 长度是否超过 300
是否泄露内部 ID、action 名或 reason_code
是否把明显工具 JSON 写入用户请求
规范化文本是否在共享 registry 中精确重复
```

D2 当前不做：

```text
不判断自然语言是否完整表达蓝图目标
不判断生活化表达是否真正指向目标设备
不做语义重复判断
不读取 conditions、keep、required_observations 或设备 state 做语义覆盖
```

近期修正的根因是：旧代码检查 `candidate.category`，但 D1 输出协议从未要求模型返回该字段。现在 D2 删除 `CATEGORY_MISMATCH`；若候选额外返回 `category`，统一标记 `CANDIDATE_EXTRA_FIELDS`。

### 8.4 D3 TaskReviewer

D3 调用 DeepSeek，审查 D2 通过的自然语言候选：

```text
目标是否完整覆盖
类别语义是否符合
是否增加额外设备或动作意图
是否存在软泄露
是否可能与其他候选语义重复
```

D3 返回 `accept`、`category_match`、`target_covered`、`extra_intent`、`soft_leakage`、`review_codes` 等字段。当前 `semantic_duplicate_group` 只是记录，还没有在构建脚本中执行第二轮语义去重。

### 8.5 C/B rollout、确定性审核和语义裁判

通过 D3 的候选先编译为 Scenario，再由 DeepSeekPolicy 作为 A 与 C/B 交互：

```text
Scenario
  -> DeepSeekPolicy 产生一次响应
  -> EpisodeRunner 解析响应并计一个 turn
  -> HomeEnv 执行合法环境工具
  -> C 返回工具反馈或协议反馈
  -> EpisodeEvaluator 读取隐藏任务并计算 EpisodeEvaluation
```

T1/T2 主要依靠确定性审查；T3/T4/T5 还调用 `DeepSeekTrajectoryJudge`，因为查询回答、拒绝语言和模糊意图不能全部靠状态布尔值判断。

合并原则：

```text
物理目标失败不能被语义裁判改成成功
结构化 finish 错误不能只靠自然语言说明补救
语义裁判 API 失败不能算策略失败
策略错误和环境错误分开统计
```

## 9. V2 Smoke Test 实际结果

第一轮五类各 1 条用于验证 API、并发、格式反馈和端到端链路：

```text
Blueprint：5
TaskWriter 候选：15
TaskReviewer：13 条通过，2 条 API/JSON 失败
rollout：5
clean_success：1
最大 API 并发：5
环境并发探针：5 个独立 HomeEnv，全部通过
```

第二轮五类各 4 条，共 20 条，报告：

```text
Blueprint：20
TaskWriter：20 / 20 返回
候选总数：60
StaticTaskValidator：55 通过，5 条 EXACT_DUPLICATE
TaskReviewer：40 通过，11 条语义拒绝，4 条 JSON 输出失败
Scenario：16 条成功编译，4 条生成阶段丢失
rollout：16
确定性正式成功：2
最终路由：clean_success 2，failed 14
```

重要限定：这个 `2/20` 不能直接解释为模型能力只有 10%。原因包括：

```text
4 条 Blueprint 在任务生成阶段没有成功候选
多个物理控制任务其实已经完成目标，但 finish 契约失败
10 条需要语义裁判的轨迹没有形成足够有效票
DeepSeek Judge 请求中 29 次 finish_reason=length，28 次空正文
当前路由把部分 Judge 系统失败归并到了 failed，而不是 system_failure
```

典型真实失败过程：

```text
HomeEnv 执行成功
  execute_action -> state_after 正确 -> goal_completion=1.0

模型最终只返回：
  {"summary": "已完成卧室主灯关闭。"}

C 内部评测：
  finish_contract_valid=false
  success=false
```

危险拒绝任务也出现类似情况：模型没有执行危险写入，状态保持不变，文字上正确说明拒绝，但没有提交结构化 `outcome=refused` 和 `reason_code=OUT_OF_SAFE_RANGE`。

任务生成阶段的典型问题是多设备任务被拆成三个片段：

```text
候选 1：只关卧室灯
候选 2：只调空调
候选 3：只说客厅灯不动
```

没有一条候选覆盖完整多设备目标，因此全部被 D3 拒绝，Blueprint 没有进入 Scenario。正式流水线需要写出 `task_generation_failed` 或待重试记录，不能静默让 20 条变成 16 条。

完整报告：

```text
homeflow_demo/reports/V2_smoke_report.md
doc/15_V2第二轮20条SmokeTest失败原因综合分析.md
```

## 10. 当前主要问题和已修正内容

### 10.1 大问题一：finish 协议不一致，尚未整体修复

当前实际代码仍存在历史协议：

```text
公开 tool schema：summary 必填，additionalProperties=false
内部 C 校验：允许 summary / outcome / facts / reason_code
旧 expected_finish：outcome / facts / allowed_reason_codes
DeepSeekPolicy prompt：要求结构化 outcome / facts / reason_code
```

这导致模型看到的 schema 与实际评测 schema 不完全一致。用户已经确定的精炼方向是：

```text
模型可见 finish：status / summary / reason_code
status：completed | refused
completed：status + summary
refused：status + summary + reason_code
reason_code：OUT_OF_SAFE_RANGE | READ_ONLY_DEVICE
summary：只辅助分析轨迹质量，不直接判断成败
删除 answered
删除 facts
十轮耗尽由 C 的 truncated 表示
```

目前这套精炼契约还没有完整写回 `tool_schema.py`、`deepseek_policy.py`、`task_blueprints.py`、`schema.py`、`episode_runner.py` 和 `episode_evaluator.py`。它是下一轮协议冻结的首要任务。

### 10.2 D2 的 `candidate.category` 问题已经修正

原问题：D2 检查 `candidate.category` 是否与 Blueprint 一致，但 D1 从未被要求输出这个字段。

当前正确边界：

```text
Blueprint.category / writer_view.category
  是 D0 给 D1 的任务语义输入和后续路由元数据

candidate.text
  是 D1 实际生成的自然语言请求

candidate.category
  不属于候选输出协议
```

已完成代码和文档调整：

```text
deepseek_task_writer.py
  prompt 明确 category 只用于理解，不要输出

static_task_validator.py
  删除 CATEGORY_MISMATCH
  额外字段统一标记 CANDIDATE_EXTRA_FIELDS

对应中文说明和 doc/14、doc/16
  已同步修改
```

已验证：

```text
{"text": "把卧室主灯关掉。"}
  -> accepted=true

{"text": "把卧室主灯关掉。", "category": "environment_query"}
  -> accepted=false
  -> CANDIDATE_EXTRA_FIELDS
```

### 10.3 其他尚未冻结的问题

```text
任务生成失败没有独立路由，Blueprint 可能静默消失
精确去重是程序字符串匹配，不是 DeepSeek 语义判断
当前 registry 跨 Blueprint 共用，去重范围可能过宽
TaskReviewer 的“完整目标覆盖”需要更明确的任务输入约束
T3 是否允许显式提及设备，需要冻结生成规则
T5 的 required_observations 是否必须检查传感器，需要重新定义
查询答案正确性不能依赖旧 facts/finish 复制机制
Judge max_tokens / reasoning 输出配置导致大量 length 截断
语义裁判 system_failure 与策略 failed 的路由优先级需修复
当前 V2 仍使用旧 finish outcome/facts 契约，需与新 status 契约统一
```

## 11. 当前代码和文件入口

### 11.1 环境 B

```text
homeflow_demo/env/models.py
  Home、Room、Device、ActionSchema、TaskSpec、Scenario、ToolCall、ToolEvent

homeflow_demo/env/schema.py
  Scenario 和任务数据 schema

homeflow_demo/env/tool_schema.py
  A 可见工具、参数形状、统一成功/错误 envelope、错误分类

homeflow_demo/env/home_env.py
  HomeEnv reset/step、发现权限、状态执行、snapshot/restore/fork

homeflow_demo/env/state_engine.py
  房间、设备、状态和 action 参数实际执行

homeflow_demo/env/predicates.py
  conditions / keep 完成度和目标判断

homeflow_demo/env/gym_adapter.py
  薄 Gym 风格适配层
```

### 11.2 A 和 C

```text
homeflow_demo/agents/oracle_policy.py
  规则 Oracle，用于环境和评测验收

homeflow_demo/agents/deepseek_client.py
  OpenAI 兼容 API、重试、JSON 解析、usage、原始响应落盘、并发计数

homeflow_demo/agents/deepseek_policy.py
  每个 turn 调用 DeepSeek，输出交给 C 解析

homeflow_demo/eval/episode_runner.py
  C 的回合循环、assistant 解析、工具派发、协议反馈、turn 计数

homeflow_demo/eval/episode_evaluator.py
  读取隐藏任务、判断 conditions/keep/required_observations/finish

homeflow_demo/eval/deterministic_audit.py
  从 EpisodeEvaluation 整理可解释的确定性结果

homeflow_demo/eval/deepseek_trajectory_judge.py
  T3/T4/T5 的语义裁判
```

### 11.3 数据 D

```text
homeflow_demo/data/scenario_generator.py
  V1.2 八类场景、家庭状态、传感器和动作

homeflow_demo/data/planner.py
  V1.2 Oracle 计划和轨迹

homeflow_demo/data/task_blueprints.py
  V2 五类 Blueprint、writer_view、hidden_truth、Scenario 编译

homeflow_demo/data/deepseek_task_writer.py
  D1 自然语言候选

homeflow_demo/data/static_task_validator.py
  D2 程序硬校验

homeflow_demo/data/deepseek_task_reviewer.py
  D3 任务语义审查

homeflow_demo/data/build_v1_2_dataset.py
  V1.2 场景和 Oracle 数据构建

homeflow_demo/data/build_v2_dataset.py
  V2 候选、审查、rollout、裁判和数据路由
```

每个 Python 模块都配有同名中文 `.md` 说明文档，说明职责、输入、输出和文件写入位置。

### 11.4 重要数据和报告目录

```text
homeflow_demo/data_processed/v1/
  V1/V1.1 历史数据，只读保留

homeflow_demo/data_processed/v1.2/
  当前本地确定性场景和 Oracle 数据

homeflow_demo/reports/V1_report.md
homeflow_demo/reports/V1.2_report.md
homeflow_demo/reports/V2_smoke_report.md

doc/14_DeepSeek候选轨迹生成与审查流水线方案.md
doc/15_V2第二轮20条SmokeTest失败原因综合分析.md
doc/16_V2当前发现问题清单.md
```

DeepSeek 原始响应和 API 日志应放在 `data_raw/` 或 smoke 临时目录，不应进入 Git。

## 12. Git 和仓库边界

项目已经开始建立 Git 仓库管理，相关原则写在：

```text
source.md
homeflow_demo/.gitignore
```

仓库纳入：

```text
HomeFlow 自主源码
测试
设计和复现分析文档
小型确定性数据和 manifest
```

仓库外保留：

```text
论文原件和提取文本
第三方 llama.cpp / MiniMind / SimuHome 源码
模型权重
homeflow_demo/.env.deepseek
API 原始响应、缓存、checkpoint 和训练输出
```

Git 提交身份已确定：

```text
name：juezhan
email：2262637958@qq.com
```

当前工作树存在大量历史修改、未跟踪的新文档和新模块，不要使用 `git reset --hard` 或无确认的回滚命令。继续工作时应基于现有状态增量修改。

## 13. 下一步推荐顺序

当前不应直接扩大 DeepSeek 数据生成规模。更合理的顺序是：

```text
第一步：冻结 finish 协议
  统一公开 schema、system prompt、本地校验、expected_finish 和评测读取
  采用 status=completed/refused
  reason_code 只保留 OUT_OF_SAFE_RANGE / READ_ONLY_DEVICE
  删除 facts / answered
  明确 summary 只作质量辅助

第二步：补齐 finish 和评测测试
  completed 控制
  completed 查询
  refused 越界
  refused 只读设备
  十轮 truncated
  纯文本终答是否自动转换为 finish

第三步：修复 V2 任务生成路由
  Blueprint 没有合格候选时写 task_generation_failed
  保存所有候选、D2 结果、D3 结果和 API 状态
  不静默减少 Scenario 数量

第四步：重新冻结查询和模糊任务契约
  明确 required_observations 是过程要求还是答案证据
  明确查询答案由结构化工具事实、语义 Judge 还是两者共同判断
  明确 T3 是否允许显式设备名称

第五步：重新跑小规模 smoke
  先每类 1 条
  再每类 4 条
  核对 route、错误分类、finish、Judge 和断点续跑

第六步：冻结后再大规模生成和进入 SFT
  通过验证的成功轨迹进入 SFT
  SFT 后再做 1.5B LoRA-GRPO
```

## 14. 新对话最先需要知道的事实

```text
1. 环境核心已经能独立运行，V1.2 不是空方案。
2. V1.2 的本地确定性数据和 Oracle 轨迹已通过 18 项测试、140 条重放检查。
3. V2 的 DeepSeek API、任务生成、任务审查、C/B rollout、确定性审核和语义裁判代码已经存在。
4. V2 20 条 smoke 证明链路可运行，但不能直接用于大规模数据生成。
5. 当前最大协议风险仍是 finish schema 与 hidden expected_finish 不一致。
6. `candidate.category` 已确认是旧设计遗留，已经移除类别一致性检查。
7. 当前机器是 RTX 5090 32GB，早期 RTX 4090 资源文档需要重新评估。
8. 真正的 1.5B SFT / LoRA-GRPO 训练还没有开始。
9. DeepSeek 是数据生成和语义审查工具，不应代替 HomeEnv/C 的确定性真值。
10. 下一轮工作的正确起点是冻结 finish 和评测契约，然后重新 smoke。
```
