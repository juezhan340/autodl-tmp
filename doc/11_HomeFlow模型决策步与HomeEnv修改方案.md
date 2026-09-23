# HomeFlow 模型决策步与 HomeEnv 修改方案

> 文档日期：2026-09-22  
> 适用范围：`homeflow_demo` V1 之后的环境接口、数据格式和在线 RL rollout

## 先看结论

```text
当前 V1：
  HomeEpisodeEnv.step(Action) = 执行一个原子工具动作
  适合测试状态转移、参数校验、规则 Oracle 和环境裁判
  还不适合作为 LLM 在线 RL 的最终决策步接口

修改后：
  HomeEpisodeEnv.step(AssistantTurn) = 消费一次模型 assistant 输出
  一个 turn 内可以包含一个或多个工具调用
  工具调用在 turn 内部执行并审计，但不拆成多个策略 transition
  每个模型输出只对应一条 observation/action/reward/next_observation 记录
```

```text
observation_t
      |
      v
模型生成一个 assistant turn
      |
      +--> turn 内部解析若干 tool call
      +--> HomeEnv 顺序或事务式执行
      +--> 汇总 tool result、状态变化和完成度
      v
observation_(t+1), reward_t, terminated, truncated
```

需要分开的两个概念：

```text
工具动作 action：环境内部可执行的原子操作，例如 set_power(off)
模型决策 turn：一次 assistant 输出，是 RL 需要计算 logprob 和更新参数的单位
```

当前 V1 的 `step(Action)` 可以保留为内部执行原语或兼容接口，但从 V1.1 开始，模型 rollout、SFT 轨迹和 Gym 对外接口应使用 turn-level 语义。

## 1. 为什么当前接口必须调整

当前 V1 的 Oracle 轨迹是：

```text
planner 产生 action_1
  -> env.step(action_1)
planner 产生 action_2
  -> env.step(action_2)
planner 产生 finish
  -> env.step(finish)
```

这对规则规划器没有问题，因为规划器本来就逐个产生动作。问题出现在 LLM rollout：如果一次模型输出已经包含三条控制操作，却把三条操作分别送入三个 `env.step()`，就会得到：

```text
模型只生成了一次 completion C_t
  -> action_1 被记录成 transition_t
  -> action_2 被记录成 transition_(t+1)
  -> action_3 被记录成 transition_(t+2)
```

后两个 transition 没有新的模型 completion，也没有对应的 assistant token、logprob 和策略采样概率。结果是：

```text
信用分配错误：第二、第三个动作没有独立策略输出，却被当成独立决策训练
logprob 对齐错误：一个 completion 的 token 不能自然映射到后续虚构出来的动作步
episode 长度失真：max_steps 统计内部工具调用数，不是模型实际决策次数
```

所以“单个模型输出对应一个环境 step”是 LLM RL 训练数据结构的必要条件，不是接口风格偏好。

## 2. HomeFlow 原文中的 step 应如何理解

本地 HomeFlow 论文文本把在线轨迹写成：

```text
τ = (u_1, a_1, r_1, ..., u_T, a_T, r_T)
```

其中 `a_t` 是智能体在一次交互回合中的动作，动作触发 HomeEnv 更新；原文没有把 `a_t` 定义成某一个设备 setter 的单独调用。

论文附录的 Gym 示例也很关键：

```text
env.step({"name": "pyexec", "code": "..."})
```

一次 `pyexec` 可以在代码中执行多个设备操作，但环境仍然只返回一次 `step` 结果。由此可见，论文中的环境 step 更接近一次 agent interaction turn；底层设备方法是该回合内部的执行内容。

论文还提供了单回合消融：`HomeFlow-RL (ST)` 删除中间工具使用和设备控制回合，只保留最终的单回合交互。这进一步说明原文对比的是多回合与单回合策略交互，而不是把每个底层设备方法强制视作独立策略步。

论文没有公开完整 HomeEnv 源码，因此不能断言其内部一定采用某一种事务实现。但从轨迹定义、Gym 示例和逐步 RLVE 描述可以确定：

```text
HomeFlow 的策略步应理解为一次模型交互回合。
pyexec 或结构化 tool call 是该回合内部的动作表达。
```

## 3. 一个例子：正确和错误的轨迹

任务：

```text
请关闭卧室的灯，并把空调设置为 26 度。
```

### 3.1 当前动作级写法

```text
obs_0
  -> control(light, off)
  -> env.step()
  -> obs_1, reward_1

obs_1
  -> control(ac, 26)
  -> env.step()
  -> obs_2, reward_2

obs_2
  -> finish
  -> env.step()
  -> obs_3, reward_3
```

如果这些动作来自规则规划器，这条轨迹是合法的。若它们都来自一次模型 completion，则第二次和第三次模型决策并不存在。

### 3.2 目标 turn 级写法

模型第一次输出：

```json
{
  "tool_calls": [
    {
      "name": "control_device",
      "arguments": {
        "device_id": "bedroom.light",
        "command": "set_power",
        "value": "off"
      }
    },
    {
      "name": "control_device",
      "arguments": {
        "device_id": "bedroom.air_conditioner",
        "command": "set_temperature",
        "value": 26
      }
    }
  ]
}
```

环境内部执行两条工具调用，记录两个 `tool_event`，但只产生一个策略转移：

```text
obs_0
  -> assistant_turn_0
       tool_event_0: light -> off
       tool_event_1: air_conditioner -> 26
  -> env.step(turn_0)
  -> obs_1, reward_0
```

模型下一次输出：

```json
{
  "tool_calls": [],
  "text": "已完成。"
}
```

环境再产生第二个策略转移并结束：

```text
obs_1
  -> assistant_turn_1
       finish
  -> env.step(turn_1)
  -> obs_2, reward_1, terminated=True
```

最终 RL 轨迹是：

```text
(obs_0, completion_0, reward_0, obs_1)
(obs_1, completion_1, reward_1, obs_2, terminated=True)
```

而不是三条被伪造的 action transition。

## 4. 简化 Demo 的最终接口

### 4.1 模型输出结构

定义一个模型回合对象 `AssistantTurn`：

```json
{
  "tool_calls": [
    {
      "name": "query_device",
      "arguments": {
        "device_id": "bedroom.air_conditioner",
        "fields": ["temperature"]
      }
    }
  ],
  "text": ""
}
```

最终回复也使用同一个结构：

```json
{
  "tool_calls": [],
  "text": "已完成。"
}
```

Demo 第一阶段可以把 `max_tool_calls_per_turn` 配为 `1`，实现保持简单；接口仍然使用 `tool_calls` 数组，为后续支持 HomeFlow 式多操作回合保留扩展位。

### 4.2 环境公开接口

```python
class HomeEpisodeEnv:
    def reset(self, scenario, seed=None): ...
    def step(self, assistant_turn): ...
    def snapshot(self): ...
    def restore(self, snapshot): ...
    def fork(self): ...
    def trajectory(self): ...
    def final_result(self): ...
```

`step(assistant_turn)` 的内部顺序：

```text
读取当前 observation
  -> 解析 assistant turn
  -> 校验所有 tool call
  -> 执行工具调用并记录 tool_events
  -> 汇总 after_state 与 state_diff
  -> 重新计算完成度
  -> 计算一个 turn reward
  -> 检查 terminated / truncated
  -> 写入一条 turn transition
```

环境内部增加一个不直接暴露给模型训练器的原语：

```python
_apply_action(action) -> ToolEvent
```

它负责单个工具调用的校验、状态转移和工具结果。`step(assistant_turn)` 负责把一次模型输出中的多个 `_apply_action` 结果聚合成一个 RL transition。

### 4.3 奖励口径

一个 turn 只计算一次环境奖励：

```text
m_before = 本 turn 开始前的完成度
m_after  = 本 turn 所有工具调用执行后的完成度

r_turn = λ_progress * (m_after - m_before)
         + λ_valid * valid_turn
         - λ_invalid * invalid_call_count
         - λ_repeat * repeat_call_count
         + λ_finish * successful_finish
         - λ_fail * failed_finish
         - λ_turn
```

内部仍保存每个 `tool_event` 的局部信息：

```text
tool_events[i].action
tool_events[i].result
tool_events[i].valid
tool_events[i].state_diff
tool_events[i].error_code
```

这些字段用于审计、数据过滤和错误分析，不作为额外模型决策步。若后续想做更细的信用分配，可以把 turn reward 分配给本 turn 的全部 assistant completion token，仍然不能凭空生成不存在的模型输出。

## 5. `max_steps` 应改成 `max_turns`

当前 V1 的 `max_steps` 统计 `env.step(Action)` 次数。在目标接口中，它应表示模型最多生成多少次 assistant turn：

```text
max_turns = 允许模型产生的 assistant 输出次数
```

例如：

```text
max_turns = 4

turn 1：查询空调
turn 2：根据查询结果控制空调
turn 3：关闭灯
turn 4：结束回复
```

一个 turn 中有两个工具调用时，仍只消耗 1 个 turn 配额。工具调用数量另设：

```text
max_tool_calls_per_turn = 单次 assistant 输出最多包含多少个工具调用
max_turns                = 一个 episode 最多允许多少次 assistant 输出
```

兼容过渡期可以保留 JSON 字段 `max_steps`，但 V1.1 以后应在解析时转换为 `max_turns`，内部统一按 turn 计数。

## 6. 对 SFT、GRPO 和 Oracle 的影响

### 6.1 SFT

SFT 样本按 assistant turn 保存：

```text
user
  -> assistant turn 0
  -> tool result(s)
  -> assistant turn 1
  -> tool result(s)
  -> assistant final text
```

成功轨迹中，每个 assistant turn 都必须有真实模型文本或明确的教师输出。不能把一条教师回复拆成多个没有文本来源的伪 assistant turn。

### 6.2 LoRA-GRPO

Rollout 循环应为：

```text
obs_t
  -> 模型生成 completion_t
  -> 解析 AssistantTurn_t
  -> env.step(AssistantTurn_t)
  -> reward_t, obs_(t+1)
  -> 继续生成下一次 completion
```

GRPO 的 token 对齐关系为：

```text
completion_t 的全部有效 token
  -> 使用 turn_t 的 reward / return-to-go / advantage
```

如果一次 completion 包含多个工具调用，这些调用共享同一个 turn-level credit。这是可解释且可实现的粗粒度方案。未来需要工具级 credit 时，应让模型在多个回合分别输出，而不是事后把一个 completion 切成多个策略步。

### 6.3 Oracle 规划器

Oracle 仍然可以逐个生成原子动作，但保存轨迹时必须明确来源：

```text
规则 Oracle：每个规划动作包装为一个 synthetic assistant turn
模型教师轨迹：保留原始 assistant turn，不重新拆分
```

这样可以让规则 Oracle 作为逐回合教师使用，同时不误称它复现了模型自然生成的一次多工具输出。

## 7. 具体修改方案

```text
阶段 A：先改契约，不改训练算法
  增加 AssistantTurn、ToolEvent、TurnResult 数据结构
  将 max_steps 规范化为 max_turns
  HomeEnv 增加 step(turn) 聚合逻辑
  保留 _apply_action 处理单个工具调用

阶段 B：改数据和 Oracle
  trajectory 从 action 列表改为 turn 列表
  每个 turn 保存 assistant_output、tool_events、reward 和 final flags
  Oracle 每个原子规划动作包装成 synthetic turn
  更新回放和数据校验脚本

阶段 C：改 DeepSeek 与 SFT 格式
  DeepSeek 输出按 assistant_turn 保存
  一个 turn 内允许 1 个工具调用，接口预留多个
  HomeEnv 验证后才进入 SFT

阶段 D：改在线 rollout
  每生成一次 completion 才调用一次 env.step
  tool result 作为下一轮上下文
  completion token、old logprob 和 turn reward 一一对应

阶段 E：再接 GRPO
  先使用 turn-level episode return
  再实现 turn-level return-to-go
  暂不做 token 内部的工具动作拆分
```

## 8. 文件级修改清单

```text
homeflow_demo/env/models.py
  新增 AssistantTurn、ToolEvent、TurnResult
  保留 Action 作为单个工具调用的数据结构

homeflow_demo/env/home_env.py
  step 的模型输入改为 AssistantTurn
  抽取 _apply_action
  trajectory 改为 turn transition + tool_events
  _step_count 改为 _turn_count，兼容读取旧字段

homeflow_demo/env/gym_adapter.py
  Gym step 接收一个 AssistantTurn
  五元组中的 reward 对应整个 assistant turn

homeflow_demo/data/planner.py
  规则动作包装为 synthetic assistant turn
  保留原始 plan actions 供审计，但不把它们混同为模型 completion

homeflow_demo/data/trajectory_format.py
  增加 turn、tool_events、assistant_output 和 token_alignment 字段
  旧 V1 JSONL 只读兼容，不直接混入新训练集

homeflow_demo/train/home_rollout.py
  模型每生成一次 completion 才调用一次 env.step
  禁止在一个 completion 内循环产生多个策略 transition

tests/
  增加“一个 completion 含两个 tool call 只产生一条 transition”测试
  增加“max_turns 按模型输出次数计数”测试
  增加“tool_events 数量可以大于 turn 数量”测试
  增加“每条 transition 都有对应 assistant output”测试
```

## 9. 版本安排

当前 V1 不需要推翻。它的定位调整为：

```text
V1 = 原子动作环境内核、规则 Oracle 和可复现状态裁判
```

在调用 DeepSeek 或训练 1.5B 之前插入 `V1.1`：

```text
V1.1：turn-level HomeEnv 契约修订
  AssistantTurn / ToolEvent / TurnResult
  max_turns
  turn trajectory
  turn-level Gym adapter
  Oracle synthetic turn
  完整回归测试
```

后续版本调整为：

```text
V2：DeepSeek 教师数据，按 assistant turn 保存
V3：turn-level SFT 数据集
V4：LoRA-SFT 和 turn-level 评测
V5：turn-level HomeEnv online rollout
V6：turn-level LoRA-GRPO
V7：消融、资源和泛化实验
```

## 10. 最终判断

```text
一个模型输出 = 一个策略决策步
一个策略决策步内部可以包含多个工具调用
多个工具调用可以形成多个 tool_event
多个 tool_event 不能自动变成多个 RL transition
```

当前 V1 的动作级 `step` 作为底层状态机测试是合理的；把它直接当成 LLM 的训练 step 才是需要修正的地方。修改的核心不是简单重命名 `max_steps`，而是把“模型输出、工具执行、环境反馈、token credit”重新对齐。

依据材料：

```text
论文/方法相关的论文/19_2026_arXiv_HomeFlow-Data-Flywheel-Smart-Home_数据飞轮智能家居训练_中.txt
doc/04_HomeFlow中HomeEnv简化复现方案.md
doc/08_HomeFlow简练Demo完整实施方案.md
homeflow_demo/env/home_env.py
homeflow_demo/data/planner.py
```
