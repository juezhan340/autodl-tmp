# HomeFlow Demo 整体实验架构与 V1.2-V4 详细交付方案

> 日期：2026-09-23
> 性质：V1.2 之后的总实施方案
> 当前状态：V1.1 已完成；V1.2 设计依据为 `11_HomeEnv统一语义接口与只读传感器设计讨论稿.md`，代码尚未重写
> 适用项目：`/root/autodl-tmp/homeflow_demo`

## 先看结论

```text
V1.2  A/B/C 核心框架重写
      重建 Home / Room / Device / Sensor / ActionSchema / Scenario 的关系
      交付 A 外部交互、B HomeEnv、C 回合评测、质量门禁和统一结果

V2    数据合成与 SFT 基线
      程序生成场景 + DeepSeek 候选轨迹 + C 驱动 B 执行并筛选
      交付可追溯的 SFT 数据和第一个 LoRA-SFT 模型

V3    在线 rollout 与 LoRA-GRPO
      SFT 模型作为 A 进入 C，C 驱动 B 多轨迹采样并形成组内优势
      交付单卡可运行的最小 RL 闭环

V4    汇总评测、迁移与消融
      复用 V1.2 评测核心完成 Base / SFT / RL 对比、未见组合测试和迁移验证
      交付可复现的实验报告和失败实验记录
```

这四个版本分别解决四个不同问题：

```text
V1.2：环境语义和基础评测是否正确、稳定、可重放？
V2：  能否获得经过环境验证的自然语言工具轨迹，并完成 SFT？
V3：  能否让 1.5B 模型在环境奖励下继续改进？
V4：  提升是否真实，能否泛化，实验能否复现和解释？
```

本方案将此前旧版交付计划中的 V0～V7 合并为四个研究阶段。旧版交付计划已经删除，不再作为后续实施依据。

## 1. 实验架构总览

### 1.1 研究问题

本项目要验证的是一条由统一评测真值贯穿的数据和后训练链路：

```text
Scenario + hidden truth
  -> C 管理 A 与 B 的逐回合交互
  -> A 产生 assistant turn，C 提取规范化 ToolCall 并交给 B 校验执行
  -> C 读取 B 的结果和隐藏真值，判断成功、失败、错误归因和 reward
  -> C 筛选出的成功轨迹进入 SFT
  -> SFT 模型重新作为 A 回到 C，完成基线评测和在线 rollout
  -> C 为 RL 提供同一口径的 EpisodeEvaluation 和 reward
  -> 冻结测评集复用 C 比较 Base / SFT / RL
```

核心比较对象固定为：

```text
Base：  原始 Qwen2.5-1.5B-Instruct
SFT：   经过成功工具轨迹 LoRA-SFT 的模型
RL：    从 SFT checkpoint 继续做 HomeEnv LoRA-GRPO 的模型
Oracle：程序规划器或经过验证的参考轨迹，只用于上界和数据核验
```

DeepSeek 的角色是候选轨迹生成器，不是环境裁判；B 的 HomeEnv 保存家庭运行状态，C 的评测框架读取 Scenario 隐藏真值并判断任务结果。A、B、C 共同构成一次完整实验回合，D、E、F 分别负责数据、SFT 和 RL。

### 1.2 六个核心模块

上层是“交互与评测核心”，下层是“数据与训练模块”。C 是整体回合控制器，A 和 B 是 C 调度的两个对象：

```text
┌────────────────────────────────────────────────────────────────────┐
│ C. 回合与评测框架                                                  │
│ 读取 Scenario、隐藏 goal、keep 和评测配置                          │
│ 管理 turn、调用 A、调用 B、记录 trajectory、计算 reward 和结果      │
│                                                                    │
│  ┌────────────────────────┐       ┌─────────────────────────────┐ │
│  │ A. 外部交互模块        │       │ B. HomeEnv 环境模块         │ │
│  │ 模型 / Oracle /         │       │ Home / Room / Device        │ │
│  │ DeepSeek               │       │ 状态、工具执行、state diff  │ │
│  │ 输入 observation       │       │ 接收 C 的 action             │ │
│  │ 输出 assistant turn    │       │ 返回 C 的 tool result        │ │
│  └────────────────────────┘       └─────────────────────────────┘ │
│                                                                    │
│  C 将响应封装转成 ToolCall；B 校验 action 语义并执行             │
│  C 控制回合、读取隐藏真值、评测结果并计算 reward                 │
│                                                                    │
│  C 内部输出：success、error class、EpisodeEvaluation、reward       │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
│ D. 数据生成与审查筛选 │  │ E. SFT 训练模块        │  │ F. RL 训练模块         │
│ Scenario、DeepSeek、  │  │ accepted trajectories │  │ SFT policy + C/B       │
│ Oracle、质量门禁      │  │ -> LoRA-SFT           │  │ -> rollout -> GRPO     │
└───────────┬────────────┘  └───────────┬────────────┘  └───────────┬────────────┘
            │ C 的评测结果              │ SFT checkpoint             │ RL checkpoint
            └───────────────>───────────┴───────────────>────────────┘
```

上图中的箭头关系是：D 调用 A 产生候选交互，C 驱动 A 与 B 完成回合并审查结果；E 读取 D 筛选后的成功轨迹，训练后的模型重新作为 A；F 让训练中的策略作为 A 进入 C，C 继续调用 B 并提供 reward。

### 1.3 主输入输出关系

```text
┌────────────────────────────────────────────────────────────────────┐
│ C. 回合与评测框架                                                  │
│                                                                    │
│  Scenario + hidden truth                                           │
│          │                                                         │
│          v                                                         │
│  while episode not done:                                           │
│      C -> A：提供 observation / tool schema                        │
│      A -> C：返回 assistant turn / finish                          │
│      C -> B：传递规范化 ToolCall                                    │
│      B -> C：返回 tool result / state diff / observation            │
│      C：记录 turn，更新完成度、错误归因和 reward                    │
│                                                                    │
│  episode end -> EpisodeEvaluation                                  │
└────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│ D. 数据生成与审查筛选   │
│ Scenario Generator       │
│ A=DeepSeek / Oracle      │──候选 turn──> C
│ C 输出 accepted/rejected │<──评测结果───┘
│ 输出高质量 SFT 数据      │
└──────────────┬───────────┘
               v
┌──────────────────────────┐
│ E. SFT 训练模块          │
│ accepted trajectories    │
│ -> Qwen2.5-1.5B LoRA-SFT │
│ -> SFT checkpoint        │──作为 A──> C 做基线评测
└──────────────┬───────────┘
               v
┌──────────────────────────┐
│ F. RL 训练模块           │
│ SFT checkpoint 作为 A    │
│ C 管理在线 rollout       │
│ B 执行环境动作           │
│ C 提供 EpisodeEvaluation │
│ -> LoRA-GRPO 更新        │
│ -> RL checkpoint ────────┘ 回到 C 做冻结评测
└──────────────────────────┘
```

### 1.4 每个模块的边界

#### A. 外部交互模块

职责：
  提供实际产生 assistant turn 的外部决策者，包括本地模型、DeepSeek、Oracle 规划器和评测时的 Base/SFT/RL checkpoint。

输入：
  C 提供的 observation、系统提示、工具 schema、历史消息和任务用户请求。

输出：
  assistant turn、结构化 tool call、finish 或解析失败响应。

读取：
  模型 checkpoint、Oracle 规则、DeepSeek API、tokenizer 和 prompt。

写入：
  原始模型响应、生成 token、logprob 和交互请求审计。

不负责：
  不直接修改家庭状态，不读取隐藏 goal，不判断任务是否成功，不计算 reward。

对应文件：
  `agents/model_client.py`、`agents/oracle_policy.py`、`agents/deepseek_client.py`、`train/rollout_runner.py`。

#### B. HomeEnv 环境模块

职责：
  维护 Home / Room / Device 的运行时状态；接收 C 传入的规范化 `ToolCall`，校验工具名、action、参数和设备状态后执行，并返回工具结果和状态变化。

输入：
  C 传入的 `Scenario`、reset 请求和规范化 `ToolCall`。`ToolCall` 至少包含 `name`、`arguments` 和 `call_id`，不包含模型厂商特有的消息封装。

输出：
  observation、tool result、state diff、统一错误返回、snapshot/fork 状态。

读取：
  `Home / Room / Device / ActionSchema`、设备初始状态和动作参数 schema。

写入：
  运行时状态副本、设备状态变化和环境事件。

不负责：
  不解析厂商特有的 assistant 消息格式，不管理完整回合，不读取隐藏目标，不判断 SFT 数据是否合格，不计算最终实验指标。

对应文件：
  `env/models.py`、`env/schema.py`、`env/tool_schema.py`、`env/state_engine.py`、`env/home_env.py`、`env/gym_adapter.py`。

#### C. 回合与评测框架

职责：
  作为整体实验框架，管理 A 与 B 的多轮交互；将 A 返回的模型响应封装解析为统一 `AssistantTurn` / `ToolCall`，处理 finish、格式错误和 turn 限制，再把规范化调用交给 B。C 同时读取 Scenario 隐藏真值、记录完整轨迹、判定 episode 结果并产生 reward。

输入：
  Scenario、隐藏 `TaskSpec`、A 的原始响应、B 的 tool result，以及评测配置。

输出：
  规范化 `AssistantTurn` / `ToolCall`、下一轮 observation、完整 trajectory、EpisodeEvaluation、success、error class、reward 和质量门禁结果。

读取：
  隐藏 conditions/keep、工具事件、状态快照、错误码和奖励配置。

写入：
  `episode_records.jsonl`、`EpisodeEvaluation`、指标输入和 accepted/rejected 标记。

不负责：
  不生成模型响应，不解析设备动作的领域含义，不直接维护设备状态，不训练模型，不修改隐藏目标。

对应文件：
  `eval/episode_runner.py`、`eval/episode_evaluator.py`、`eval/trajectory_quality.py`、`eval/metrics.py`、`env/predicates.py`。

解析边界示例：A 返回模型厂商格式的 assistant tool call 后，C 只识别消息结构并提取 `{name, arguments, call_id}`。响应不是合法的 assistant/tool-call 结构时，由 C 记录为交互协议错误；参数格式不合法、设备不存在或设备不支持该 action 时，由 B 按统一错误协议返回 `BAD_REQUEST`、`UNKNOWN_DEVICE` 或 `UNSUPPORTED_ACTION`。C 记录错误并继续回合控制或结束 episode，但不解释设备动作的领域含义。

#### D. 数据生成与审查筛选模块

职责：
  生成 Scenario，调用 A 产生候选轨迹，并把候选交给 C 驱动 B 执行和审查；最终管理 accepted/rejected 数据。

输入：
  设备模板、房间模板、任务模板、固定 seed、DeepSeek API 配置和 C 的评测接口。

输出：
  Scenario JSONL、原始 API 响应、候选轨迹、质量审查结果、SFT 数据和 manifest。

读取：
  `homeflow_demo/data/templates/`、统一工具 schema、prompt 版本和 `.env.deepseek`。

写入：
  `data_processed/v1.2/`、`data_raw/v2/deepseek/`、`data_processed/v2/`。

不负责：
  不自行判断任务成功；所有成功、失败和质量判断都来自 C。eval Scenario 只冻结给 C 评测，不参与训练数据生成。

对应文件：
  `data/scenario_generator.py`、`data/task_templates.py`、`data/deepseek_teacher.py`、`data/trajectory_parser.py`、`data/candidate_runner.py`、`data/deduplicator.py`。

#### E. SFT 训练模块

职责：
  读取 D 筛选出的高质量成功轨迹，构造训练集并完成 LoRA-SFT；训练后的模型作为 A 接回 C 做基线评测。

输入：
  accepted trajectories、Tokenizer、Qwen2.5-1.5B-Instruct 和训练配置。

输出：
  SFT train/val JSONL、LoRA adapter、训练日志和 SFT 评测结果。

读取：
  C 产生的 accepted 标记、chat template、工具调用格式和数据 manifest。

写入：
  `data_processed/v2/sft/`、`checkpoints/v2_sft/` 和对应 episode records。

不负责：
  不使用 rejected trajectory 更新模型，不另建成功判定逻辑，不执行在线 GRPO。

对应文件：
  `data/sft_dataset_builder.py`、`train/model_loader.py`、`train/sft.py`。

#### F. RL 训练模块

职责：
  让策略模型作为 A 进入 C，由 C 管理在线 rollout、调用 B 执行环境动作并提供 EpisodeEvaluation，再执行 LoRA-GRPO 更新。

输入：
  SFT adapter、RL Scenario、采样配置、C 的回合接口和 reference policy。

输出：
  grouped rollouts、token 对齐、old logprobs、reward components、GRPO adapter 和训练日志。

读取：
  C 返回的 observation、tool events、EpisodeEvaluation、reward 和模型生成 token。

写入：
  `data_processed/v3/rollouts/`、`checkpoints/v3_grpo/` 和 RL episode records。

不负责：
  不维护环境状态，不复制 C 的 verifier，不修改隐藏目标，不把环境故障当成策略错误。

对应文件：
  `train/rollout_types.py`、`train/rollout_runner.py`、`train/token_alignment.py`、`train/reward.py`、`train/grpo.py`、`train/checkpoint.py`。

## 2. 统一数据契约

### 2.1 Scenario 与 HomeEnv 的关系

`Scenario` 是一条实验样本的静态配置，不是户型，也不是运行中的环境。它包含一个家庭初始快照和一个任务定义：

```text
Scenario
├── home
│   ├── rooms[]
│   └── devices[]
├── task
│   ├── user_request
│   ├── conditions
│   └── keep
└── episode_config
    ├── max_turns
    └── max_tool_calls_per_turn
```

运行关系为：

```text
Scenario（静态）
      │ reset()
      v
HomeEnv Runtime State（可变）
      │ step(assistant_turn)
      v
Tool Events + Reward + Observation
```

同一个家庭模板可以生成多个 Scenario：任务不同、初始状态不同、目标不同，都会形成不同的实验样本。HomeEnv 运行时只修改状态副本，不修改 Scenario 原始记录。

### 2.2 V1.2 领域对象

```text
Home
  rooms: dict[room_id, Room]
  devices: dict[device_id, Device]

Room
  room_id
  display_name
  device_ids

Device
  device_id
  room_id
  display_name
  kind: sensor | actuator
  device_type
  state
  actions: list[ActionSchema]

ActionSchema
  action
  params
  description
```

温度和湿度传感器使用 `kind=sensor`，其 `actions=[]`；房间环境摘要由传感器状态派生，不另存一份可写的重复真值。当前不实现房间面积、邻接、户型拓扑和连续热湿传播。

### 2.3 策略可见工具

```text
observe_home()
  输出：房间目录、房间级温湿度摘要、设备数量

inspect_room(room_id)
  输出：该房间全部设备的轻量摘要，包含 device_id

inspect_device(device_id)
  输出：完整 state 和 actions schema

execute_action(device_id, action, params)
  输出：state_after、verified、统一 error envelope

finish(summary)
  输出：runner 终止事件；不属于 HA 家庭语义写工具
```

隐藏目标校验由 C 调用 `predicates.py` 和 `episode_evaluator.py` 完成；HomeEnv 只返回当前状态、工具结果和事件，不自行判定 episode 成功。`fields` 在当前 Demo 不进入策略 schema。旧代码的 `query_device`、`control_device`、`capabilities` 仅作为迁移输入兼容，不再作为新数据的正式协议。

### 2.4 错误与奖励归因

```text
UNKNOWN_ROOM / UNKNOWN_DEVICE / UNSUPPORTED_ACTION / BAD_REQUEST
  归因：策略或协议错误
  处理：记录 tool event，可给动作级负奖励

DEVICE_UNAVAILABLE / BACKEND_UNREACHABLE
  归因：执行环境错误
  处理：标记 system failure，重试或剔除，不记入策略负奖励

SERVICE_ERROR
  归因：读取 message、hint 和后端上下文后再决定
  处理：无法归因时标记 unresolved，不直接惩罚策略
```

错误码提供失败原因，奖励函数才把原因转换成学习信号。环境故障不能与策略错误混合，否则模型会学习到错误的因果关系。

### 2.5 轨迹格式

```text
Trajectory
├── scenario_id
├── model_id / checkpoint_id
├── turns[]
│   ├── assistant_output
│   ├── tool_events[]
│   ├── observation_before
│   ├── observation_after
│   ├── reward
│   └── reward_components
└── final_result
```

一条 assistant turn 对应一条 RL transition；一个 turn 内可以有多个 tool event。依赖前一个工具结果的调用必须进入下一次 assistant turn，保证每个模型决策步都有对应的输入、输出和 token 记录。

### 2.6 统一评测结果

C 模块对每个 episode 生成同一种 `EpisodeEvaluation`。数据筛选、SFT 基线、RL reward 和冻结测评只能读取这个结果，不能各自重新解释轨迹：

```text
EpisodeEvaluation
├── scenario_id
├── success
├── goal_completion
├── keep_preservation
├── terminated / truncated
├── strategy_error_count
├── environment_failure_count
├── failure_class
├── reward
├── reward_components
├── accepted_for_sft
└── rejection_reasons[]
```

`accepted_for_sft=true` 至少要求：任务成功、没有未决环境故障、轨迹可重放、工具结果结构完整、没有终止后的多余动作。自然语言风格可以作为数据清洗条件，但不能覆盖环境失败结论。

## 3. 强化学习的奖励设计

### 3.1 奖励来源

奖励按来源拆开保存，不只保留一个总分：

```text
goal_progress       当前 conditions 完成度相对上一步的增量
terminal_success    全部目标和 keep 条件满足时的终局奖励
valid_action        合法工具调用的轻微正反馈
strategy_error      UNKNOWN_* / UNSUPPORTED_* / BAD_REQUEST 的负反馈
tool_cost           不必要查询、重复动作、额外 turn 的轻微成本
environment_failure 执行环境异常，默认不进入策略 reward
```

初始总奖励可以写成：

```text
r_t = 1.0 * goal_progress
   + 1.0 * terminal_success
   + 0.02 * valid_action
   - 0.10 * strategy_error
   - 0.01 * tool_cost
```

数值只作为 V3 初始配置，最终以固定 eval 上的行为和 reward 分布校准。奖励版本必须写入 manifest，不能在不同实验中静默修改。

### 3.2 不纳入默认奖励的内容

```text
elapsed_ms 不直接参与 reward
DeepSeek 的文字评分不参与 reward
模型自然语言是否漂亮不参与 reward
后端掉线、设备 unavailable 不作为策略错误
隐藏 goal 不进入模型 observation
```

## 4. V1.2：A/B/C 核心框架重写

### 4.1 版本目标

把当前 V1.1 的扁平设备列表和旧 query/control 协议整体重写为 11 号讨论稿确定的统一语义环境，同时建立 C 模块的回合控制、隐藏 verifier、错误归因和轨迹质量门禁。这里采用完整重构，避免在旧字段、旧工具、旧状态流转和旧评测口径上继续局部打补丁。

V1.2 结束时应能完成：

```text
C.reset(Scenario)
  -> C 向 A 提供 observation 和工具 schema
  -> A 返回 assistant turn
  -> C 解析模型消息封装，提取规范化 ToolCall
  -> B 校验工具名、action、参数和设备状态后执行
  -> B 返回 tool result、state diff 和 observation
  -> C 继续管理下一轮
  -> C 读取隐藏真值并生成 EpisodeEvaluation
      -> success / failure
      -> reward / error class
      -> accepted_for_sft / rejection_reasons
```

### 4.2 交付模块

```text
homeflow_demo/env/models.py
  重建 Home、Room、Device、ActionSchema、Scenario、TaskSpec、RuntimeHomeState。

homeflow_demo/env/schema.py
  校验房间引用、设备归属、sensor 只读边界、action 参数 schema 和 goal。

homeflow_demo/env/tool_schema.py
  固化五个策略入口、ToolCall 参数结构、统一返回外壳和错误码；负责工具名与参数 schema 的环境侧校验。

homeflow_demo/env/state_engine.py
  校验设备是否支持规范 action，将其映射到状态字段；执行前完成检查，失败时无部分写入。

homeflow_demo/env/home_env.py
  实现 reset、结构化 action step、工具事件审计和 snapshot/fork；不计算最终 reward，不读取隐藏目标。

homeflow_demo/env/predicates.py
  实现 conditions + keep 的隐藏验证和完成度计算。

homeflow_demo/env/gym_adapter.py
  保留为可选薄适配层；核心 HomeEnv 不依赖 Gymnasium。

homeflow_demo/agents/oracle_policy.py
  提供 V1.2 可重放的 Oracle 决策者，作为 A 模块的最小实现。

homeflow_demo/eval/episode_runner.py
  由 C 模块管理 A 与 B 的 turn 级交互、模型响应封装解析、ToolCall 提取、上下文拼接和 episode 终止；不实现设备动作语义。

homeflow_demo/eval/episode_evaluator.py
  由 C 模块读取隐藏目标、keep、tool events 和终止状态，输出统一 EpisodeEvaluation。

homeflow_demo/eval/trajectory_quality.py
  根据 EpisodeEvaluation 和轨迹结构生成 accepted_for_sft 与 rejection_reasons。

homeflow_demo/eval/metrics.py
  定义稳定的 episode 指标字段；V1.2 先完成单条和小批量统计，V4 再扩展完整比较。
```

每个代码文件同步维护同名中文 `.md`，说明输入、输出、状态归属和失败返回。

### 4.3 代码重写边界

```text
保留：
  turn-level AssistantTurn / ToolEvent / TurnResult 思想
  snapshot / restore / fork
  固定 seed 和可重放轨迹
  hidden verifier 和完成度 reward
  单条 episode 的成功、失败和错误归因思想

重写：
  Scenario 数据结构
  Home / Room / Device 索引
  初始 observation
  设备发现式工具协议
  action schema 和统一错误
  传感器只读状态
  旧 query/control 状态转移路径
  轨迹验收结果和训练数据质量门禁

不做：
  Matter Endpoint / Cluster / Attribute
  房间拓扑和户型几何
  tick 连续物理仿真
  time_control、memory、query_events
  真机后端依赖
```

SimuHome 只借鉴以下结构：房间索引、设备索引、先发现再执行、设备动作与状态分离、环境聚合结果可被验证。其 Matter 层级、tick 系统、工作流和多设备物理影响不复制到 V1.2。

### 4.4 数据交付

旧 V1 数据保留在 `data_processed/v1/` 作为历史验收产物。V1.2 重新生成独立数据，不在旧 JSONL 上做字段拼接：

```text
homeflow_demo/data_processed/v1.2/
├── scenarios_train.jsonl
├── scenarios_val.jsonl
├── scenarios_eval.jsonl
└── manifest.json
```

初始规模沿用当前 Demo 的可控范围：

```text
train：80
val：  20
eval： 40
```

任务至少覆盖：单设备控制、多设备控制、查询后控制、温度阈值、湿度阈值、正确不动作、传感器只读拒绝、缺少目标设备。

### 4.5 V1.2 验收

```text
房间可以独立枚举，不能通过猜 device_id 访问设备
inspect_room 返回房间全部设备摘要
inspect_device 返回完整 state 和 actions
sensor 的 actions 必须为空，任何写动作都返回 UNSUPPORTED_ACTION
set_temperature / set_percentage / set_mode 参数范围可发现且可重复校验
错误返回统一为 ok/data/error/meta 外壳
非法动作不产生部分状态写入
同一 Scenario 重置后得到完全一致的初始状态
同一轨迹重复执行得到一致 final_result
同一场景 fork 出的 rollout 相互隔离
同一轨迹重复评测得到一致 EpisodeEvaluation
成功轨迹满足 accepted_for_sft=true，失败原因进入 rejection_reasons
策略错误、环境故障和任务定义错误可以稳定区分
数据筛选、奖励计算和冻结评测读取同一评测结果结构
旧 V1.1 代码测试不再作为新协议验收依据，V1.2 测试覆盖新契约
```

### 4.6 进入 V2 的条件

```text
V1.2 核心测试通过
V1.2 场景全部通过 schema 校验
Oracle 能在新工具协议下完成可行任务
成功和失败轨迹都能被保存、读取、重放和重新评测
EpisodeEvaluation 可以独立判断轨迹能否进入 SFT 数据
eval 场景与 train 场景无 scenario_id 重叠
不依赖 DeepSeek 也能完成环境执行、轨迹评测和质量筛选闭环
```

## 5. V2：训练数据合成与 LoRA-SFT 基线

### 5.1 版本目标

建立“场景生成 -> A 产生 DeepSeek/Oracle 候选 -> C 驱动 B 执行与评测 -> 高质量成功数据 -> SFT 模型”的离线链路。V2 不做在线 RL，先证明候选轨迹经过统一评测后可以形成可靠训练数据，并让模型学会统一工具协议。

### 5.2 交付模块

```text
homeflow_demo/data/deepseek_teacher.py
  读取 .env.deepseek，调用 OpenAI 兼容接口并保存 request/response 审计。

homeflow_demo/data/teacher_prompt.py
  生成工具 schema、用户任务和输出约束，要求模型只给结构化 assistant turn。

homeflow_demo/data/trajectory_parser.py
  解析 JSON、assistant turn、tool call 和 finish，格式错误单独记录。

homeflow_demo/data/candidate_runner.py
  把候选轨迹交给 C 模块，由 C 驱动 A 与 B 完成交互，保存 tool events、final_result 和 EpisodeEvaluation；自身不重复判断成功。

homeflow_demo/data/deduplicator.py
  按 scenario_id、动作序列和最终状态去重。

homeflow_demo/data/sft_dataset_builder.py
  只把 verified_success 和合格 Oracle 轨迹转换为 SFT 消息。

homeflow_demo/train/sft.py
  使用 Transformers + PEFT + TRL 完成 LoRA-SFT。
```

### 5.3 数据流和文件

```text
v1.2 train scenarios
        │
        ├── Oracle planner ───────────────> oracle_trajectories.jsonl
        │
        └── DeepSeek candidates
                 │
                 v
          trajectory parser
                 │
                 v
          C. 回合管理 + 基础评测
          （C 驱动 B 执行，并读取隐藏真值）
                 │
                 ├── verified_success.jsonl
                 ├── verified_failure.jsonl
                 ├── parse_errors.jsonl
                 └── oracle_fallback.jsonl
                 │
                 v
          SFT dataset builder
                 │
                 ├── sft_train.jsonl
                 └── sft_val.jsonl
```

目录：

```text
homeflow_demo/data_raw/v2/deepseek/
homeflow_demo/data_processed/v2/
├── teacher_candidates.jsonl
├── verified_success.jsonl
├── verified_failure.jsonl
├── oracle_trajectories.jsonl
├── sft_train.jsonl
├── sft_val.jsonl
└── manifest.json

homeflow_demo/checkpoints/v2_sft/
├── adapter_config.json
├── adapter_model.safetensors
└── train_state.json
```

### 5.4 API 和数据隔离

```text
只允许 train 场景调用 DeepSeek
val 只用于选择 prompt / checkpoint，不生成最终训练标准
eval 场景冻结，不调用 DeepSeek 产生参考轨迹
原始响应与清洗数据分目录保存
日志不写入 API key 或 Authorization header
每条响应保留 request_id、模型名、prompt_version、重试次数
```

### 5.5 SFT 初始规模

第一轮只做可验证的 Demo 规模：

```text
训练场景：80
每个训练场景候选：2～3 条
目标成功轨迹：120～240 条，包含 Oracle 和 DeepSeek 来源标记
训练/验证：8:2
模型：Qwen2.5-1.5B-Instruct
更新：LoRA，先不做全量参数训练
```

### 5.6 V2 验收

```text
API 解析失败不会中断整批生成
每条 verified_success 都能在 V1.2 环境重放成功
每条进入 SFT 的记录都有 accepted_for_sft=true
失败轨迹不进入主 SFT 数据
SFT 数据中 tool name、参数和 tool result 可重新解析
train / val 没有 scenario_id 重叠
SFT adapter 可以保存并重新加载
Base 与 SFT 可以在同一批冻结场景上完成 smoke eval
至少一种单设备任务的合法工具调用率高于 Base
```

### 5.7 V2 不做的内容

```text
不把 DeepSeek 判断当作最终 reward
不把未验证候选直接加入 SFT
不训练 GRPO
不接 vLLM
不引入完整 Matter 协议
```

## 6. V3：在线 Rollout 与 LoRA-GRPO 最小闭环

### 6.1 版本目标

让 V2 的 SFT 模型作为 A 模块进入 C，由 C 驱动 A 与 B 在线生成轨迹；同一 EpisodeEvaluation 产生 reward，再按照同一任务的多条 rollout 计算组内相对优势并完成 LoRA-GRPO 更新。

### 6.2 训练框架

```text
Transformers：模型加载和原生生成
PEFT：         LoRA adapter
TRL：          训练组件和参考实现
Accelerate：   单卡训练配置、梯度累积和 checkpoint 管理
bitsandbytes： 显存不足时再启用 QLoRA，不作为第一默认路径
Gymnasium：    仅作为可选外部适配器，不作为 HomeEnv 核心依赖
```

第一版使用 Transformers 原生 rollout，先保证 token、tool event 和环境状态一一对应。vLLM 留到性能优化阶段，不在最小闭环中引入额外的生成后端差异。

### 6.3 交付模块

```text
homeflow_demo/train/rollout_types.py
  定义 Rollout、Turn、TokenAlignment、RolloutBatch。

homeflow_demo/train/rollout_runner.py
  组织模型生成、assistant/tool-call 封装解析、规范化 ToolCall 派发、HomeEnv step 和多轮上下文拼接；动作 schema 校验由 HomeEnv 完成。

homeflow_demo/train/token_alignment.py
  只标记模型 completion token；tool result 和系统提示不进入 policy loss。

homeflow_demo/train/reward.py
  读取 C 模块 EpisodeEvaluation，提取总 reward 和 reward_components，不重新解释环境事件。

homeflow_demo/train/grpo.py
  计算 group-relative advantage，执行 LoRA policy 更新。

homeflow_demo/train/checkpoint.py
  保存 adapter、optimizer、scheduler、reference 配置和训练 manifest。
```

### 6.4 一次 RL rollout

```text
Scenario
  -> C.reset(Scenario)
  -> C 向 A 提供 observation
  -> A 生成 assistant turn
  -> C 解析模型消息封装，提取 ToolCall / finish
  -> B 校验工具/action/参数并执行 ToolCall
      -> B 返回 tool result / state diff
      -> C 更新 EpisodeEvaluation
  -> C 返回 observation、tool events、EpisodeEvaluation
  -> 拼回下一轮上下文
  -> 直到 success / failure / truncation
  -> 保存 completion token、old logprob、reward、错误归因和 final_result
```

一个 group 的关系：

```text
同一个 scenario + 同一个初始状态
    ├── rollout_0 -> reward_0
    └── rollout_1 -> reward_1

advantage_i = normalize(reward_i - mean(group_rewards))
```

每条 rollout 必须使用独立的 HomeEnv 状态副本；上一条轨迹的设备变化不得污染下一条轨迹。

### 6.5 V3 初始配置

```text
基座：                 V2 SFT LoRA checkpoint
num_generations：      2
RL prompts：           40～80
optimizer steps：      30～80
max assistant turns：  6
max completion length：128～256
gradient accumulation：4～8
LoRA 更新：            只更新 adapter
rollout：              Transformers 原生生成
reward source：        C 模块 EpisodeEvaluation.reward
```

### 6.6 V3 验收

```text
同一 scenario 的 group rollout 从完全相同的初始状态开始
rollout 状态互相隔离
completion_mask 只覆盖模型生成部分
每条 rollout 都有 final_result 和 reward_components
每条 rollout 都有对应的 EpisodeEvaluation
至少部分 group 存在非零 reward 方差
GRPO 可以完成至少 30 个 optimizer steps
adapter、optimizer 和 scheduler 可以恢复
训练后 checkpoint 可以单独运行 eval
非法动作和环境故障在 reward 中按规则分开
```

如果 loss 下降但 C 评测得到的任务成功率下降，先检查 reward、token mask、tool result 拼接和终止条件，不把 loss 下降视作训练成功。

### 6.7 V3 不做的内容

```text
不做全量参数 GRPO
不做多卡并行
不把 DeepSeek 作为在线 reward model
不伪造随机后端故障来宣称真机鲁棒性
不在没有 reward 方差的情况下盲目扩大训练步数
```

## 7. V4：汇总评测、迁移和消融

### 7.1 版本目标

基础评测能力已经在 V1.2 建立，并在 V2 数据筛选和 V3 在线奖励中持续使用。V4 不新建第二套评测器，只把 C 模块切换到冻结 eval Scenario 的批量运行模式，回答三个研究问题：

```text
SFT 是否真的提高了工具协议和基本任务能力？
GRPO 是否在 HomeEnv 成功率上进一步提高？
提升来自任务策略，还是来自记忆设备 ID、背诵模板或 reward loophole？
```

### 7.2 冻结测评运行方式

评测 runner 调用 C 模块；A 提供被测模型，B 提供环境执行，只接收模型 checkpoint 和冻结 Scenario，不读取教师标准轨迹：

```text
checkpoint + eval Scenario
          │
          v
    model rollout
          │
          v
 C. 回合与评测框架
          │
          ├── final_result
          ├── tool_events
          ├── reward_components
          └── episode failure class
          │
          v
        metrics
          │
          v
      report.md
```

### 7.3 评测模块

```text
homeflow_demo/eval/run_eval.py
  在冻结 split 上运行 Base / SFT / RL。

homeflow_demo/eval/metrics.py
  沿用 V1.2 指标字段，聚合任务成功率、完成度、合法率、错误分布和效率。

homeflow_demo/eval/compare_runs.py
  对齐同一场景上的 Base/SFT/RL 结果。

homeflow_demo/eval/report.py
  生成 JSON、CSV 和 Markdown 报告。
```

### 7.4 核心指标

```text
task_success_rate        全部隐藏目标满足的 episode 比例
goal_completion          最终 conditions 完成度
keep_preservation        无关状态保持通过率
tool_parse_rate          assistant 输出可解析比例
valid_action_rate        合法工具调用比例
strategy_error_rate      策略错误码比例
environment_failure_rate 执行环境故障比例
mean_turns               平均 assistant turn 数
mean_tool_calls          平均工具调用数
unnecessary_call_rate    多余查询和重复动作比例
```

### 7.5 必测任务切分

```text
已见任务模板 + 已见设备组合
已见任务模板 + 未见设备组合
未见自然语言措辞 + 已见状态组合
温度传感器读取与空调控制
湿度传感器读取与条件控制
条件不满足时的正确不动作
传感器写入拒绝
未知房间 / 未知设备 / 不支持动作
多设备目标与 keep 条件
```

### 7.6 语义迁移验证

V4 只验证统一语义能否迁移，不把真机接入当成 HomeEnv 单元测试的一部分：

```text
同一条语义轨迹
  -> Fake/HomeEnv backend
  -> HA/MCP adapter 的 dry-run 或 contract test

比较：
  tool name
  参数结构
  result envelope
  state 字段
  action 名称
  error code
```

真机实际服务调用、异步回读、设备掉线和延迟归入 adapter 测试与独立实验。HomeEnv 达成目标不等价于真机一定达成目标。

### 7.7 必做消融

```text
Base vs SFT vs RL
Oracle 轨迹 vs DeepSeek 轨迹
只用终局奖励 vs 加 progress shaping
错误码统一惩罚 vs 策略错误/环境故障分离
有 observe/inspect 发现链 vs 初始暴露设备库存
无温湿度传感器 vs 有只读传感器
GRPO group=2，必要时对比 group=4
LoRA rank=8 与 rank=16
```

每次消融只改变一个主要变量，并固定：

```text
模型基座、Scenario split、工具 schema、seed、max_turns、评测脚本、reward 版本
```

### 7.8 V4 交付

```text
homeflow_demo/results/v4/
├── configs/
├── episode_records/
├── metrics/
├── ablations.csv
├── checkpoints_manifest.json
├── reproducibility.md
└── final_report.md
```

报告必须分开写：

```text
已验证事实：测试、指标和重放实际得到的结果
实验观察：多次运行中出现的稳定现象
研究推断：根据结果提出、但尚未被单独证明的解释
残余风险：数据规模、模型随机性、真机迁移和奖励漏洞
```

## 8. 版本交付总表

```text
V1.2 A/B/C 核心框架重写
  主要产物：Home/Room/Device/Sensor、发现式工具、EpisodeEvaluation、质量门禁
  数据产物：data_processed/v1.2 场景与 Oracle
  验收重点：语义正确、可重放、状态隔离、统一成功判定和错误归因
  不依赖：DeepSeek、训练模型、真机

V2 数据合成与 SFT
  主要产物：DeepSeek 原始响应、验证成功轨迹、SFT JSONL、SFT adapter
  验收重点：候选可追溯、C 模块质量门禁、数据无泄漏、SFT 可加载
  不包含：在线 RL

V3 在线 rollout 与 LoRA-GRPO
  主要产物：rollout batch、token 对齐、reward、GRPO adapter
  验收重点：group 隔离、复用 C 模块 reward、训练可恢复、成功率可评估
  不包含：全量 GRPO、多卡、真实后端鲁棒性

V4 汇总评测、迁移与消融
  主要产物：Base/SFT/RL 指标、消融表、迁移 contract test、最终报告
  验收重点：未见组合泛化、错误归因、实验可复现、结论有证据
```

## 9. 执行顺序和暂停条件

```text
当前
  V1.1 完成
  11 号 V1.2 设计讨论稿基本确认
  此前两份旧讨论文档已删除
  12 号整体实施方案完成

下一步
  完成 V1.2 环境与基础评测代码重写
  运行 V1.2 单元测试、场景重放、EpisodeEvaluation 和 Oracle 验收

之后
  才启用 DeepSeek，进入 V2
  V2 SFT 基线通过后，进入 V3
  V3 最小 GRPO 通过后，进入 V4
```

任何阶段出现以下情况时暂停扩大规模：

```text
环境状态不可重放
训练/评测出现 scenario_id 泄漏
tool result 与 token mask 对不上
group reward 没有有效方差
环境故障被计入策略负奖励
SFT/RL 指标只在训练场景上提升
```

## 10. 本方案的最终边界

```text
核心目标：验证统一 HomeEnv 语义是否能支撑 1.5B 模型的 SFT 与 LoRA-GRPO

保留：
  房间发现、设备发现、动作 schema、温湿度只读传感器、确定性状态转移、隐藏目标、轨迹审计

暂缓：
  Matter 细粒度对象、时间工作流、连续物理仿真、复杂记忆、真实用户循环、完整 Home Assistant 运行时

研究原则：
  先让环境与基础评测共同成为可靠真值源；候选数据先评测再进入 SFT；RL 复用同一 reward；最后只做冻结场景上的汇总比较、迁移和消融
```
