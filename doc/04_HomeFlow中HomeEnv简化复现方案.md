# HomeFlow 中 HomeEnv 简化复现方案

> 方案日期：2026-09-20  
> 目标：实现一个足以支撑智能家居 SFT 数据生成与环境奖励强化学习的简化 HomeEnv。  
> 定位：机制复现，不追求 HomeFlow 论文的设备规模、MCTS 数据量、96×H20 训练规模或最终分数复现。

## 1. 结论

### 1.1 Gym 是否必要

需要区分“Gym 语义”和“Gymnasium 依赖”。

```text
必须具备的 Gym 语义：
  reset(seed, scenario)
  step(action)
  observation
  reward
  terminated
  truncated
  info
  独立 episode
  可复现随机性

第一版不必强制具备：
  继承 gymnasium.Env
  gymnasium.make 注册
  用 Space 完整描述变长文本和 JSON
  直接接入通用经典 RL 算法库
```

结论是：

> 对强化学习而言，Gym 风格的 episode 与 step 契约是必要的；具体使用 Gymnasium 类库不是必要条件。简化版应先实现框架无关的 `HomeEpisodeEnv`，再提供一个很薄的 `GymHomeEnvAdapter`。

这样做有四个原因：

| 原因 | 说明 |
|---|---|
| SFT 不依赖 Gym | SFT 消费的是已经验证的多轮消息轨迹，不会直接调用 `gym.make` |
| LLM RL 不等于经典离散动作 RL | 策略先生成 token，再解析成工具动作，训练器还要保存 token logprob 与动作回合的对应关系 |
| HomeEnv 还需要 Gym 没定义的能力 | SFT 搜索需要快照、恢复、分支复制和完整轨迹日志 |
| 薄适配器足够获得生态兼容 | 核心稳定后再补 `action_space`、`observation_space`、环境注册和 `env_checker` |

官方 Gymnasium 环境契约要求 `reset` 返回初始观测和 `info`，`step` 返回观测、奖励、`terminated`、`truncated` 与 `info`。本方案保留这组语义，但让核心代码不依赖 Gymnasium 包。

### 1.2 简化复现的主线

```text
设备规格 + 初始家庭状态 + 任务场景
                    |
                    v
              HomeStateEngine
              确定性状态转移
                    |
        +-----------+-----------+
        |                       |
        v                       v
  PredicateEvaluator       ActionAuditor
  目标完成度 m_t            非法/越界/副作用
        |                       |
        +-----------+-----------+
                    v
              HomeEpisodeEnv
      reset / step / reward / termination
                    |
        +-----------+-----------+
        |                       |
        v                       v
   SFTTrajectoryBuilder     HomeEnvRolloutCollector
   生成并筛选成功轨迹        在线采样环境 episode
        |                       |
        v                       v
    SFTDataset              GRPO / RLVE
```

第一版不实现 `pyexec`。模型通过结构化工具调用控制环境：

```text
query_device
control_device
ask_user
finish
```

其中 `query_device`、`control_device` 和 `ask_user` 作为模型可见工具；`finish` 是环境内部动作。模型在某个 assistant turn 不再发工具调用而直接给出最终回复时，rollout collector 将该回复包装成 `FinishAction(text)`。

这足以验证 HomeFlow 的核心机制：

```text
环境执行动作
  -> 状态变化
  -> 条件完成度变化
  -> 生成监督轨迹
  -> 产生强化奖励
```

`pyexec` 是论文协议复现能力，可以在第二阶段作为 adapter 增加。第一版直接实现它，会把主要工作转移到 Python 沙箱、安全隔离和代码审计上，延迟 SFT/RL 闭环验证。

## 2. 复现目标与非目标

### 2.1 必须完成的目标

```text
G1  同一初始状态和动作序列产生完全相同的最终状态
G2  非法动作被拒绝，且不能修改环境
G3  每一步返回目标完成度、奖励分量和状态差异
G4  成功轨迹可以直接转换为 MiniMind SFT conversations
G5  MiniMind 多轮 rollout 能用真实 HomeEnv 替换 MOCK_RESULTS
G6  环境终局奖励可以替换当前的文本 GT 匹配奖励
G7  同一任务可采样多个候选 episode，形成组相对优势
G8  核心环境不依赖模型框架、Gymnasium 或 HTTP 服务
```

### 2.2 第一版明确不做

```text
不做连续热力学、光照传播和真实传感器噪声
不做时间调度、Cron 和持续设备过程
不做 HomeMaker 大规模程序化家庭生成
不做 MCTS-Flow 树搜索
不做 Python pyexec 沙箱
不做 GPT-5 动态用户模拟器
不做 1,678 条 SmartHome-Bench 重建
不做自动化与纯环境查询两个扩展任务族
不做真机 Home Assistant / MCP 接入
```

这些能力不会被写死为“不支持”。核心接口要为后续时间推进、MCTS 分支、`pyexec` 和真机 adapter 留出扩展位。

## 3. Gym 风格契约分析

### 3.1 为什么 RL 必须有 episode 契约

当前状态、模型输出和奖励必须形成稳定 transition。这里的 `action_t` 指一次 assistant turn，不等于 turn 内部的每个底层工具调用：

```text
observation_t
      |
      v
policy 生成一次 assistant turn 文本
      |
      v
解析为 AssistantTurn_t
      |
      v
env.step(AssistantTurn_t)
      |
      +-> observation_(t+1)
      +-> reward_t
      +-> terminated
      +-> truncated
      +-> info
```

缺少这组契约会出现三个直接问题：

```text
状态归属不清：
  无法确定模型看到的状态与动作后的状态属于哪个时刻。

奖励归因不清：
  无法判断哪次工具调用使目标完成度发生变化。

回合边界不清：
  模型停止生成、任务完成和步数耗尽会混成一个 done。
```

### 3.2 为什么核心不直接继承 `gymnasium.Env`

本任务中的动作和观察天然是变长结构：

```text
Action：
  JSON 工具名
  变长参数对象
  自然语言澄清问题或最终响应

Observation：
  用户请求
  设备索引
  某次查询结果
  某次控制状态差异
  错误信息
  对话历史
```

它们可以被包装为 `spaces.Text` 或嵌套 `Dict`，但这样做不会帮助 MiniMind 的 token 级训练。训练器仍需自行完成：

```text
文本生成
  -> 工具调用解析
  -> 环境执行
  -> 工具结果重新写入聊天模板
  -> 保存模型 token mask 和 logprob
```

此外，SFT 数据探索还需要：

```text
snapshot()
restore(snapshot)
fork()
trajectory()
```

这些都不属于标准 Gym API。

因此，核心先定义自己的强类型契约：

```python
class HomeEpisodeEnv:
    def reset(self, scenario, seed=None) -> ResetResult: ...
    def step(self, assistant_turn) -> StepResult: ...
    def snapshot(self) -> Snapshot: ...
    def restore(self, snapshot) -> None: ...
```

Gymnasium adapter 只负责返回格式转换：

```python
class GymHomeEnvAdapter(gym.Env):
    def reset(self, seed=None, options=None):
        result = self.core.reset(options["scenario"], seed)
        return result.observation, result.info

    def step(self, assistant_turn):
        result = self.core.step(assistant_turn)
        return (
            result.observation,
            result.reward,
            result.terminated,
            result.truncated,
            result.info,
        )
```

### 3.3 Gym adapter 何时加入

推荐在核心环境通过集成测试后立即加入，但不让训练代码依赖它。

```text
核心环境调用路径：
  MiniMind collector -> HomeEpisodeEnv

兼容性验证路径：
  GymHomeEnvAdapter -> HomeEpisodeEnv

后续标准框架路径：
  Gymnasium VectorEnv / RLlib -> GymHomeEnvAdapter
```

这样既保留标准契约，又避免训练主线增加无意义的序列化和 adapter 层开销。

### 3.4 `terminated` 与 `truncated` 的定义

简化版明确区分：

```text
terminated = True
  agent 调用 finish，且全部目标成立：任务成功
  agent 提前调用 finish，目标未完成：任务失败
  场景定义了不可恢复失败，且该失败已经发生

truncated = True
  达到 max_env_steps
  达到 max_dialogue_turns
  模型上下文达到 token 上限
  单步执行超时
```

目标条件全部成立时，环境先返回 `ready_to_finish=true`，不会立即终止。模型需要再发出 `finish`，从而保留最终自然语言响应的训练位置。

这与 HomeFlow 论文中“全部条件满足即可终止”的描述略有差异，是简化版为了兼容工具对话 SFT 所做的明确改动。后续可以通过配置切换为 `auto_terminate_on_success=true`。

## 4. 最小领域模型

### 4.1 HomeState

职责：保存一局 episode 的完整物理真值。

输入：场景中的初始房间、设备和属性。

输出：只供环境内核读取和修改的当前状态。

```text
HomeState
  home_id
  rooms: room_id -> Room
  devices: did -> DeviceState
  step_index
  dialogue_turn
  done
```

不负责：面向模型的文本序列化、奖励计算、训练日志。

### 4.2 Room

```text
Room
  room_id
  name
  room_type
  floor
  parent_id: optional
```

第一版保留嵌套房间字段，但不实现空间传播。

### 4.3 DeviceSpec 与 DeviceState

静态能力和动态状态分开保存：

```text
DeviceSpec
  spec_id
  category
  attributes_schema
  services
  components

DeviceState
  did
  spec_id
  name
  room_id
  attributes
  component_attributes
```

服务定义：

```text
ServiceSpec
  locator
  arguments_schema
  effects
  preconditions
```

第一版不在配置中保存任意 Python `code`，而是使用声明式 effect：

```text
locator: set_brightness
arguments:
  brightness: int [1, 100]
effects:
  brightness <- arguments.brightness
```

这样可以避免设备规格文件内嵌任意执行代码。

### 4.4 第一版设备范围

```text
light
  state
  brightness
  color_temperature

ac
  state
  mode
  target_temperature

fan
  state
  speed_level
  oscillating

fan_light
  light.state
  light.brightness
  fan.state
  fan.speed_level

curtain
  state
  position

climate_sensor
  temperature
  humidity

speaker
  state
  volume
  muted
  playback_state
```

这七类设备足以覆盖：组件路径、数值参数、枚举参数、传感器筛选、多设备组合和状态依赖选择。

## 5. 场景与目标结构

### 5.1 Scenario

一条训练或评测任务定义为：

```text
Scenario
  scenario_id
  task_family
  initial_home
  user_request
  history
  memory
  goal_predicates
  allowed_mutations
  clarification_script
  max_env_steps
  max_dialogue_turns
  metadata
```

其中：

```text
goal_predicates
  决定任务是否完成

allowed_mutations
  决定哪些设备属性允许被改变

clarification_script
  当模型提出合法澄清时，返回预先定义的用户回答
```

`allowed_mutations` 必须独立存在，不能仅从最终目标推断。示例：

```text
用户要求：
  开启客厅空调并设为 24°C。

goal_predicates：
  ac_1.state == on
  ac_1.target_temperature == 24

allowed_mutations：
  ac_1.state
  ac_1.target_temperature
  ac_1.mode        # 若设备前置条件要求设置模式，可明确允许
```

否则无法区分合理前置操作和无关副作用。

### 5.2 安全谓词 AST

第一版不执行 `device(...).attribute == value` 形式的 Python 字符串。条件使用结构化 AST：

```text
all
  eq(path="devices.ac_1.state", value="on")
  between(path="devices.ac_1.target_temperature", low=23.5, high=24.5)
```

最小操作符：

```text
all
any
not
eq
ne
gt
ge
lt
le
between
in
```

第一版不支持任意函数调用、属性反射和动态表达式。

### 5.3 条件完成度

```text
K   = 原子目标条件数量
m_t = 当前满足的原子条件数 / K
```

每一步都从当前状态重新计算，已经满足的条件可以被后续动作破坏：

```text
t1：2/3 完成
t2：模型误关空调 -> 1/3 完成

delta_progress = 1/3 - 2/3 = -1/3
```

不能把条件一旦完成就永久锁定，否则模型可以先满足目标再破坏状态而仍获得成功。

## 6. 最小动作与观察协议

### 6.1 模型回合与工具动作

模型的一个 assistant turn 是一个策略决策步。turn 内部可以包含工具调用；工具调用是环境执行层的原子事件，不自动形成额外的 RL transition。

为了让第一版实现保持简单，V1.1 默认将 `max_tool_calls_per_turn` 设为 1，但数据结构直接使用数组，后续可以放开为多个工具调用。

```text
query_device
  用过滤条件查询候选设备，或读取指定设备的规格与状态

control_device
  调用一个设备服务

ask_user
  对缺失槽位提出一个澄清问题

finish
  返回最终自然语言响应并结束任务
```

前三类通过工具调用解析；若 assistant 输出不含工具调用，则解析器生成：

```text
FinishAction
  text = assistant 最终自然语言回复
```

这样 SFT 数据中的最后一轮仍是普通 assistant 文本，不需要训练一个用户侧不可见的 `finish` 工具。

动作示例：

```json
{
  "type": "control_device",
  "did": "ac_1",
  "locator": "set_target_temperature",
  "arguments": {
    "temperature": 24
  }
}
```

当前 V1 的原子动作接口确实一次只执行一个工具动作；这是底层状态机和 Oracle 的实现方式。面向 SFT/RL 的 V1.1 不再把一个模型 completion 拆成多个环境 step：一个 turn 内的多个工具调用由环境内部顺序执行，最终只生成一条 turn transition。多设备任务是否跨多个 turn，由模型实际输出决定。

### 6.2 初始观察

```text
Observation
  user_request
  history
  memory
  rooms_summary
  device_index
  last_tool_result
  step_budget
  ready_to_finish
```

初始观察只给房间和设备索引：

```text
rooms_summary：
  客厅、主卧、书房

device_index：
  ac_1：客厅空调
  light_1：客厅灯
  fan_light_1：书房风扇灯
```

属性当前值、服务名、参数范围需要通过 `query_device` 获取。

### 6.3 工具结果观察

查询结果：

```text
ok
device
state
services
components
```

控制结果：

```text
ok
error_code
message
state_diff
goal_progress_before
goal_progress_after
ready_to_finish
```

面向模型的 observation 不包含完整目标谓词、全量 HomeState 和奖励数值。奖励与调试字段只放入 `info`，避免信息泄漏。

### 6.4 错误码

```text
DEVICE_NOT_FOUND
SERVICE_NOT_FOUND
COMPONENT_NOT_FOUND
MISSING_ARGUMENT
UNKNOWN_ARGUMENT
TYPE_MISMATCH
VALUE_OUT_OF_RANGE
INVALID_ENUM
PRECONDITION_FAILED
MUTATION_NOT_ALLOWED
CLARIFICATION_NOT_AVAILABLE
ACTION_AFTER_DONE
MALFORMED_ACTION
```

错误码必须稳定。SFT 轨迹可以学习根据错误修正动作，RL 也可以用错误类型生成审计惩罚。

## 7. 环境执行顺序

`step(assistant_turn)` 固定按以下顺序执行：

```text
1  检查 episode 是否已经结束
2  解析 assistant turn 结构
3  保存 before snapshot
4  逐个校验 turn 内的 tool call
5  执行工具调用并记录 tool_events
6  应用确定性状态转移
7  生成 after snapshot 与 state diff
8  检查 diff 是否超出 allowed_mutations
9  重新计算全部目标条件与 m_t
10 汇总本 turn 的奖励分量
11 更新 turn_index 与 dialogue_turn
12 判定 terminated / truncated
13 构造 observation 与 info
```

控制动作必须满足事务性：

```text
校验全部成功
  -> 一次性提交状态变化

任何校验失败
  -> 状态保持 before snapshot
  -> 返回审计错误
```

## 8. 奖励设计

### 8.1 第一版奖励

```text
r_t = lambda_progress * (m_t - m_(t-1))
    + lambda_success  * success_t
    - lambda_invalid  * invalid_t
    - lambda_side     * side_effect_t
    - lambda_step
    - lambda_finish   * premature_finish_t
```

建议初始权重：

```text
lambda_progress = 1.0
lambda_success  = 1.0
lambda_invalid  = 0.5
lambda_side     = 1.0
lambda_step     = 0.01
lambda_finish   = 0.5
```

权重放在版本化配置中，不写死在环境逻辑里。

### 8.2 奖励分量定义

```text
progress
  当前条件完成比例减去上一步完成比例，可正可负。

success
  finish 时全部目标成立，取 1，否则取 0。

invalid
  动作结构、设备、服务或参数不合法，取 1。

side_effect
  状态差异包含 allowed_mutations 以外路径，取 1。

step
  每个环境动作固定成本，抑制无限查询。

premature_finish
  目标未完成时调用 finish，取 1，并终止为失败。
```

`info` 必须返回原始分量：

```json
{
  "reward_components": {
    "progress": 0.3333,
    "success": 0.0,
    "invalid": 0.0,
    "side_effect": 0.0,
    "step_cost": -0.01,
    "premature_finish": 0.0
  }
}
```

训练报告不能只记录总 reward，否则无法判断模型是在完成任务，还是仅仅减少非法动作。

### 8.3 SFT 与 RL 使用同一验证器

```text
SFT 轨迹保留条件：
  success == true
  invalid_action_count == 0
  side_effect_count == 0
  全部目标在终局成立

RL 奖励：
  使用同一个目标完成度与审计结果计算逐步 reward
```

两条链若使用不同条件实现，会出现“训练数据认为成功，RL 环境认为失败”的口径分裂。

## 9. SFT 数据生成方案

### 9.1 第一阶段不做 MCTS

机制验证不需要先实现树搜索。第一版采用：

```text
每个 Scenario
  -> oracle / teacher 生成 N 条候选轨迹
  -> 每条从相同 initial_home reset
  -> HomeEpisodeEnv 逐步执行
  -> 严格验证
  -> 成功轨迹去重
  -> 转换为 conversations JSONL
```

候选来源分两种：

```text
规则 oracle
  用于证明环境可解、生成最短正确轨迹、构建测试金标。

教师 LLM
  用于生成不同查询顺序、澄清方式和动作路径。
```

规则 oracle 不能作为最终大规模数据生成方法，但必须存在。没有 oracle 的场景无法区分“模型不会”与“任务不可解”。

### 9.2 SFT 消息结构

MiniMind 的 `SFTDataset` 已支持 system 中的 `tools` 和 assistant 的 `tool_calls`。成功轨迹转换为：

```text
system
  智能家居规则 + tools schema

user
  用户请求

assistant
  query_device tool call

tool
  设备规格和状态

assistant
  control_device tool call

tool
  执行结果与状态差异

assistant
  普通自然语言确认；collector 将其解释为 FinishAction
```

SFT label 只覆盖 assistant token；system、user 和 tool observation 作为上下文，不计算语言模型损失。当前 `SFTDataset.generate_labels` 已采用这一基本方式。

### 9.3 第一版数据规模

```text
任务场景：100 条
每个任务族：20 条
每个场景候选轨迹：5 条
目标成功轨迹：每场景至少 2 条
最终 SFT 数据：200 至 500 条
```

五个任务族：

```text
F1 原子控制
F2 多设备与状态依赖控制
F3 缺失槽位与脚本化澄清
F4 对话历史中的指代与修正
F5 用户记忆与偏好应用
```

这个规模只用于验证数据格式、训练收敛方向和环境奖励。不能用于声明达到 HomeFlow 论文能力。

### 9.4 轨迹去重

去重签名：

```text
trajectory_signature = hash(
  sequence of action.type,
  normalized device category,
  normalized service locator,
  query/control ordering
)
```

只按自然语言文本去重不够。同一工具路径的措辞改写仍然是同一行为示范。

## 10. 强化学习接入方案

### 10.1 本地 MiniMind 现状

当前仓库已有两条相关能力：

```text
minimind/trainer/train_agent.py
  支持多轮工具调用
  支持把 tool observation 插回上下文
  保存 assistant token mask 与旧策略 logprob

现有限制
  工具来自进程内 MOCK_RESULTS
  工具没有持久环境状态
  reward 主要检查工具数量、参数格式和文本 GT
  每个样本没有独立 HomeEnv episode
```

因此不需要重写模型生成与 GRPO/CISPO 主体。正确修改层级是工具执行与奖励来源。

### 10.2 新增 HomeEnv rollout collector

```text
输入：
  scenario batch
  policy model
  tokenizer
  num_generations

处理：
  为每个 scenario × generation 创建独立 HomeEpisodeEnv
  reset
  构造初始 messages
  模型生成一个 assistant turn
  解析一个或多个工具调用
  env.step(assistant_turn)
  将 observation 追加为 tool message
  重复直到 terminated / truncated

输出：
  完整 messages
  assistant token ids
  assistant token mask
  old logprobs
  step rewards
  episode return
  success / audit metrics
```

关键隔离关系：

```text
一个训练 batch 中：

scenario_1 × generation_1 -> env_1_1
scenario_1 × generation_2 -> env_1_2
scenario_1 × generation_3 -> env_1_3

三个 env 从相同初始状态开始，但状态互不共享。
```

不能让多个 generation 共用一个环境，否则前一个候选动作会污染后一个候选。

### 10.3 第一阶段 RL：turn-level episode rollout

先复用当前 `train_agent.py` 的组相对训练方式：

```text
同一 scenario 生成 G 条完整 episode
  -> 每条得到 episode_return
  -> 同组内标准化形成 advantage
  -> 每个 assistant turn 的 token 使用该 turn 对应的 reward 或 return-to-go
```

episode return：

```text
R_episode = sum(r_t)
```

这不是论文完整的逐步 RLVE 信用分配，但实现简单，能够先验证：

```text
环境成功率是否提高
非法动作率是否下降
平均工具调用是否变化
策略是否学会先查询再控制
```

### 10.4 第二阶段 RL：turn-level return-to-go

完成 episode-level 训练后，再为每个 assistant turn 保存 token 区间：

```text
turn_1 assistant tokens [a:b] -> reward r_1
turn_2 assistant tokens [c:d] -> reward r_2
turn_3 assistant tokens [e:f] -> reward r_3
```

计算：

```text
G_t = r_t + gamma*r_(t+1) + ...
```

每个 turn 的 token 使用对应 `G_t` 或归一化 advantage。这样才接近 HomeFlow 所说的逐步 RLVE。

不要在第一版做 token 内部的工具动作拆分。环境只知道 turn 中的工具事件和最终状态，不知道单个 token 的物理含义；把 turn reward 均匀分配给该 turn 的 assistant token 已足够。

### 10.5 需要修改的本地训练接口

```text
现有：
  execute_tool(name, args) -> MOCK_RESULTS

修改后：
  env.step(parsed_assistant_turn) -> StepResult
```

```text
现有：
  gt_batch = 文本答案或工具数量参考

修改后：
  scenario_batch = 场景 ID 或完整 Scenario
```

```text
现有：
  calculate_rewards(...) -> 文本/格式启发式分数

修改后：
  collect_episode_return(step_results) -> 环境回报
```

格式合法率、重复惩罚等可以作为小权重辅助项保留，但不能压过环境任务奖励。

## 11. 模块规格

### 11.1 `domain/models.py`

职责：定义 `Room`、`DeviceSpec`、`DeviceState`、`HomeState`、`Scenario`、`Action`、`Observation`、`StepResult`。

输入：结构化 Python 对象或配置解析结果。

输出：强类型领域对象。

读取：无外部状态。

写入：无。

不负责：状态转移、奖励、文件加载。

对应文件：

```text
homeflow_min/domain/models.py
homeflow_min/domain/models.md
```

### 11.2 `engine/executor.py`

职责：解析设备和服务、校验参数、事务性应用状态转移。

输入：`HomeState`、`ControlAction`、`DeviceSpecRegistry`。

输出：新状态或执行错误、状态差异。

读取：设备规格注册表。

写入：当前 episode 的 `HomeState`。

不负责：奖励、任务终止、自然语言观察。

对应文件：

```text
homeflow_min/engine/executor.py
homeflow_min/engine/executor.md
```

### 11.3 `engine/predicates.py`

职责：解析安全谓词 AST、求值原子条件、计算完成比例。

输入：谓词树、`HomeState`。

输出：每个条件的真假、`m_t`、全部完成标志。

读取：只读家庭状态。

写入：无。

不负责：生成 Blueprint、执行 Python 表达式。

对应文件：

```text
homeflow_min/engine/predicates.py
homeflow_min/engine/predicates.md
```

### 11.4 `engine/audit.py`

职责：检查非法动作、越界参数和不允许的状态变化。

输入：动作、执行结果、before/after diff、`allowed_mutations`。

输出：审计事件和稳定错误码。

读取：场景边界。

写入：episode 审计日志。

不负责：决定总 reward 权重。

对应文件：

```text
homeflow_min/engine/audit.py
homeflow_min/engine/audit.md
```

### 11.5 `engine/snapshots.py`

职责：深复制状态、计算 diff、恢复状态、生成状态哈希。

输入：`HomeState`。

输出：不可变快照、差异集合、哈希。

读取：当前状态。

写入：恢复时替换当前状态。

不负责：MCTS 节点管理。

对应文件：

```text
homeflow_min/engine/snapshots.py
homeflow_min/engine/snapshots.md
```

### 11.6 `env/episode.py`

职责：实现 `reset`、`step`、回合预算、终止和截断。

输入：`Scenario`、动作、随机种子。

输出：`ResetResult`、`StepResult`。

读取：状态引擎、谓词、审计、奖励配置。

写入：episode 当前状态和轨迹。

不负责：模型推理、tokenization、优化器更新。

对应文件：

```text
homeflow_min/env/episode.py
homeflow_min/env/episode.md
```

### 11.7 `env/reward.py`

职责：根据完成度变化、成功、审计和步数成本计算奖励分量。

输入：前后条件状态、审计事件、动作类型。

输出：总 reward 和分量字典。

读取：奖励权重配置。

写入：无。

不负责：修改环境状态。

对应文件：

```text
homeflow_min/env/reward.py
homeflow_min/env/reward.md
```

### 11.8 `env/observation.py`

职责：把内部状态和工具结果投影成模型可见观察。

输入：`HomeState`、动作结果、可观测配置。

输出：结构化 observation 与文本 observation。

读取：当前状态。

写入：无。

不负责：奖励和状态修改。

对应文件：

```text
homeflow_min/env/observation.py
homeflow_min/env/observation.md
```

### 11.9 `env/gym_adapter.py`

职责：把 `HomeEpisodeEnv` 映射成 Gymnasium 五元组接口。

输入：Gym action、`options["scenario"]`。

输出：Gym observation、reward、terminated、truncated、info。

读取：核心环境。

写入：无独立状态，状态归核心环境所有。

不负责：定义领域逻辑。

对应文件：

```text
homeflow_min/env/gym_adapter.py
homeflow_min/env/gym_adapter.md
```

### 11.10 `data/sft_builder.py`

职责：运行 oracle/teacher 候选轨迹、筛选成功 episode、转换 MiniMind conversations。

输入：场景集、候选 agent、轨迹数量。

输出：SFT JSONL 与生成统计。

读取：`HomeEpisodeEnv`。

写入：版本化数据集和 manifest。

不负责：训练模型。

对应文件：

```text
homeflow_min/data/sft_builder.py
homeflow_min/data/sft_builder.md
```

### 11.11 `rl/rollout_collector.py`

职责：连接 MiniMind 模型生成与独立 HomeEnv episode，保存 token、logprob、turn span 和环境奖励。

输入：场景 batch、策略模型、tokenizer、生成参数。

输出：可供 GRPO/CISPO 使用的环境 rollout batch。

读取：`HomeEpisodeEnv`、模型 rollout engine。

写入：可选原始轨迹日志。

不负责：反向传播和优化器更新。

对应文件：

```text
homeflow_min/rl/rollout_collector.py
homeflow_min/rl/rollout_collector.md
```

## 12. 建议目录

```text
homeflow_min/
  README.md

  domain/
    models.py
    models.md

  engine/
    executor.py
    executor.md
    predicates.py
    predicates.md
    audit.py
    audit.md
    snapshots.py
    snapshots.md

  env/
    episode.py
    episode.md
    reward.py
    reward.md
    observation.py
    observation.md
    gym_adapter.py
    gym_adapter.md

  specs/
    light.json
    light.md
    ac.json
    ac.md
    fan.json
    fan.md
    fan_light.json
    fan_light.md
    curtain.json
    curtain.md
    climate_sensor.json
    climate_sensor.md
    speaker.json
    speaker.md

  scenarios/
    train.jsonl
    train.md
    dev.jsonl
    dev.md
    test.jsonl
    test.md

  data/
    oracle_agent.py
    oracle_agent.md
    sft_builder.py
    sft_builder.md

  rl/
    rollout_collector.py
    rollout_collector.md
    environment_rewards.py
    environment_rewards.md

  tests/
    test_executor.py
    test_executor.md
    test_predicates.py
    test_predicates.md
    test_episode.py
    test_episode.md
    test_sft_pipeline.py
    test_sft_pipeline.md
    test_rl_rollout.py
    test_rl_rollout.md
```

每份 `.py` 与 `.json/.jsonl` 均配同名中文 `.md`。代码模块和函数至少包含一行中文注释，说明职责或关键约束。

## 13. 实施阶段

### Phase 0：协议冻结

产物：

```text
Action 数据结构
Observation 数据结构
Scenario 数据结构
Predicate AST
错误码表
奖励分量表
terminated / truncated 规则
```

验收：用手写对象表达三条完整任务，不写环境代码也能明确每一步输入输出。

### Phase 1：确定性状态引擎

范围：

```text
Room / DeviceSpec / DeviceState / HomeState
设备服务解析
类型、范围、枚举校验
组件 locator
事务性状态更新
snapshot / restore / diff
```

验收：

```text
正确动作改变预期属性
错误动作不改变任何属性
风扇灯组件路径正确
相同 seed 与动作序列结果完全一致
快照恢复后状态哈希一致
```

### Phase 2：谓词、审计与 episode

范围：

```text
安全 Predicate AST
条件完成比例
allowed_mutations
reset / step
reward components
terminated / truncated
轨迹日志
```

验收：

```text
正进度、负进度都能计算
提前 finish 被判失败
达到目标后 finish 被判成功
越界和副作用产生独立惩罚
max steps 触发 truncated，不触发 terminated
```

### Phase 3：SFT 数据闭环

范围：

```text
100 条手工/程序化场景
规则 oracle
候选轨迹执行
严格成功过滤
MiniMind conversations 导出
SFT 冒烟训练
```

验收：

```text
oracle 场景可解率 = 100%
导出轨迹重新回放成功率 = 100%
assistant/tool 消息顺序合法率 = 100%
SFT 后结构化工具调用合法率显著高于 base
```

### Phase 4：环境 GRPO 闭环

范围：

```text
每个 generation 独立 env
多轮 tool observation
episode return
group-relative advantage
环境指标日志
```

验收：

```text
同一 scenario 可并行产生 G 条互不污染的 episode
环境 reward 完全替代文本 GT 主奖励
训练前后至少比较任务成功率、完成率和非法动作率
固定配置重复运行，指标方向一致
```

### Phase 5：逐步 RLVE

范围：

```text
assistant turn token span
turn-level reward
return-to-go
逐步 advantage
终局奖励与密集奖励消融
```

验收：

```text
每个 turn 的 reward 能对应到正确 assistant token 区间
破坏已完成目标会产生负进度
密集奖励与仅终局奖励可独立配置
两种配置的训练曲线和最终成功率可比较
```

### Phase 6：Gymnasium adapter

范围：

```text
gymnasium.Env adapter
action_space / observation_space
环境注册
env_checker
可选 SyncVectorEnv 冒烟
```

这一阶段可以提前到 Phase 3 之后，但不能阻塞 SFT/RL 主线。

## 14. 测试与验证闭环

### 14.1 单元测试

```text
设备查询与服务解析
参数类型、范围、枚举
组件 locator
事务回滚
Predicate 每个操作符
状态 diff
allowed_mutations
奖励每个分量
终止与截断
随机种子
```

### 14.2 Golden episode

至少固定十条完整轨迹：

```text
原子灯光控制
空调先开机再设温
风扇灯组件控制
多设备组合控制
状态依赖设备筛选
合法澄清
不必要澄清
参数越界
无关设备副作用
满足目标后又破坏目标
```

每条 golden 保存：

```text
初始状态哈希
动作序列
每步 observation
每步 state diff
每步 reward components
最终状态哈希
终局结果
```

### 14.3 SFT 闭环验证

```text
生成轨迹
  -> 导出 JSONL
  -> SFTDataset 加载
  -> chat template 序列化
  -> 训练一个短 run
  -> 模型重新在 HomeEnv 中执行
  -> 统计成功率和非法动作率
```

### 14.4 RL 闭环验证

先用三个 agent 验证奖励方向：

| Agent | 预期 |
|---|---|
| OracleAgent | 成功率 100%，高回报 |
| RandomValidAgent | 部分完成，回报居中 |
| InvalidAgent | 大量审计失败，低回报 |

若三者回报顺序不稳定，不能开始模型 RL。

## 15. 指标

环境级指标：

```text
strict_success_rate
goal_completion_rate
invalid_action_rate
side_effect_rate
premature_finish_rate
average_env_steps
average_dialogue_turns
query_to_control_ratio
truncation_rate
```

数据级指标：

```text
candidate_trajectory_count
verified_trajectory_count
generation_success_rate
trajectory_signature_count
average_trajectory_length
replay_success_rate
```

训练级指标：

```text
episode_return
progress_reward
success_reward
audit_penalty
group_reward_std
policy_kl
tool_call_format_rate
```

报告时同时给出成功率、条件完成率和非法动作率。单独报告 reward 没有可解释性。

## 16. 关键设计取舍

### 16.1 结构化动作优先于 `pyexec`

```text
第一版选择结构化动作：
  实现成本低
  安全边界清楚
  参数错误容易诊断
  reward 归因明确
  与 MiniMind tool call 已有能力兼容

后续增加 pyexec adapter：
  用于复现 HomeFlow 论文动作协议
  做结构化工具与代码动作的接口消融
```

### 16.2 一次模型输出对应一个 step

论文中的一次 `pyexec` 可以包含多个设备操作。面向 LLM 训练的简化版应采用“一次模型输出对应一个 step”：

```text
一个 assistant turn
  -> 一个策略 transition
  -> turn 内部包含一个或多个 tool_event
  -> 汇总一次 reward 和终止信号

底层原子动作
  -> 只负责单个工具的校验和状态转移
  -> 可以被 turn step 重复调用
  -> 不单独占用模型 turn 计数
```

这样才能保证模型 completion、token logprob、reward 和 RL transition 一一对应。V1 的动作级接口仍保留用于状态机测试和规则 Oracle；它不能直接作为在线 LLM RL 的最终数据接口。

### 16.3 固定场景优先于 HomeMaker

先用 100 条版本化场景验证训练闭环，再做环境生成器。

```text
固定场景阶段解决：
  环境是否正确
  奖励是否正确
  训练是否接通

HomeMaker 阶段解决：
  数据规模
  家庭多样性
  泛化和去重
```

两者同时开发会让失败来源无法定位。

### 16.4 episode-level RL 优先于逐步 RLVE

第一阶段把整局回报分配给整条 assistant token 序列，最大限度复用现有 `train_agent.py`。确认环境奖励能够提升任务成功率后，再实现 turn-level return-to-go。

```text
Phase 4 回答：
  环境奖励能否驱动学习？

Phase 5 回答：
  密集逐步信用分配是否优于终局回报？
```

## 17. 主要风险

### 17.1 奖励投机

风险：模型通过无关动作、重复查询或提前 finish 获得不合理回报。

控制：

```text
allowed_mutations
step cost
审计惩罚
当前状态重新求值
严格 success 条件
完整轨迹回放
```

### 17.2 环境信息泄漏

风险：observation 或 tool error 暴露目标谓词和完整状态。

控制：

```text
模型 observation 与 trainer info 分离
reward_components 只进 info
目标条件不进入 prompt
查询只返回请求范围内信息
```

### 17.3 多 generation 状态污染

风险：GRPO 同一任务的多个候选共享环境对象。

控制：每个 candidate 从同一不可变初始快照 fork 独立环境。

### 17.4 SFT 和 RL 口径分裂

风险：SFT 过滤器与 RL reward 使用不同谓词或状态路径。

控制：二者只调用同一个 `PredicateEvaluator` 和 `ActionAuditor`。

### 17.5 当前 MiniMind 训练上下文截断

当前 `train_agent.py` 会按 `max_total_len` 截断完整多轮序列。智能家居轨迹加入设备规格和状态后，工具 observation 很容易占满上下文。

控制：

```text
工具观察只返回必要字段
限制单次查询设备数
状态差异代替完整状态
轨迹构建时记录 token 数
截断前保证 assistant turn 边界完整
```

## 18. 最小成功标准

完成以下闭环即可称为“HomeFlow HomeEnv 机制级简化复现”：

```text
环境：
  7 类设备
  结构化查询与控制
  目标谓词
  状态 diff
  审计
  reset / step

SFT：
  至少 100 个可解场景
  至少 200 条环境验证成功轨迹
  MiniMind SFT 可加载并训练
  SFT 后工具格式与任务成功率高于 base

RL：
  同任务多候选独立 rollout
  环境 episode return 进入 GRPO/CISPO
  至少完成终局奖励与复合奖励消融
  训练后严格成功率提高或非法动作率下降

复现边界：
  明确未复现 pyexec、MCTS、HomeMaker 和论文规模
```

如果只完成环境回放和最终打分，尚未支持在线 RL；如果只把环境包成 Gym 类但 reward 仍来自文本 GT，也不能称为复现了 HomeFlow 的可验证训练机制。

## 19. 推荐实施顺序

```text
第 1 周
  冻结协议
  状态引擎
  设备规格
  谓词与审计

第 2 周
  HomeEpisodeEnv
  golden tests
  规则 oracle
  100 条场景

第 3 周
  SFT builder
  MiniMind SFT 冒烟
  base / SFT 环境评测

第 4 周
  HomeEnv rollout collector
  episode-level GRPO
  环境指标与奖励消融

后续
  turn-level RLVE
  Gymnasium adapter
  HomeMaker
  MCTS-Flow
  pyexec adapter
```

这里的周数是单人实现的排期估计，不是论文给出的数据。若优先完成机制验证，可以暂时只做灯、空调、风扇灯和传感器四类设备，把第一轮闭环压缩到两周左右。

## 20. 最终架构判断

```text
Gymnasium 包
  可选

Gym 风格语义
  必须

HomeEnv 核心
  框架无关、确定性、可复制、可验证

SFT 支持
  通过成功轨迹生成器消费 HomeEnv

RL 支持
  通过多轮 rollout collector 消费 HomeEnv

MiniMind 对接
  复用现有多轮工具调用与 token logprob 逻辑
  替换 MOCK_RESULTS 和文本 GT 奖励
```

本方案的核心不是先做一个完整模拟器，也不是先满足 Gymnasium 的形式检查。正确顺序是：

> 先建立唯一的状态真值、动作边界和条件验证，再用 `reset/step` 把它变成可训练 episode；SFT 从环境中抽取成功行为，RL 从同一个环境中获得逐步反馈。Gymnasium adapter 负责兼容，不负责定义系统。

## 21. 依据材料

[01_SMH-Bench 与 HomeFlow 实验架构复现分析](./01_SMH-Bench与HomeFlow实验架构复现分析.md)

[02_HomeEnv 核心谱系与两篇论文模拟器分析](./02_HomeEnv核心谱系与两篇论文模拟器分析.md)

[03_HomeFlow 中 HomeEnv 面向 SFT 与强化学习的调整分析](./03_HomeFlow中HomeEnv面向SFT与强化学习的调整分析.md)

[Gym 接口要求与 SimuHome 现状差异分析](../UbiComp三支柱讨论/5_Gym接口要求与SimuHome现状差异分析.md)

[统一语义接口架构与伪代码](../UbiComp三支柱讨论/8_统一语义接口架构与伪代码.md)

[MiniMind Agent RL](../minimind/trainer/train_agent.py)

[MiniMind Rollout Engine](../minimind/trainer/rollout_engine.py)

外部依据：Gymnasium 官方 `Env` API 与自定义环境教程，核对日期为 2026-09-20。官方接口将环境核心定义为 `reset`、`step`、动作/观察空间以及 `terminated`、`truncated` 分离的 episode 契约。
