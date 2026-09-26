# SimuHome时间机制简化与强化学习方案

> 本文基于 `simuprocject/Simuhome_experiment/` 源码、现有 SimuHome 时间机制分析，以及当前 HomeFlow V1.1 的环境设计讨论。目标是判断：在不真实推进时间的情况下，能否保留时间任务的核心语义，并把它做成适合 SFT 与强化学习训练的 Demo。

## 0. 结论先行

可以。

建议把 SimuHome 的完整时间模拟，简化成：

```text
自然语言任务
    ↓
时间语义结构化
    ↓
确定性规则校验
    ↓
立即返回奖励
    ↓
本轮结束，不推进真实时间
```

这个方案训练的是：

```text
时间表达理解
相对时间与绝对时间换算
时间触发器选择
事件依赖表达
时间条件与设备动作绑定
预约动作的结构化输出
```

它暂时不训练：

```text
真实虚拟时钟的连续推进
设备随时间的物理变化
预约任务到点后的真实执行
多个工作流之间的竞态
温度、湿度、空气质量等持续环境动力学
```

因此，文档中建议把这个版本称为：

```text
时间语义强化学习环境
Temporal Semantic RL Environment
```

不要把它直接称为“完整的时间模拟器”。它适合 HomeFlow 的简练 Demo、SFT 数据构造和 GRPO 奖励验证，也适合研究模型能否正确理解并输出智能家居中的时间意图；如果论文要研究真实延迟、连续环境变化或复杂调度执行，仍然需要回到 SimuHome 一类的虚拟时间内核。

---

## 1. SimuHome 当前时间机制是什么

### 1.1 时间不是一个字段，而是一条运行链路

SimuHome 在 `src/simulator/domain/home.py` 中维护 `current_tick` 和 `tick_interval`，虚拟时间大致按下面的方式计算：

```text
虚拟时间
    = base_time
    + virtual_offset_seconds
    + current_tick × tick_interval
```

默认 `tick_interval=0.1`，意味着一个 tick 对应 0.1 秒虚拟时间。

但时间不会因为模型调用 `get_current_time` 自动产生。真正推进时间的是后台模拟线程：

```text
后台线程
    ↓
处理时间敏感设备
    ↓
处理环境聚合器
    ↓
处理到期调度任务
    ↓
处理 API 队列
    ↓
根据真实耗时 sleep
    ↓
current_tick += 1
```

在非 `fast_forward` 模式下，主循环会根据本轮真实执行耗时决定还要不要 sleep。于是模型推理耗时、HTTP 请求耗时、机器负载都会间接影响虚拟时间推进速度。

### 1.2 预约只是登记，执行发生在未来

`schedule_workflow` 主要做以下几件事：

```text
检查步骤格式
    ↓
解析绝对时间
    ↓
把绝对时间换算成 due_tick
    ↓
写入 workflows_by_id
    ↓
写入 PriorityQueue
    ↓
返回 workflow_id
```

模型得到的成功响应只表示“预约已经登记”，不表示未来的设备动作已经执行成功。

时间真正到达 `due_tick` 后，调度队列才会把工作流启动。工作流中的多个步骤由 `__execute_workflow_step` 递归执行，因此同一个工作流内的步骤通常会在同一个触发点连续完成，并没有模拟步骤之间的时间间隔。

### 1.3 快进解决了评测等待，但没有解决训练契约

SimuHome 有 `_fast_forward_to`：它可以把时间跳到目标 tick。无事件且聚合器支持批量推进时，系统会整段跳过；存在不可批量推进的设备或调度事件时，再逐 tick 处理。

整体关系可以画成：

```text
模型
  └── 预约未来动作、读取状态、查询工作流

后台模拟线程
  └── 按真实执行节奏持续推进 tick

评测脚本
  └── 事后 fast_forward 到检查点，再判断动作是否按时发生
```

这适合基准测试，却不适合直接放入强化学习内循环。强化学习需要在每次动作后快速得到状态和奖励，而 SimuHome 的时间任务往往要等到后续检查点才能判定。

---

## 2. 为什么完整时间机制不适合直接做 RL 内循环

### 2.1 奖励不是动作之后立即可见

以“13 分钟后把客厅灯调到 30%”为例，SimuHome 的完整流程是：

```text
模型读取当前时间
    ↓
模型计算未来绝对时间
    ↓
模型调用 schedule_workflow
    ↓
系统返回 workflow_id
    ↓
时间继续推进
    ↓
到达 due_tick
    ↓
工作流执行
    ↓
评测脚本读取状态并判断是否命中时间容差
```

模型调用预约工具之后，立即得到的只是“注册成功”。如果在这一时刻给正奖励，奖励的是 API 格式正确，不是时间任务真正完成；如果等到动作执行后再给奖励，训练内循环就必须引入时间推进和延迟回报。

### 2.2 后台线程把真实时间带进了环境

当前 ReAct 和 HI Agent 对工作流状态查询设置了轮询预算，并且轮询之间会进行真实 `sleep` 退避。源码中默认最多轮询 8 次，退避时间从 1 秒逐步增加，最大 8 秒。

这在评测真实智能家居服务时有意义，但对于 GRPO 训练有三个直接问题：

```text
一次 rollout 的耗时不再主要由模型推理决定
多条候选轨迹会争抢后台模拟器和 API 队列
相同动作序列可能因为机器负载不同而得到不同的时间跨度
```

### 2.3 SimuHome 的推进权不在 Gym step 中

当前时间机制的推进权分散在后台线程和评测脚本中：

```text
Gym 风格训练期望：
    action → env.step → next_observation, reward, done

SimuHome 当前实际情况：
    action → API 入队
    后台线程择机处理
    评测脚本之后再 fast_forward
    评测脚本最后判断结果
```

这样可以支持复杂模拟，但不适合要求大量并行轨迹的 GRPO。特别是对 1.5B 端侧模型，训练资源本来就有限，环境再引入后台线程、HTTP、sleep 和延迟评测，会明显降低有效样本吞吐。

### 2.4 时间模拟的复杂度超过了当前 Demo 的研究问题

如果当前研究问题只是：

```text
模型能否理解“十分钟后”
模型能否区分“现在执行”和“预约执行”
模型能否把事件依赖转换成结构化动作
模型能否按照时间条件生成正确设备操作
```

那么设备的温度变化、聚合器的逐 tick 更新、后台 API 队列和快进分支都不是必要条件。它们属于“执行真实性”，不是“时间语义正确性”。

---

## 3. “只做语义校验”到底应该怎么理解

这里必须区分两种完全不同的方案。

### 3.1 不推荐：让另一个大模型自由判断“说得像不像正确答案”

```text
模型输出自然语言
    ↓
调用 DeepSeek 或其他 LLM 评价
    ↓
返回“看起来合理”的分数
```

这种方式有延迟、成本和随机性，奖励边界不稳定。相同输出可能因为评审模型采样差异得到不同分数，也容易出现“语言很流畅但时间关系错了”的情况。

### 3.2 推荐：语义归一化后用规则校验

推荐把“语义校验”定义成一个确定性流程：

```text
自然语言任务
    ↓
模型输出结构化 TemporalIntent
    ↓
JSON Schema 校验
    ↓
时间表达归一化
    ↓
设备、动作、事件能力校验
    ↓
与目标语义结构比较
    ↓
立即计算奖励
```

比如：

```text
用户：十分钟后关卧室灯。

目标语义：
    trigger.kind = relative_time
    trigger.offset_seconds = 600
    actions[0].device_id = bedroom.light
    actions[0].command = turn_off
```

模型输出“现在关卧室灯”，设备动作虽然正确，但时间触发器错误，应该得到部分分或负分，而不能被自由文本评审判为完全正确。

因此，关键不在于有没有自然语言，而在于是否存在稳定的中间表示。

---

## 4. 简化版时间环境的核心设计

### 4.1 环境职责

```text
模块：TemporalSemanticEnv

职责：
    提供带时间关系的智能家居任务
    接收模型生成的时间动作
    将动作解析为统一语义结构
    校验时间、设备、动作和条件
    立即返回奖励与终止状态

输入：
    任务文本
    固定的当前时间
    当前设备目录与能力表
    目标 TemporalIntent

输出：
    observation
    reward
    terminated
    truncated
    info

读取：
    任务配置、设备能力、时间语义规则

写入：
    本轮已接受的预约语义
    轨迹记录与评分明细

不负责：
    推进真实时间
    启动后台线程
    执行未来设备动作
    模拟传感器和环境动力学
```

### 4.2 最小状态结构

环境不需要维护 `current_tick`。建议维护下面的静态场景状态：

```json
{
  "episode_id": "time_001",
  "current_time": "2026-09-22 09:00:00",
  "user_request": "十分钟后关卧室灯。",
  "devices": {
    "bedroom.light": {
      "capabilities": ["turn_on", "turn_off", "set_brightness"]
    }
  },
  "target_intent": {
    "trigger": {
      "kind": "relative_time",
      "offset_seconds": 600
    },
    "actions": [
      {
        "device_id": "bedroom.light",
        "command": "turn_off",
        "arguments": {}
      }
    ]
  }
}
```

这里的 `current_time` 只用于解析“今天 18:00”“半小时后”等表达，不会随着模型推理时间变化。

### 4.3 模型动作结构

建议模型在训练时输出统一 JSON。自然语言可以作为输入，但动作最好落到结构化协议：

```json
{
  "action": "schedule",
  "trigger": {
    "kind": "relative_time",
    "offset_seconds": 600
  },
  "conditions": [],
  "actions": [
    {
      "device_id": "bedroom.light",
      "command": "turn_off",
      "arguments": {}
    }
  ]
}
```

动作类型可以先限制为三种：

```text
execute_now       立即执行设备动作
schedule          按时间或事件预约设备动作
clarify           信息不足时请求澄清
```

V1 Demo 只需要 `execute_now` 和 `schedule`。`clarify` 可以留到多轮环境再加入。

### 4.4 时间触发器类型

第一阶段不需要支持所有自然语言时间，只需要覆盖具有代表性的几类：

```json
{
  "kind": "relative_time",
  "offset_seconds": 600
}
```

```json
{
  "kind": "absolute_time",
  "datetime": "2026-09-22 18:30:00"
}
```

```json
{
  "kind": "event_after",
  "event": {
    "device_id": "dishwasher",
    "name": "completed"
  }
}
```

```json
{
  "kind": "periodic",
  "frequency": "daily",
  "at": "18:30"
}
```

其中 `event_after` 只表达事件依赖，不真的运行洗碗机；`periodic` 只校验周期语义，不真的每天触发。

### 4.5 时间加状态条件

时间语义可以和设备状态条件组合，但条件只做静态校验：

```json
{
  "trigger": {
    "kind": "absolute_time",
    "datetime": "2026-09-22 14:00:00"
  },
  "conditions": [
    {
      "device_id": "kitchen.temperature",
      "attribute": "value",
      "operator": ">",
      "value": 35
    }
  ],
  "actions": [
    {
      "device_id": "kitchen.fan",
      "command": "turn_on",
      "arguments": {}
    }
  ]
}
```

环境检查的是：

```text
时间格式是否正确
温度条件是否可表达
设备是否存在
设备是否支持对应动作
动作参数是否满足 Schema
```

环境不回答“14:00 时温度是否真的超过 35 度”，因为这需要真实环境演化。返回结果中应明确写出：

```json
{
  "semantic_status": "valid",
  "execution_status": "not_simulated"
}
```

这样可以避免把“语义预约有效”误写成“设备已经执行成功”。

---

## 5. 一次环境交互应该怎么走

推荐把每个时间任务设计成一步或极少步的回合：

```text
reset()
    ↓
返回任务文本、当前时间、设备目录
    ↓
模型生成一个结构化动作
    ↓
step(action)
    ↓
解析与归一化
    ↓
校验时间语义
    ↓
校验设备动作
    ↓
计算奖励
    ↓
terminated=True
```

伪代码如下：

```python
obs, info = env.reset(seed=seed)
action = policy(obs)
next_obs, reward, terminated, truncated, info = env.step(action)
```

这个 `step` 不做以下事情：

```text
不 sleep
不启动后台模拟线程
不调用 HTTP 服务
不推进 tick
不轮询 workflow 状态
不等待未来检查点
```

如果要支持多动作预约，仍然在同一个结构化动作内表达，不把“预约第一步”和“等待执行结果”拆成多个真实时间轮次。

---

## 6. 奖励设计

推荐使用确定性、可拆解的稠密奖励，而不是只返回一个最终 0/1。

```text
R = 0.25 × 结构合法性
  + 0.35 × 时间触发器正确性
  + 0.25 × 设备与动作正确性
  + 0.10 × 条件与周期正确性
  + 0.05 × 安全性与冗余控制
  - 错误惩罚
```

各项含义如下：

```text
结构合法性：JSON、字段类型、必填字段正确
时间触发器：relative、absolute、event_after 等类型正确，数值或事件关系正确
设备与动作：设备 ID、命令名称、参数值正确
条件与周期：状态条件、每日/每周等重复关系正确
安全性：没有额外执行用户未要求的立即动作，没有重复或冲突动作
```

以“十分钟后关卧室灯”为例：

```text
输出完整正确的 schedule       → 1.0
输出关卧室灯，但立即执行        → 0.55 左右
输出十分钟后开卧室灯            → 0.25 左右
输出十分钟后关客厅灯            → 0.20 左右
JSON 损坏或缺少动作             → 0 或负分
```

具体权重可以在小规模实验中调整，但奖励项要保持稳定，不能随着评审模型的随机输出变化。

### 6.1 为什么不能只给“预约成功”奖励

如果环境只检查 JSON 是否可解析，模型可能学会下面这种投机策略：

```text
永远输出 schedule
永远给一个未来时间
动作内容随便填
```

因此至少要检查四个层次：

```text
能不能解析
时间关系对不对
设备动作对不对
有没有多余或危险动作
```

### 6.2 适合 GRPO 的奖励形态

GRPO 一组样本需要在同一个任务上比较相对表现。因此建议：

```text
同一条用户任务
    ↓
采样 G 条模型输出
    ↓
逐条用同一个确定性 validator 评分
    ↓
组内标准化奖励
    ↓
更新模型
```

不建议把 LLM Judge 放在这个内循环中。DeepSeek 可以用于离线生成任务、改写用户表达和做抽样质量复核，但训练时的核心奖励应该由本地规则校验器完成。

---

## 7. 三个具体例子

### 7.1 相对时间任务

```text
用户：十分钟后关卧室灯。
当前时间：2026-09-22 09:00:00
```

目标：

```json
{
  "trigger": {
    "kind": "relative_time",
    "offset_seconds": 600
  },
  "actions": [
    {
      "device_id": "bedroom.light",
      "command": "turn_off",
      "arguments": {}
    }
  ]
}
```

环境只比较“十分钟后”和“关卧室灯”是否被正确表达，不等待 600 秒。

### 7.2 事件依赖任务

```text
用户：洗碗机完成后打开厨房灯。
```

目标：

```json
{
  "trigger": {
    "kind": "event_after",
    "event": {
      "device_id": "dishwasher",
      "name": "completed"
    }
  },
  "actions": [
    {
      "device_id": "kitchen.light",
      "command": "turn_on",
      "arguments": {}
    }
  ]
}
```

环境校验洗碗机是否有 `completed` 事件、厨房灯是否支持 `turn_on`，但不真的启动洗碗机，也不等待完成事件。

### 7.3 时间与状态组合任务

```text
用户：每天晚上六点，如果客厅温度高于 28 度，就打开风扇。
```

目标语义中包含三部分：

```text
周期：daily
时间：18:00
条件：living_room.temperature > 28
动作：living_room.fan.turn_on
```

这个任务可以训练模型理解“每天”“晚上六点”“如果”之间的组合关系。它不能证明模型已经学会了 18:00 时根据真实温度做出动态控制，这一部分属于后续完整模拟阶段。

---

## 8. 与 SimuHome 的能力边界

可以把两者的定位放在同一张图中：

```text
                         时间任务能力

语义校验环境  ───────────────────────────────┐
    时间表达理解                             │
    时间关系结构化                           │
    设备动作绑定                             │  高吞吐、低延迟、适合 RL
    事件依赖表达                             │
    静态条件校验                             │
                                             │
SimuHome     ────────────────────────────────┘
    虚拟时钟推进
    设备持续演化
    聚合器更新
    未来任务触发
    工作流执行
    快进评测
                                             高真实性、较低训练吞吐
```

更准确的对比是：

```text
能力                         语义校验环境       SimuHome
时间文本解析                 支持               支持
相对/绝对时间换算             支持               支持
时间触发器结构化               支持               支持
未来动作实际到点执行           不模拟             支持
设备状态随时间变化             不模拟             支持
温度/湿度等环境动力学           不模拟             支持
多工作流竞态                   只做静态检查       支持部分机制
即时确定性奖励                 支持               需要快进或事后评测
高并行 GRPO rollout            适合               成本较高
```

所以这个简化方案并不是替代 SimuHome 的全部功能，而是把“时间任务”拆成两个研究层次：

```text
第一层：时间语义决策
第二层：时间驱动执行与环境动力学
```

HomeFlow 的 Demo 应先完成第一层。只有当实验问题确实涉及第二层，才引入虚拟时钟。

---

## 9. 对 SFT、RL 和 DeepSeek 数据生成的适配

### 9.1 SFT 数据

每条 SFT 样本可以包含：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "十分钟后关卧室灯。"
    },
    {
      "role": "assistant",
      "content": "{\"action\":\"schedule\",\"trigger\":{\"kind\":\"relative_time\",\"offset_seconds\":600},\"actions\":[{\"device_id\":\"bedroom.light\",\"command\":\"turn_off\",\"arguments\":{}}]}"
    }
  ]
}
```

DeepSeek API 可以用于离线生成：

```text
同一时间意图的多种自然语言表达
边界案例与容易混淆的表达
错误输出与错误类型标注
时间、事件、状态条件的组合任务
```

但生成后的样本必须经过本地 Schema 和 validator 过滤，不能直接把 DeepSeek 生成结果全部作为正确答案。

### 9.2 RL 数据

RL 阶段不需要等待未来事件。环境在 `step` 中直接完成语义评价：

```text
任务采样
    ↓
模型输出动作
    ↓
确定性校验器评分
    ↓
返回 reward
    ↓
进入下一条 episode
```

这使得在线 rollout 具有明确的成本：主要是模型推理，不再叠加 SimuHome 的 HTTP、后台线程、sleep 和 fast-forward。

### 9.3 评测数据

评测集要区分“表达变化”和“语义变化”：

```text
同一语义，不同说法：
    十分钟后关灯
    过十分钟把灯关掉
    现在不用关，十分钟后关闭卧室灯

不同语义，表面相似：
    现在关卧室灯
    十分钟后关卧室灯
    卧室灯亮着时关掉它
```

评测指标至少包括：

```text
完整语义准确率
时间触发器准确率
设备动作准确率
结构化输出合法率
安全性错误率
```

---

## 10. 推荐的落地模块

后续实现可以按下面的文件边界展开：

```text
homeflow_demo/env/time_schema.py
    定义 TemporalIntent、Trigger、Condition、DeviceAction 的结构

homeflow_demo/env/time_normalizer.py
    将相对时间、绝对时间、事件依赖统一成标准结构

homeflow_demo/env/time_validator.py
    执行 Schema、时间关系、设备能力和安全规则校验

homeflow_demo/env/time_scenarios.py
    生成与读取时间任务、目标语义和设备目录

homeflow_demo/env/home_env.py
    在现有 HomeEnv 中接入时间语义任务模式

homeflow_demo/data/time_tasks.json
    保存训练、验证、测试任务及其标准答案
```

建议调用关系：

```text
HomeEnv.step(action)
    ├── TimeNormalizer.normalize(action)
    ├── TimeValidator.validate(normalized, task)
    ├── RewardCalculator.score(result)
    └── 返回 observation, reward, terminated, truncated, info
```

`TimeValidator` 的返回结果应同时给出总分和分项原因，便于调试：

```json
{
  "valid": true,
  "score": 0.85,
  "components": {
    "structure": 1.0,
    "time": 1.0,
    "device_action": 0.8,
    "conditions": 0.0,
    "safety": 1.0
  },
  "errors": [],
  "semantic_status": "valid",
  "execution_status": "not_simulated"
}
```

---

## 11. 分阶段实施建议

```text
阶段 A：相对时间与绝对时间
    支持“十分钟后”“今天 18:30”
    支持 execute_now 与 schedule
    支持单设备单动作
    目标：先验证 SFT 与 GRPO 奖励闭环

阶段 B：事件依赖与多动作
    支持“洗碗机完成后”
    支持一个触发器对应多个动作
    支持设备能力和非法动作检查
    目标：验证时间语义与设备规划的结合

阶段 C：时间加状态条件
    支持“每天 18:00，如果温度高于 28 度”
    支持周期、阈值和静态冲突检查
    目标：扩展任务难度，但仍不推进真实时间

阶段 D：可选的符号时间执行
    引入离散事件表或符号时间点
    只在事件关系需要验证时推进“逻辑时刻”
    仍不运行真实 sleep 和连续设备动力学
    目标：在吞吐与真实性之间增加一层折中

阶段 E：完整虚拟时间模拟
    才考虑接入 SimuHome 类 tick、设备演化和快进机制
    目标：研究真实时间执行、延迟、竞态和环境反馈
```

### 11.1 阶段 D 是否值得做

如果后续只关心单轮预约是否正确，阶段 A 到 C 已经够用；如果需要验证“任务之间是否按先后关系冲突”，可以加入轻量符号时间：

```text
事件 A：洗碗机完成
事件 B：厨房灯打开
约束：A < B
```

这里的 `A < B` 仍然是逻辑关系，不代表环境真的经过了洗碗机运行时间。它比纯字符串校验更可靠，又不会承担 SimuHome 全部时间模拟成本。

---

## 12. 最终判断

用“语义校验、不实际模拟时间”的方式实现时间强化学习是可行的，而且适合当前 HomeFlow Demo 的目标。正确的实现重点有三点：

```text
一、把自然语言时间转换成统一的 TemporalIntent

二、把奖励交给确定性 validator，而不是交给自由发挥的 LLM Judge

三、在结果中明确区分“语义预约有效”和“未来设备已经执行”
```

推荐当前 HomeFlow 采用下面的最小方案：

```text
固定 current_time
    +
相对/绝对/事件三类时间触发器
    +
结构化 schedule 动作
    +
设备能力校验
    +
立即稠密奖励
    +
单步 episode
```

这样可以保留时间任务最核心的决策难点，又把 SimuHome 中最影响强化学习吞吐的后台推进、真实 sleep、API 轮询和事后快进全部移出训练内循环。最终得到的是一个适合科研入门、可被 SFT 初始化、可被 LoRA-GRPO 优化、也可以在后续逐步升级到符号时间和完整模拟的 HomeFlow 时间环境。
