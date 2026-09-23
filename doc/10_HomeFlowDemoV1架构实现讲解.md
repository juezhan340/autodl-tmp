# HomeFlow Demo V1.1 架构实现讲解

## 先看整体

V1.1 已经把 HomeFlow Demo 的环境闭环和模型决策步契约跑通：

```text
结构化场景
  -> schema 校验
  -> HomeEnv.reset()
  -> assistant turn
  -> 校验并执行一个或多个工具调用
  -> 记录 tool_events
  -> 汇总完成度、reward 和终止状态
  -> 保存一条 turn-level 可重放轨迹
```

当前还没有接入 DeepSeek、SFT 和 GRPO。V1.1 先固定“模型输出如何进入环境”和“环境如何判断动作与任务结果”。

当前代码中的 `Action` 仍是一个原子工具动作，但 `HomeEpisodeEnv.step()` 的主语义已经是“一个 assistant turn 一次 step”。一个 turn 内可以记录多个 `tool_event`，但只形成一条 RL transition。旧动作级 `actions/transitions` 字段保留用于兼容，新训练主字段是 `turns`。

## 1. 用一个任务贯穿系统

例子是 V1 中的双目标任务：

```text
用户请求：睡前请关闭卧室的灯，并把空调温度设置为26度。
```

设备初始状态：

```text
bedroom.light
  power = on

bedroom.air_conditioner
  temperature = 24
  mode        = cool
```

环境内部把目标保存为两个目标条件（代码中称为 predicate）：

```json
{
  "predicates": [
    {"device_id": "bedroom.light", "field": "power", "equals": "off"},
    {"device_id": "bedroom.air_conditioner", "field": "temperature", "equals": 26}
  ]
}
```

这两个目标条件就是环境的标准答案。模型看到的是用户请求、设备状态和工具，不直接看到目标条件。

这里的“谓词”只是程序设计中的术语，表示一个可以判断真假的条件。例如：

```text
bedroom.light.power == off
```

当前实现中，它完全可以理解为“目标状态条件”，并不是额外的一层复杂推理结构。

样例场景位于：

```text
homeflow_demo/data_processed/v1/scenarios_train.jsonl
scenario_id = v1_train_00001
```

## 2. 场景如何进入环境

[`schema.py`](/root/autodl-tmp/homeflow_demo/env/schema.py) 会检查：

```text
场景 ID 和用户请求是否存在
设备 ID 是否重复
设备类型和状态字段是否匹配
初始状态值是否在合法范围
目标条件是否引用真实设备和字段
max_turns 是否在 1～64 之间；旧 max_steps 仍可读取
max_tool_calls_per_turn 是否在 1～64 之间
```

例如空调温度允许范围是 16～30 度：

```text
场景格式错误      直接拒绝
目标温度为31度    保留为不可行任务
```

这样可以区分数据结构错误和任务本身不可完成。

调用 `reset` 后，[`home_env.py`](/root/autodl-tmp/homeflow_demo/env/home_env.py) 会复制设备初始状态、清空 episode 历史，并返回：

```json
{
  "user_request": "睡前请关闭卧室的灯，并把空调温度设置为26度。",
  "devices": [
    {"id": "bedroom.light", "state": {"power": "on"}},
    {"id": "bedroom.air_conditioner", "state": {"temperature": 24, "mode": "cool"}}
  ],
  "turn": 0,
  "max_turns": 4,
  "max_tool_calls_per_turn": 4,
  "tools": ["query_device", "control_device", "finish"]
}
```

目标条件不会放进 observation，避免训练时直接暴露答案。

## 3. 模型如何执行任务

模型通过工具动作改变状态，不直接修改设备对象。

关闭卧室灯：

```json
{
  "name": "control_device",
  "arguments": {
    "device_id": "bedroom.light",
    "command": "set_power",
    "value": "off"
  }
}
```

调节空调：

```json
{
  "name": "control_device",
  "arguments": {
    "device_id": "bedroom.air_conditioner",
    "command": "set_temperature",
    "value": 26
  }
}
```

任务完成后：

```json
{
  "name": "finish",
  "arguments": {"summary": "灯已关闭，空调已设置为26度。"}
}
```

当前工具只有三个：

```text
query_device    查询设备状态
control_device  修改一个设备字段
finish          声明任务结束
```

## 4. 一次 turn step 的内部流程

以下流程描述的是 V1.1 当前已经实现的模型决策步：

```text
assistant_turn 输入
  -> normalize_assistant_turn：兼容 Action、AssistantTurn、dict、JSON 字符串
  -> 检查 max_tool_calls_per_turn
  -> 对每个 tool_call 执行 _apply_action
       |
       +-- 非法：写入 tool_event，设备状态不变
       |
       +-- 合法：交给 StateEngine 执行
  -> 汇总本 turn 的完成度和 reward
  -> 检查 terminated/truncated
  -> 写入一条 turn trajectory
```

双目标任务可以由一次模型输出完成两个控制：

```json
{
  "tool_calls": [
    {"name": "control_device", "arguments": {"device_id": "bedroom.light", "command": "set_power", "value": "off"}},
    {"name": "control_device", "arguments": {"device_id": "bedroom.air_conditioner", "command": "set_temperature", "value": 26}}
  ],
  "text": ""
}
```

环境结果是：

```text
trajectory 条数：1
tool_events 数量：2
turn_index：1
completion：1.0
```

例如把空调调到 31 度：

```text
error_code = VALUE_OUT_OF_RANGE
设备状态   = 不变
reward     = 负值
```

[`state_engine.py`](/root/autodl-tmp/homeflow_demo/env/state_engine.py) 只负责合法状态转移。关闭灯后，它会返回：

```json
{
  "state_diff": {
    "power": {"from": "on", "to": "off"}
  }
}
```

状态引擎不判断任务是否成功，成功判断由 HomeEnv 根据目标条件完成。

## 5. 完成度、reward 和终止

这个任务有两个目标，完成度是满足目标条件的比例：

```text
初始：       0 / 2 = 0.0
关闭灯后：   1 / 2 = 0.5
调好空调后： 2 / 2 = 1.0
```

V1.1 reward 的主要组成：

```text
完成度提升：2.0 * 完成度增量
有效状态变化：+0.02
重复动作：-0.10
非法动作：-0.30
成功 finish：+1.00
失败 finish：-0.50
每个 turn 成本：-0.01
```

规则 Oracle 仍按单动作生成，但每个动作会包装成一个 synthetic assistant turn：

```text
turn 1：关闭灯，完成度 0.0 -> 0.5
turn 2：空调设为26度，完成度 0.5 -> 1.0
turn 3：finish，success=True
```

如果未完成就 `finish`：

```text
terminated = true
success = false
failure_reason = FINISH_BEFORE_GOAL
```

如果一直不结束直到达到最大步数：

```text
terminated = false
truncated = true
failure_reason = MAX_TURNS
```

## 6. Oracle 规划器和 V1 数据

[`planner.py`](/root/autodl-tmp/homeflow_demo/data/planner.py) 是规则规划器，不是语言模型。对于这个任务，它生成：

```text
1. control_device：卧室灯 -> off
2. control_device：卧室空调 -> 26
3. finish
```

规划器生成动作后，会真正调用 HomeEnv 执行，保存。当前记录同时保留兼容字段和 V1.1 主字段：

```text
actions       动作序列
transitions   每个原子动作的 observation、reward、info
turns         每个 assistant turn 及其 tool_events，RL 只读取这个字段
final_result  完成度、成功状态和最终设备状态
metadata      任务类型、seed、数据划分
```

[`build_v1_dataset.py`](/root/autodl-tmp/homeflow_demo/data/build_v1_dataset.py) 的流程是：

```text
生成场景
  -> schema 校验
  -> planner 生成动作
  -> HomeEnv 执行
  -> 保存场景和轨迹 JSONL
  -> 写入 manifest
```

当前数据规模：

```text
train：80 条场景
val：  20 条场景
eval： 40 条场景
总计：140 条场景
```

数据位于：

```text
homeflow_demo/data_processed/v1/
  scenarios_train.jsonl
  scenarios_val.jsonl
  scenarios_eval.jsonl
  oracle_trajectories_train.jsonl
  oracle_trajectories_val.jsonl
  oracle_trajectories_eval.jsonl
  manifest.json
```

## 7. Gym 接口和当前边界

核心环境是 `HomeEpisodeEnv`。`GymHomeEnvAdapter` 只是把它包装成标准的 reset/step 形式：

```python
observation, info = env.reset(options={"scenario": scenario})
observation, reward, terminated, truncated, info = env.step(assistant_turn)
```

其中 `assistant_turn` 是一次模型输出；如果它包含两个工具调用，环境内部执行两个工具事件，但仍只返回一条 turn-level transition。旧版 `env.step(Action(...))` 仍然可用。

职责边界：

```text
HomeEpisodeEnv       环境真值、状态和 reward
GymHomeEnvAdapter    外部接口兼容
模型或规划器         生成动作
数据脚本             批量生成和保存轨迹
```

V1.1 已完成：

```text
场景和动作校验
设备状态转移
完成度、reward、成功和失败判断
snapshot / restore / fork
Oracle 轨迹生成和重放验证
train / val / eval 数据集
turn-level AssistantTurn、ToolEvent、TurnResult
max_turns 和 max_tool_calls_per_turn
V1.1 Oracle turns 轨迹和全量重放验证
```

后续尚未完成：

```text
DeepSeek 候选轨迹生成
自然语言改写和 SFT 数据
Qwen2.5-1.5B 训练
在线 rollout
LoRA-GRPO
```

V1.1 的核心价值是固定模型输出、工具执行和环境 transition 的边界。下一步进入 V2：让 DeepSeek 生成候选 assistant turn，再由同一套 HomeEnv 验证和筛选。
