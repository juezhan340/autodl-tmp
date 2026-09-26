# HomeFlow V1.2 当前实现结果梳理

> 记录日期：2026-09-23
> 文档性质：当前实现结果说明，不是后续版本计划书
> 适用目录：`/root/autodl-tmp/homeflow_demo`

## 1. 先看结论

V1.2 已经完成一次可独立运行的 HomeFlow 最小实验闭环：

```text
A Oracle 决策者
        │ assistant turn
        v
C 回合与评测框架
        │ 规范化 ToolCall
        v
B HomeEnv
        │ tool result / state diff
        v
C 读取隐藏任务真值，判定成功、失败、错误类型和 reward
        │
        v
D 场景、Oracle 轨迹、重放与数据质量验证
```

当前版本已经能够验证以下问题：

```text
Home / Room / Device / Sensor / Action 的关系是否稳定
模型是否必须通过发现链获取设备信息
工具调用是否能被规范化、执行和记录
环境状态是否能正确变化并可重放
成功轨迹、策略错误和环境错误能否分开统计
高质量轨迹是否能通过质量门禁进入后续 SFT 数据
```

当前版本还没有进入模型训练闭环：DeepSeek 候选轨迹生成、SFT 训练、在线 rollout 和 LoRA-GRPO 属于后续版本。

## 2. 当前代码的模块关系

V1.2 落地的是 A、B、C、D 四个模块。E、F 只在架构设计中预留，代码尚未实现。

```text
┌─────────────────────────────────────────────────────────────────┐
│ C. 回合与评测框架                                               │
│                                                                 │
│  读取 Scenario 和隐藏 TaskSpec                                 │
│  管理多轮 turn、finish、错误、轨迹、reward 和最终评测结果        │
│                                                                 │
│   ┌──────────────────────┐       ┌──────────────────────────┐  │
│   │ A. 外部交互模块      │       │ B. HomeEnv 环境模块      │  │
│   │ OraclePolicy         │──────>│ Home / Room / Device     │  │
│   │ 产生 assistant turn  │       │ 工具校验、状态读取与执行  │  │
│   └──────────────────────┘       └──────────────────────────┘  │
│                                                                 │
│  C 负责管理回合和评测，不把隐藏目标交给 A，也不让 B 计算 reward  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────┐
│ D. 数据生成与质量验证                                           │
│ ScenarioGenerator + OraclePolicy + EpisodeRunner                 │
│ 生成场景、执行轨迹、确定性重放、质量筛选、写出 JSONL 和 manifest │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐   ┌──────────────────────────────┐
│ E. SFT                       │   │ F. RL                        │
│ V1.2 未实现                  │   │ V1.2 未实现                  │
│ 后续读取 accepted trajectory │   │ 后续读取环境 reward 做 rollout │
└──────────────────────────────┘   └──────────────────────────────┘
```

## 3. B：HomeEnv 当前实现了什么

### 3.1 家庭对象关系

V1.2 没有把房间名称写进设备路径，也没有假设固定户型。设备通过所在房间的关系被发现：

```text
Home
├── Room: bedroom
│   ├── Device: bedroom_env_sensor
│   │   ├── temperature
│   │   └── humidity
│   │   └── actions = []       # 只读传感器
│   ├── Device: bedroom_light
│   │   └── actions = [turn_on, turn_off]
│   └── Device: bedroom_climate
│       └── actions = [set_temperature]
├── Room: bathroom
│   ├── Device: bathroom_humidity_sensor
│   │   └── actions = []       # 只读传感器
│   └── Device: bathroom_fan
│       └── actions = [turn_on, turn_off]
├── Room: living
│   └── Device: living_light
│       └── actions = [turn_on, turn_off]
├── Room: kitchen
│   └── Device: kitchen_switch
│       └── actions = [turn_on, turn_off]
└── Room: study
    └── 无设备                  # 用于缺失设备任务
```

传感器仍然是 `Device`，只是设备的 `actions` 为空，并且通过统一设备读取接口返回温度、湿度等状态。这样可以避免额外设计一套传感器协议，同时保证传感器不会被 `execute_action` 写入。

### 3.2 当前可见工具和调用关系

当前可见工具只有四个，另有一个只供回合控制器使用的 `finish`：

```text
observe_home()
    -> 返回房间目录、环境摘要和设备数量，不返回 device_id

inspect_room(room_id)
    -> 返回指定房间内的设备列表和设备类型

inspect_device(device_id)
    -> 返回指定设备的状态和可执行 action

execute_action(device_id, action, parameters)
    -> 修改设备状态，返回 action 结果和 state diff

finish()
    -> 由 C 处理回合结束，不作为 HomeEnv 的设备控制动作
```

模型不能凭空使用未知设备 ID。正常调用顺序是：

```text
observe_home
    -> 从房间摘要中得到 room_id
inspect_room(room_id)
    -> 从房间设备列表中得到 device_id
inspect_device(device_id)
    -> 读取状态和 action schema
execute_action(device_id, action, parameters)
    -> 执行已经确认过的动作
finish
    -> 交给 C 判断任务是否完成
```

`HomeEnv` 维护发现状态，用于拒绝越级调用。例如模型直接猜测 `bedroom_light` 并执行动作，即使设备真实存在，也会因为没有经过可见的发现流程而被拒绝。这一约束使训练轨迹包含“先获取信息，再采取动作”的行为，而不是只记住设备 ID。

### 3.3 环境边界

```text
HomeEnv 负责：
  维护设备运行状态
  校验 room、device、action 和参数
  返回统一工具结果
  记录 state diff
  支持 snapshot / restore / fork

HomeEnv 不负责：
  不读取隐藏任务目标
  不判断 episode 是否成功
  不计算 reward
  不解析模型厂商消息格式
  不处理 finish
```

动作采用“先完整校验，后一次性提交”的方式。设备不存在、动作不支持、参数越界等错误不会留下部分状态变化。

## 4. C：回合与评测框架当前实现了什么

C 是当前实现的整体控制器。它连接 A 和 B，但不替代二者的职责。

```text
Scenario
  ├── public task：给 A 的用户任务
  ├── initial home：交给 B 的初始状态
  └── hidden TaskSpec：只给 C 的 conditions / keep / 评测配置

C 每一回合执行：
  1. 向 A 提供当前 observation 和工具 schema
  2. 解析 A 的 assistant turn
  3. 转换为统一 ToolCall
  4. 调用 B 执行或读取
  5. 保存 turn、tool event、state diff 和错误
  6. 判断是否 finish、超限或失败
  7. 回合结束后读取隐藏条件并计算 EpisodeEvaluation
```

A 返回的 OpenAI function call、统一结构或 JSON 文本，都由 C 解析成同一种内部对象：

```json
{
  "call_id": "call_001",
  "name": "inspect_device",
  "arguments": {
    "device_id": "bedroom_env_sensor"
  }
}
```

C 统一记录以下结果：

```text
success
reward
strategy_error_count
environment_failure_count
unresolved_error_count
tool_events
assistant_turns
accepted_for_sft
```

错误分为三类，便于强化学习时区分策略问题和执行环境问题：

```text
策略或协议错误：
  UNKNOWN_ROOM / UNKNOWN_DEVICE / UNSUPPORTED_ACTION / BAD_REQUEST
  -> 计入轨迹质量和策略错误，可按实验设置给负奖励

执行环境错误：
  DEVICE_UNAVAILABLE / BACKEND_UNREACHABLE / SERVICE_ERROR
  -> 标记 episode 或 system failure，不和策略失误混算

未决错误：
  无法归入上述类别的异常
  -> 保留原始信息，阻止轨迹直接进入高质量 SFT 数据
```

同一回合内，C 在回合开始时冻结可访问状态。模型不能在一个 assistant turn 中先调用 `inspect_room`，再依赖该结果调用 `inspect_device`；后一个调用会在下一轮得到新的 observation 后再执行。这保证轨迹中的信息依赖真实存在。

## 5. A：当前外部交互实现

V1.2 当前接入的是本地 `OraclePolicy`，用于验证环境和评测框架，不代表已经训练出模型。

```text
OraclePolicy 输入：
  当前 observation
  可见工具 schema
  当前任务请求

OraclePolicy 输出：
  每个 assistant turn 一个结构化工具调用
  或 finish
```

Oracle 的作用是提供可验证的参考行为：

```text
Oracle 轨迹成功
    -> 说明当前任务定义、工具协议和 HomeEnv 至少能够闭环

Oracle 轨迹失败
    -> 可以定位到任务定义、环境协议或规划逻辑

Oracle 轨迹不能直接证明小模型会成功
    -> 模型能力和训练效果要到后续 SFT / RL 版本验证
```

DeepSeek 配置文件已经预留为 `homeflow_demo/.env.deepseek`，但 V1.2 的正式数据构建不依赖 API，也没有把外部模型响应混入当前数据集。

## 6. D：当前数据和轨迹结果

### 6.1 当前任务覆盖

当前场景生成器维护固定的最小家庭拓扑，并生成八类任务：

```text
single_control       单设备控制
multi_control        多设备控制
query_then_control   查询后控制
temperature_threshold 温度阈值判断
humidity_threshold    湿度阈值判断
correct_no_op        正确不动作
sensor_readonly      尝试写入只读传感器
missing_device       目标设备不存在
```

温度和湿度任务均覆盖两条分支：

```text
条件满足 -> 执行动作
条件不满足 -> 正确保持不动作
```

因此当前版本不只是验证“设备能不能打开”，还验证了读取传感器、判断条件、选择动作或保持状态的基本链路。

### 6.2 正式数据目录

```text
homeflow_demo/data_processed/v1.2/
├── scenarios_train.jsonl             80 条
├── scenarios_val.jsonl               20 条
├── scenarios_eval.jsonl              40 条
├── oracle_trajectories_train.jsonl   80 条
├── oracle_trajectories_val.jsonl     20 条
├── oracle_trajectories_eval.jsonl    40 条
├── manifest.json
└── manifest.md
```

共 140 个场景，train、val、eval 的场景 ID 相互隔离。三个数据集都覆盖八类任务，eval 集不参与数据生成和后续训练。

当前 manifest 的关键记录如下：

```text
dataset_version：v1.2
format_version：v1.2-turn
seed：20260924
reward_version：v1.2-initial
dataset_fingerprint：
5ffd45205f1d7f42fff68be7d3b5ede099765b619de30b1ffed8bf64d9c02af9
```

可行任务中，Oracle 能完成控制和阈值分支；只读传感器写入被归为策略错误，缺失设备被归为任务定义错误。当前正式 Oracle 数据没有环境故障样本，这说明环境故障分类已经实现，但还没有专门的数据注入实验。

## 7. 用一个阈值任务看完整结果

例如任务是：

```text
“如果卧室湿度高于 60%，打开浴室风扇；否则保持当前状态。”
```

当前链路会这样运行：

```text
用户任务
    │
    v
C 创建回合，向 A 提供 observe_home 和其他可见工具
    │
    v
A 调用 observe_home
    │
    v
B 返回房间摘要，A 发现 bedroom
    │
    v
A 调用 inspect_room("bedroom")
    │
    v
B 返回 bedroom_env_sensor 等设备
    │
    v
A 调用 inspect_device("bedroom_env_sensor")
    │
    v
B 返回 humidity = 65
    │
    v
A 根据任务条件选择：
    humidity > 60 -> inspect bathroom_fan -> execute_action(turn_on)
    humidity <= 60 -> 不执行写操作，直接 finish
    │
    v
C 读取隐藏 conditions / keep
    │
    v
EpisodeEvaluation：success、reward、错误归因、轨迹质量
```

这个例子体现了当前设计中的三层分工：

```text
A 决定下一步想做什么
B 只负责把合法工具调用映射为环境读取或状态变化
C 决定这次回合是否完成任务，以及轨迹是否可用于训练
```

## 8. 已验证结果

以下结果来自当前工作区的实际验证，而不是设计预期：

```text
Python compileall                         通过
V1.2 单元测试                             18 / 18 通过
V1.2 场景 schema 校验                     140 / 140 通过
V1.2 轨迹确定性重放                       140 / 140 通过
V1.2 重复构建结果一致                     140 / 140 通过
V1 历史数据只读检查                       140 / 140 ID 对齐
git diff --check                          通过
Python 模块中文注释静态检查               通过
Python 文件与同名中文说明文档检查         通过
```

对应验证命令：

```bash
cd /root/autodl-tmp

PYTHONPATH=/root/autodl-tmp \
python -m unittest discover -v

PYTHONPATH=/root/autodl-tmp \
python -m homeflow_demo.data.build_v1_2_dataset \
  --output-dir /root/autodl-tmp/homeflow_demo/data_processed/v1.2

PYTHONPATH=/root/autodl-tmp \
python -m homeflow_demo.data.validate_v1_2_dataset \
  --root /root/autodl-tmp/homeflow_demo/data_processed/v1.2
```

验证器当前会检查：

```text
JSONL 是否符合 V1.2 schema
train / val / eval 的 ID 是否隔离
轨迹是否能重新驱动 HomeEnv
重新生成的轨迹指纹是否一致
accepted_for_sft 是否符合成功、无错误、可重放条件
```

## 9. 当前实现边界

### 已经落地

```text
Home / Room / Device / ActionSchema / Scenario 数据模型
只读传感器和温湿度状态
observe_home -> inspect_room -> inspect_device -> execute_action 发现链
统一 ToolCall 和 {ok, data, error, meta} 结果封装
HomeEnv 状态执行、state diff、snapshot / restore / fork
EpisodeRunner、EpisodeEvaluator、TrajectoryQuality
Oracle 轨迹生成、失败分类、确定性重放
V1.2 train / val / eval 正式数据和 manifest
```

### 明确尚未落地

```text
DeepSeek API 候选轨迹生成与审查流水线
SFT 数据转换脚本和 LoRA-SFT 训练
真实模型 client、tokenizer、logprob 记录
在线 rollout 和 LoRA-GRPO
Qwen2.5-1.5B Base / SFT / RL 的效果对比
真实 Home Assistant / MCP 接入
连续物理仿真、复杂户型和长期记忆
```

Gymnasium 适配器也已经提供，但它只是中性接口适配层，当前核心 HomeEnv 不依赖 Gymnasium，也不在环境内部放入 reward 和 termination 逻辑。这保留了以后接 SFT、RL 框架的可能性，同时没有把实验评测职责塞回环境。

## 10. 对当前结果的判断

### 已验证的事实

```text
V1.2 的环境、回合、评测、轨迹格式和本地数据生成链路可以独立运行。
统一语义接口已经从设备对象贯通到 ToolCall、tool result 和轨迹记录。
训练数据的入口条件已经明确：成功、结构完整、无策略错误污染、可确定性重放。
```

### 当前只能作出的判断

```text
V1.2 已经具备作为 SFT / RL 实验底座的必要结构。
Oracle 数据能够证明环境协议可用，但不能证明 1.5B 模型已经具备对应能力。
错误分类能够支持后续 reward 设计，但不同 reward 权重仍需在 RL 实验中校准。
```

### 仍待后续验证的风险

```text
DeepSeek 生成的自然语言轨迹通过率和重复率
accepted SFT 数据量是否足以训练 1.5B 模型
模型是否能学会发现链，而不是记忆固定 device_id
LoRA-GRPO 是否比 LoRA-SFT 进一步提升成功率和泛化能力
在未见房间、设备组合和任务组合上的迁移效果
```

## 11. 当前文件入口

```text
环境：
  homeflow_demo/env/models.py
  homeflow_demo/env/schema.py
  homeflow_demo/env/tool_schema.py
  homeflow_demo/env/state_engine.py
  homeflow_demo/env/home_env.py

回合与评测：
  homeflow_demo/eval/episode_runner.py
  homeflow_demo/eval/episode_evaluator.py
  homeflow_demo/eval/trajectory_quality.py
  homeflow_demo/eval/metrics.py

外部交互：
  homeflow_demo/agents/oracle_policy.py

数据生成与验证：
  homeflow_demo/data/scenario_generator.py
  homeflow_demo/data/planner.py
  homeflow_demo/data/build_v1_2_dataset.py
  homeflow_demo/data/validate_v1_2_dataset.py

正式数据：
  homeflow_demo/data_processed/v1.2/

交付报告：
  homeflow_demo/reports/V1.2_report.md
```
