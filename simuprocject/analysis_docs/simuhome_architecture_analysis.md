# SimuHome 智能家居仿真架构深度分析

> 基于论文（ICLR 2026 Oral）、项目源码结构及 README 综合梳理

---

## 一、项目整体架构总览

### 1.1 目录结构

```
Simuhome_experiment/
├── src/                          # 核心源码
│   ├── cli/                      # 命令行入口（simuhome 命令）
│   │   ├── main.py               # CLI 入口，注册所有子命令
│   │   ├── episode_generator.py   # Episode 生成器
│   │   ├── episode_evaluator.py   # Episode 评估器
│   │   ├── parallel_model_evaluation.py  # 并行模型评估
│   │   ├── config_resolver.py     # 配置解析
│   │   └── artifact_audit.py      # 产出审计
│   │
│   ├── simulator/                # 核心模拟器
│   │   ├── api/                  # FastAPI 对外接口层
│   │   │   ├── routes.py         # API 路由（设备控制、时间加速、工作流等）
│   │   │   ├── schemas.py        # 请求/响应 Schema
│   │   │   ├── responses.py      # 响应构建器
│   │   │   └── app.py            # FastAPI 应用
│   │   │
│   │   ├── domain/               # 领域模型（核心仿真逻辑）
│   │   │   ├── home.py           # Home 类：仿真引擎核心（Tick 循环、调度队列）
│   │   │   ├── result.py         # 结果/错误码定义
│   │   │   ├── devices/          # 17 种设备类型
│   │   │   │   ├── base.py       # Device 基类
│   │   │   │   ├── air_conditioner.py
│   │   │   │   ├── heat_pump.py
│   │   │   │   ├── fan.py
│   │   │   │   ├── dehumidifier.py
│   │   │   │   ├── humidifier.py
│   │   │   │   ├── air_purifier.py
│   │   │   │   ├── dishwasher.py
│   │   │   │   ├── laundry_washer.py
│   │   │   │   ├── laundry_dryer.py
│   │   │   │   ├── refrigerator.py
│   │   │   │   ├── freezer.py
│   │   │   │   ├── on_off_light.py
│   │   │   │   ├── dimmable_light.py
│   │   │   │   ├── tv.py
│   │   │   │   ├── rvc.py        # 机器人吸尘器
│   │   │   │   ├── electrical_sensor.py
│   │   │   │   └── window_covering_controller.py
│   │   │   │
│   │   │   ├── clusters/         # Matter 协议 Cluster 实现
│   │   │   │   ├── base.py       # Cluster 基类
│   │   │   │   ├── onoff.py
│   │   │   │   ├── fan_control.py
│   │   │   │   ├── thermostat.py
│   │   │   │   ├── temperature_measurement.py
│   │   │   │   ├── level_control.py
│   │   │   │   ├── operational_state.py
│   │   │   │   ├── rvc_run_mode.py
│   │   │   │   ├── rvc_clean_mode.py
│   │   │   │   ├── rvc_operational_state.py
│   │   │   │   ├── laundry_washer_mode.py
│   │   │   │   ├── laundry_washer_controls.py
│   │   │   │   ├── laundry_dryer_controls.py
│   │   │   │   ├── dishwasher_mode.py
│   │   │   │   ├── dishwasher_alarm.py
│   │   │   │   ├── media_playback.py
│   │   │   │   └── ... （共约 30+ 个 Cluster）
│   │   │   │
│   │   │   └── aggregators/      # 环境变量聚合器
│   │   │       ├── base.py       # Aggregator 基类
│   │   │       ├── temperature.py    # 温度计算引擎
│   │   │       ├── humidity.py       # 湿度计算引擎
│   │   │       ├── illuminance.py    # 照度计算引擎
│   │   │       ├── pm10.py           # 空气质量（PM10）计算引擎
│   │   │       └── registry.py       # 聚合器注册表
│   │   │
│   │   └── application/          # 应用层（设备工厂、Home 初始化）
│   │       ├── device_factory.py
│   │       └── home_initializer.py
│   │
│   ├── agents/                   # LLM Agent 实现
│   │   ├── tools.py              # Agent 可用工具定义（调用模拟器 API）
│   │   ├── types.py              # Agent 类型定义
│   │   ├── strategies/           # 多种 Agent 策略
│   │   │   ├── base.py
│   │   │   ├── react_agent.py    # ReAct（推理+行动）
│   │   │   └── hi_agent.py       # HI Agent（层次化指令）
│   │   ├── providers/            # LLM 提供商封装
│   │   │   ├── base.py
│   │   │   └── openai_provider.py
│   │   └── memory/               # 记忆管理
│   │       └── hi_memory.py
│   │
│   ├── pipelines/                # 流水线
│   │   ├── episode_generation/   # Episode 生成流水线（按 QT 分类）
│   │   │   ├── core/             # 核心生成逻辑
│   │   │   ├── qt1/ ~ qt4_3/    # 各查询类型生成器
│   │   │   └── shared/           # 共享工具
│   │   └── episode_evaluation/   # Episode 评估流水线
│   │       ├── runner.py
│   │       ├── common.py
│   │       ├── qt1/ ~ qt4/       # 各查询类型评估逻辑
│   │       └── aggregate_results.py / aggregate_all_results.py
│   │
│   └── clients/
│       └── smarthome_client.py   # 模拟器 HTTP 客户端
│
├── data/
│   ├── benchmark/                # 600 个预制 Episode
│   │   ├── qt1_feasible_seed_*.json
│   │   ├── qt1_infeasible_seed_*.json
│   │   ├── ...（qt2 ~ qt4-3，各 50 个可行 + 50 个不可行）
│   │   └── vector_db/            # Matter 协议文档向量数据库（FAISS）
│   │
├── docs/
│   └── clusters/                 # 70 个 Matter Cluster 描述文档（英文）
│
├── experiments/                  # 评估实验输出
│
├── assets/
│   └── figures/                  # 架构图、流程图
│
├── prompts/                      # Agent Prompt 模板（推测路径）
├── pyproject.toml                # 项目配置及依赖
└── README.md / README_CN.md      # 项目说明
```

### 1.2 技术栈

| 组件 | 技术 |
|------|------|
| 模拟器后端 | Python + FastAPI + Uvicorn |
| 仿真引擎 | 自研 Tick 离散时间框架（`Home` 类） |
| 设备协议 | 基于 **Matter 协议**的 Cluster/Attribute/Command 架构 |
| Agent 框架 | ReAct（默认）+ HI（层次化）策略 |
| LLM 接入 | OpenAI / OpenRouter API + 本地推理端点 |
| 向量检索 | FAISS + LangChain（用于 Matter 协议文档 RAG） |
| 进程管理 | 多进程并行评估（`concurrent.futures`） |
| 构建工具 | uv（Python 包管理） |

---

## 二、核心仿真机制详解

### 2.1 Tick 驱动的时间系统

SimuHome 的核心是一个**离散时间步（Tick）**驱动引擎，由 `Home` 类实现。

#### 工作原理

```
每个 Tick = 0.1 秒（可配置）
虚拟时间 = 基准时间 + Tick 数 × Tick 间隔

Tick 循环处理逻辑（simulator/domain/home.py）：
1. 处理 API 请求队列（设备控制命令）
2. 执行 Tick 到达的工作流任务（从 PriorityQueue 弹出）
3. 对每个时间感知设备调用 on_time_tick()
4. 更新环境变量聚合器（温度、湿度、照度、PM10）
5. Tick 计数 +1
6. 等待（实时的 Tick 间隔 × 时间加速系数）
```

#### 时间加速机制

SimuHome 支持两种时间推进模式：

- **实时模式**（默认）：每个 Tick 实际等待 0.1s，与真实时间 1:1 同步
- **时间加速模式**（Fast-Forward）：通过 `fast_forward` 标志或 API 调用，跳过等待直接推进虚拟时间。这在评估工作流调度（QT4）时至关重要——无需等待实际的"10分钟后"，而是直接快进到目标时间点检查结果

#### 确定性保证

由于 Tick 是离散且确定的，给定相同的**初始种子**和**操作序列**，仿真结果完全可重现。这是通过：

- 伪随机种子控制所有随机化过程
- Tick 状态更新使用确定性的数学公式
- 设备状态转换由 Cluster 规则严格约束

### 2.2 Matter 协议的实现模型

#### 四层协议架构

```
┌─────────────────────────────────────────────┐
│                Endpoint                      │  (设备端点：每个设备可有多个)
├─────────────────────────────────────────────┤
│  Cluster A  │  Cluster B  │  Cluster C      │  (功能集群：如 OnOff、Thermostat)
├─────────────┴─────────────┴─────────────────┤
│  Attribute  │  Attribute  │  Attribute      │  (属性：如 OnOff=true, Temp=25°C)
├─────────────┴─────────────┴─────────────────┤
│  Command   │  Command    │  Command         │  (命令：如 TurnOn, SetTemperature)
└─────────────────────────────────────────────┘
```

#### 具体实现

每个设备（如 `AirConditioner`）内部维护多个 **Endpoint**，每个 Endpoint 挂载多个 **Cluster**：

```python
# air_conditioner.py （简化结构）
class AirConditioner(Device):
    endpoints = {
        1: {
            "OnOff": OnOffCluster,              # 开关控制
            "FanControl": FanControlCluster,     # 风扇控制
            "Thermostat": ThermostatCluster,     # 恒温控制
            "TemperatureMeasurement": ...,       # 温度传感器
        },
        2: {
            "RelativeHumidityMeasurement": ..., # 湿度传感器
        },
    }
```

**Agent 通过 Cluster Command 与设备交互**，而非直接修改设备状态。例如：

- 调用 `OnOff.TurnOn()` → 设备 OnOff 属性变为 true
- 调用 `Thermostat.Setpoint()` → 设置目标温度
- 调用 `OperationalState.Start()` → 启动洗碗机等设备的运作周期

**操作依赖约束**同样在 Matter Cluster 层面实现。例如：
- 空调必须先 `OnOff.TurnOn()` 后才能设置温度
- 机器人吸尘器必须在开机后才能切换到拖地模式

### 2.3 环境变量动态仿真系统

这是 SimuHome 区别于其他基准测试的核心创新——设备操作会**持续影响环境变量**。

#### 四种环境变量

| 变量 | 单位 | 聚合器实现 |
|------|------|-----------|
| 温度 (Temperature) | °C | `TemperatureAggregator` |
| 湿度 (Humidity) | %RH | `HumidityAggregator` |
| 照度 (Illuminance) | lux | `IlluminanceAggregator` |
| 空气颗粒物 (PM10) | μg/m³ | `PM10Aggregator` |

#### 环境变量更新流程

```
每个 Tick：
  1. 聚合器轮询所有已监控设备的状态变化
  2. 若有变化，调用 _recalculate() 重新计算连续影响
  3. 将各设备的环境影响累加到 `continuous_effects` 字典
  4. 计算总影响值并更新 current_value
  5. 添加自然回复效应（如温度向 baseline 回归）
  6. 将环境值同步回设备的传感器属性
```

以 **TemperatureAggregator** 为例：

```python
# 温度变化的计算公式（简化）
temp_diff = (current_value - target_setpoint) / 100.0
cooling_rate = min(0.0005, temp_diff * 1.0) * fan_intensity
delta_per_tick = -(cooling_rate * 100.0) * tick_interval

# 自然回复效应
delta = baseline_value - current_value  # 向基准温度回归
current_value += delta * restoration_rate * tick_interval
```

关键特性：
- **多设备叠加**：两台空调同时运行比一台降温更快
- **设备差异性**：空调、热泵、风扇各自有不同的制冷/制热效率系数
- **风扇强度影响**：风扇转速百分比直接影响降温速率
- **自然回复**：关闭制冷设备后，温度会缓慢回复到基线值
- **传感器同步**：设备的温度传感器属性在每个 Tick 被更新为当前环境温度

### 2.4 工作流调度系统

#### 调度队列

Home 内部维护一个 `PriorityQueue` 作为调度队列：

```python
self.schedular_queue: PriorityQueue[tuple[int, int, str, Any]]
# 优先级 = (目标Tick, 序列号, 操作ID, 参数)
```

#### 工作流注册流程

1. Agent 调用 `schedule_workflow(time, steps[])` API
2. 模拟器将相对时间/用户指定的时间转换为绝对 Tick 数
3. 将工作流注册到 `workflows_by_id` 字典
4. 在调度队列中按 Tick 排序插入
5. 当 Tick 到达时，引擎自动执行对应命令

#### 工作流类型

| 类型 | 说明 |
|------|------|
| QT4-1 时间基调度 | "10分钟后关灯" → 转换为绝对时间 → 注册工作流 |
| QT4-2 事件驱动调度 | "洗碗机完成后开灯" → 查询洗碗机剩余时间 → 计算完成时间 → 注册工作流 |
| QT4-3 协调调度 | "让洗碗机和洗衣机同时完成" → 查询两者周期 → 计算同步点 → 注册工作流 |

**重要设计**：模拟器只确认工作流已注册，不提前验证命令能否执行成功。这模拟了真实智能家居中设备状态在调度和执行之间可能发生变化的情况。

---

## 三、Agent-模拟器交互机制

### 3.1 Agent 可用工具

Agent 通过 `tools.py` 中定义的函数与模拟器交互，这些工具封装了对模拟器 REST API 的调用：

| 工具 | 功能 |
|------|------|
| `get_room_devices(room)` | 获取指定房间的所有设备清单 |
| `get_device_state(room, device)` | 获取设备当前状态（所有属性） |
| `get_environment(room)` | 获取房间环境变量（温湿度等） |
| `command(room, device, cluster, cmd, params)` | 执行设备命令 |
| `read_attribute(room, device, endpoint, cluster, attr)` | 读取设备属性 |
| `schedule_workflow(time, steps[])` | 注册定时工作流 |
| `fast_forward()` | 时间加速/快进 |
| `search_matter_docs(query)` | 检索 Matter 协议文档（RAG） |

### 3.2 通信流程

```
Agent (LLM)                   模拟器 FastAPI Server              Home 引擎
    │                              │                              │
    │── HTTP POST /api/command ────→│                              │
    │                              │── queue_api("command", ...) ─→│
    │                              │                              │── 加入 API 队列
    │                              │                              │── 下一 Tick 处理
    │                              │←── Result ───────────────────│
    │←── HTTP Response ────────────│                              │
    │                              │                              │
    │── HTTP POST /api/get_device ─→│                              │
    │                              │── queue_api("device_info") ──→│
    │                              │←── Result ───────────────────│
    │←── HTTP Response ────────────│                              │
```

### 3.3 策略框架

#### ReAct 策略（默认）

```
循环：
  1. Observation（观察当前环境）
  2. Thought（推理：当前状态、目标差距、下一步计划）
  3. Action（调用工具改变环境）
  4. 回到步骤 1（或完成）
```

#### HI 策略（层次化指令，`hi_agent.py`）

将任务分解为高层规划和低层执行，复用相同的工具集但增加了记忆管理（`hi_memory.py`）。

---

## 四、Episode 生成与评估

### 4.1 600 个 Episode 的组成

| 查询类型 | 简称 | 可行 | 不可行 |
|---------|------|------|--------|
| 状态查询 | QT1 | 50 | 50 |
| 隐式意图推断 | QT2 | 50 | 50 |
| 显式设备控制 | QT3 | 50 | 50 |
| 时间基调度 | QT4-1 | 50 | 50 |
| 事件驱动调度 | QT4-2 | 50 | 50 |
| 协调调度 | QT4-3 | 50 | 50 |
| **合计** | | **300** | **300** |

### 4.2 Episode 生成三步流程

**Step 1：初始家庭状态构建**
- 随机生成房间布局和设备配置（基于种子确保可重现）
- 从全关状态开始，多轮随机化设备状态
- 遵守设备操作依赖顺序（先开机后调温）
- 时间加速使环境变量更新到稳定状态

**Step 2：目标与前置操作生成**
- 为每个 Episode 定义结构化 Goal（目标设备、属性、环境变化方向等）
- 设置前置操作（Prerequisite Actions）：如必须先查询房间设备再操作

**Step 3：Query 合成**
- 使用 GPT-5 mini 从 Goal 生成自然语言查询
- 两位研究生独立人工验证，Cohen's κ = 0.92

### 4.3 不可行 Episode 的三种类型

| 类型 | 示例 |
|------|------|
| 设备不存在 | 要求打开客厅中不存在的加湿器 |
| 物理极限 | 要求将已开到最大风速的空气净化器再加速 |
| 时间矛盾 | 要求空调在 1 分钟内将房间从 30°C 降到 18°C（物理不可达） |

### 4.4 两种评估方法

#### 基于模拟器的评估（Simulator-Based）
- 适用于涉及物理状态变化的 Episode（QT2/3/4 的可行场景）
- 直接将最终设备状态与 Goal 比较
- 确保前置操作在 Agent 工具调用历史中出现

#### LLM-as-a-Judge 评估
- 适用于需要自然语言响应的 Episode（所有不可行场景 + QT1 可行）
- 提供完整推理轨迹给 Judge 模型
- 每个 Episode 投票 3 次取多数决
- 与人工评估的 Cohen's κ = 0.826

---

## 五、Matter 协议 Cluster 实现体系

项目实现了约 **30+ 个 Matter Cluster**，分布在 `src/simulator/domain/clusters/` 下。每个 Cluster 对应 Matter 协议标准中定义的一个功能组。

### Cluster 类型与被覆盖设备

| Cluster 类 | 适用设备 | 代码文件 |
|------------|---------|---------|
| OnOff | 所有开关设备 | `onoff.py` |
| FanControl | 风扇、空调、热泵 | `fan_control.py` |
| Thermostat | 空调、热泵 | `thermostat.py` |
| LevelControl | 可调光灯 | `level_control.py` |
| OperationalState | 洗碗机、洗衣机、烘干机 | `operational_state.py` |
| TemperatureMeasurement | 温控设备 | `temperature_measurement.py` |
| RelativeHumidityMeasurement | 湿度传感器 | `relative_humidity_measurement.py` |
| LaundryWasherMode / LaundryWasherControls | 洗衣机 | `laundry_washer_mode.py` |
| DishwasherMode / DishwasherAlarm | 洗碗机 | `dishwasher_mode.py` |
| RVCRunMode / RVCCleanMode / RVCOperationalState | 机器人吸尘器 | `rvc_*.py` |
| MediaPlayback | TV | `media_playback.py` |
| ... | ... | ... |

### Cluster 的核心作用

每个 Cluster 实现三个关键功能：
1. **属性管理**：维护设备属性值（如 OnOff 的布尔值、Thermostat 的目标温度）
2. **命令处理**：接收并执行 Matter 命令（如 On、Off、Setpoint 等）
3. **时间回调**：`on_time_tick()` 方法处理时间驱动的状态变化（如洗衣机按 Tick 推进洗涤阶段）

### 设备工厂模式

`device_factory.py` 通过工厂模式创建设备实例，自动为每个设备组装所需的 Cluster 集合。

---

## 六、评估流水线：并行架构

`episode_evaluator.py` 和 `parallel_model_evaluation.py` 实现了高效的并行评估架构：

```
用户配置 YAML
    │
    ▼
config_resolver.py    解析配置，解析种子范围
    │
    ▼
episode_evaluator.py  分配 Episode 到工作进程
    │
    ├── Worker 1: Simulator Server Port 8001 + Agent Instance 1
    ├── Worker 2: Simulator Server Port 8002 + Agent Instance 2
    ├── ...
    │
    ▼
各 Worker 独立运行：
  1. 读取 Episode JSON（初始家居状态 + 用户 Query + Goal）
  2. 重置模拟器到初始状态
  3. 向 Agent 发送 Query
  4. Agent 执行 ReAct 循环（观察→推理→行动）
  5. 模拟器记录所有状态变化
  6. 评估器比较最终状态与 Goal
  7. 输出结果到 experiments/<run_id>/ 目录
```

关键特性：
- **多模型并行**：一个配置可评估多个模型
- **中断恢复**：`eval-resume` 支持从断点继续
- **结果聚合**：`aggregate` / `aggregate-all` 汇总统计
- **模拟器健康检查**：自动确保模拟器正常运行

---

## 七、关键设计决策总结

| 设计决策 | 实现 | 目的 |
|---------|------|------|
| **Tick 驱动** | 0.1s 离散时间步 | 确定性 + 可加速 |
| **Matter 协议** | Cluster/Attribute/Command 三层 | 工业标准兼容，真实设备等价 |
| **环境联动** | Aggregator 聚合器体系 | 设备操作对环境有真实连续影响 |
| **工作流调度** | PriorityQueue + 时间加速 | 无需等待真实时间流逝 |
| **时间加速** | 跳过 Tick 等待 + 批量推进 | 大规模评估可行 |
| **并行评估** | 多进程 + 多模拟器实例 | 高效批量评估 |
| **可重现性** | 种子控制 + 确定性计算 | 公平比较不同模型 |
| **双重评估** | 模拟器状态比较 + LLM Judge | 物理变化和对话响应都能评估 |
| **RAG 支持** | FAISS 向量库检索 Matter 文档 | Agent 可查询协议规范 |

---

## 八、与传统基准测试的核心区别

| 特性 | 现有基准（HomeBench, Sasha 等） | SimuHome |
|------|-------------------------------|----------|
| 环境动态变化 | ❌ 静态状态 | ✅ 设备操作持续影响环境变量 |
| 操作依赖 | ❌ 无约束 | ✅ Matter 协议强制执行操作顺序 |
| 时间感知 | ❌ 无时间概念 | ✅ Tick 驱动，支持定时/延时操作 |
| 工作流调度 | ❌ 不支持 | ✅ 支持未来命令调度 |
| 时间加速 | ❌ 必须实时等待 | ✅ 可快进到任意时间点 |
| 物理真实感 | ❌ 抽象指令匹配 | ✅ 温度/湿度等连续物理建模 |
| 不可行请求 | 部分支持 | ✅ 系统化的三类不可行场景 |
| 协议基础 | 自定义 API | ✅ 基于 Matter 行业标准 |

---

## 九、总结

SimuHome 是一个**时间加速的、环境感知的、基于 Matter 协议**的智能家居仿真平台。其核心创新在于：

1. **环境-设备闭环**：设备操作不是一次性指令，而是持续影响环境变量（温度/湿度/照度/PM10），Agent 需要实时监控并响应
2. **时间维度引入**：支持定时调度、事件触发调度、多设备同步调度，并通过时间加速使评估成为可能
3. **Matter 工业标准**：设备行为严格遵循真实协议规范，确保仿真结果可迁移到物理设备
4. **高质量基准**：600 个人工验证的 Episode，覆盖 6 种查询类型 × 可行/不可行变体

从代码架构看，它分为**模拟器引擎**（Home + Tick + Aggregator + Cluster）、**Agent 框架**（ReAct/HI + Tools + LLM Provider）、**评估流水线**（Generator + Evaluator + Aggregator）三大部分，通过 REST API + 并行进程实现高效的大规模 LLM Agent 评估。

