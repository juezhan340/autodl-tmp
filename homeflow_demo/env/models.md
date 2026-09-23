# `homeflow_demo/env/models.py` 说明

## 职责

集中定义 HomeEnv 的场景、原子工具调用、模型决策 turn、工具事件和环境返回值，避免环境、数据生成器和训练器各自维护一套字典格式。

## 主要数据结构

```text
GoalPredicate：设备字段目标，例如 bedroom.light.power == off
Scenario：     episode 的静态场景、设备、目标条件和 max_turns
metadata：     任务类型、条件和数据划分等非环境核心元数据
Action：       一个原子工具调用
AssistantTurn：一次 assistant 输出，可包含多个 Action
ToolEvent：    一个 Action 的校验、执行和状态变化审计
TurnResult：   一个 AssistantTurn 聚合后的环境反馈
StepResult：   reset/step 后的 observation、reward、终止状态和 info
FinalResult：  episode 的成功状态、完成度、turn 数和最终设备状态
PredicateResult：目标条件满足情况
```

## 输入输出

```text
输入：Python 字典、JSON 场景对象、Action、AssistantTurn 或 JSON 字符串
输出：类型明确的 dataclass，可转换为字典或 JSON
```

## 兼容字段

```text
旧场景 max_steps：可以读取，内部按模型 turn 数解释
新场景 max_turns：统一写入新 JSON
FinalResult.steps：保留旧访问方式，FinalResult.turns 是新名称
```

## 不负责

```text
不负责设备状态转移
不负责工具参数校验
不负责 reward 计算
不负责模型生成
```
