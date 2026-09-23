# SimuHome 设备建模机制梳理

## 这份文档回答什么问题

这份文档聚焦一个问题：**SimuHome 里的“设备”到底是怎么建模、怎么执行命令、怎么判断成功的。**

你关心的几个点，我在下面会分别回答：

- 它是不是状态机？
- 它是怎么和 Matter 协议对应上的？
- 什么样的指令算“符合 Matter”，什么样算“驱动成功”？
- “命令执行成功”和“环境真的发生目标变化”是不是同一回事？

先给一个短结论：

- **它不是一个统一的全局状态机框架**。
- 它更像是一个 **Matter 风格的设备对象模型**：
  - 设备 = `Device`
  - 能力 = `Cluster`
  - 状态 = `attributes`
  - 行为 = `commands`
- 某些设备或 cluster 内部又会带有**局部状态机/过程机**，例如洗碗机运行流程、调光灯渐变、倒计时执行等。

所以最准确的说法是：

- **底层结构是对象模型**
- **局部行为上有状态机特征**

## 1. 总体设备模型：不是“一个大状态机”，而是 Device + Cluster

### 1.1 核心抽象

设备基类在 [base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:7)。

一个设备对象包含：

- `device_id`
- `device_type`
- `endpoints`

其中 `endpoints` 的结构是：

- `endpoint_id -> { cluster_id -> cluster_instance }`

这其实就是在模拟 Matter 的典型组织形式：

- 一个物理设备可以有多个 endpoint
- 每个 endpoint 上挂多个 cluster
- 每个 cluster 里有 attribute 和 command

换句话说，这个项目不是直接模拟“品牌 API”，而是在模拟 **Matter 应用层设备模型**。

### 1.2 命令和属性是怎么走的

设备对外有两个最关键的入口：

- `execute_command(endpoint_id, cluster_id, command_id, **args)`
- `write_attribute(endpoint_id, cluster_id, attribute_id, value)`

对应代码见 [base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:56) 和 [base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:66)。

也就是说，agent 真正“驱动设备”时，发的不是一句抽象的“把空调调低”，而是更底层的结构化指令，例如：

```json
{
  "device_id": "living_room_ac_1",
  "endpoint_id": 1,
  "cluster_id": "Thermostat",
  "attribute_id": "SystemMode",
  "value": 3
}
```

或者：

```json
{
  "device_id": "bathroom_light_1",
  "endpoint_id": 1,
  "cluster_id": "OnOff",
  "command_id": "On",
  "args": {}
}
```

所以，从接口形式上说，它和 Matter 的匹配方式不是“按完整官方协议栈逐位兼容”，而是：

- **采用 Matter 的 endpoint / cluster / attribute / command 组织方式**
- **采用 Matter 风格的 cluster 名称和能力语义**

## 2. Cluster 是真正的“能力单元”

### 2.1 Cluster 基类定义了统一执行协议

Cluster 基类在 [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:6)。

一个 cluster 内部一般有三部分：

- `attributes`
- `commands`
- `readonly_attributes`

例如 `OnOffCluster` 在 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:14) 里：

- attribute 有 `OnOff`
- command 有 `On` / `Off` / `Toggle`

Cluster 基类的 `execute_command()` 做的事情很关键：

1. 检查 `command_id` 是否存在于 `self.commands`
2. 找到对应函数
3. 用传入参数执行
4. 把结果包装成 `Result`

这一步定义了“驱动成功”的最底层判定标准。

### 2.2 什么叫 cluster 级别的“成功”

最底层的成功标准其实很朴素：

- 命令名存在
- 参数类型/格式正确
- 当前状态允许执行
- 约束校验通过
- 执行函数返回 `Result.ok(...)`

如果这几步成立，这个命令就算**设备语义上执行成功**。

这和“环境有没有立即变成用户想要的结果”不是一回事。

## 3. 它是不是状态机？

### 3.1 不是统一大状态机

如果你问“整个设备系统是不是一个标准 FSM 框架”，答案是：**不是**。

项目里没有看到这种统一模式：

- `State` 抽象类
- `Transition` 表
- 统一状态图解释器

相反，它是把状态分散存放在：

- cluster attribute
- device 辅助字段
- time-aware cluster 的内部变量

所以更像：

- **面向对象状态模型**
- 而不是统一 FSM 引擎

### 3.2 但很多局部实现有明显状态机味道

虽然没有统一 FSM 框架，但很多 cluster/设备本身就是“带状态迁移规则的状态机”。

最明显的例子：

- `OperationalStateCluster`
- `LevelControlCluster`
- 洗碗机运行周期

比如 `OperationalStateCluster` 在 [operational_state.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/operational_state.py:66) 里有：

- `STOPPED`
- `RUNNING`
- `PAUSED`
- `ERROR`

并且：

- `Start` 只能从 `STOPPED` 进入 `RUNNING`
- `Pause` 只能从 `RUNNING` 进入 `PAUSED`
- `Resume` 只能从 `PAUSED` 回到 `RUNNING`
- `Stop` 会回到 `STOPPED`

这已经是一个很典型的局部状态机了。

所以更准确地说：

- **设备整体建模方式不是统一状态机**
- **但具体 cluster 经常就是一个小状态机**

## 4. 它是怎么“匹配” Matter 的

### 4.1 匹配的是应用层模型，不是完整协议栈

论文里反复强调它 grounded in Matter protocol。结合代码来看，这里的“grounded”主要体现在：

1. **设备能力按照 Matter cluster 划分**
2. **命令通过 cluster command 调用**
3. **状态通过 cluster attribute 表示**
4. **很多 cluster 名称直接沿用 Matter 术语**

例如：

- `OnOff`
- `FanControl`
- `Thermostat`
- `LevelControl`
- `RelativeHumidityMeasurement`
- `OperationalState`

也就是说，它在模拟的是：

- Matter 的**设备能力结构**
- Matter 的**控制语义**

而不是在模拟：

- 真实网络发现
- Pairing / commissioning
- Fabric / session
- IM 报文编码
- 真正的底层数据包收发

所以你可以把它理解成：

- **一个 Matter 应用层语义模拟器**
- 而不是完整 Matter 协议栈仿真器

### 4.2 “符合 Matter 协议”在这里是什么意思

在这个项目里，“符合 Matter”的实际含义更接近：

- `endpoint_id` 对
- `cluster_id` 对
- `command_id` 或 `attribute_id` 对
- 参数类型对
- 参数值满足该 cluster 约束
- 设备当前状态允许执行

如果这些满足了，系统就会把这次操作认定为“合法的 Matter 风格操作”。

它不会去做一些更底层的 Matter 校验，比如：

- 命令码是否和官方规范数值一一对应
- TLV 编码是否正确
- 是否通过真实设备网络链路发出

所以这里的“协议符合性”是**语义级符合性**，不是**线协议级符合性**。

## 5. “驱动成功”到底怎么判断

这个问题特别重要，因为它其实有两层。

### 5.1 第一层：命令/属性写入在设备语义上成功

这是最基础的成功定义。

如果 `execute_command()` 或 `write_attribute()` 最后返回 `Result.ok(...)`，那么：

- 这次驱动在模拟器里算成功
- HTTP 层会返回 200

相关包装见 [responses.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/api/responses.py:14)。

也就是说，“驱动成功”首先是：

- 找到了设备
- 找到了 endpoint
- 找到了 cluster
- 找到了 command / attribute
- 参数合法
- 状态合法
- 执行后没有违反约束

### 5.2 第二层：驱动成功不等于任务目标成功

这层特别容易混淆。

例如空调：

- 你成功发了 `On`
- 成功写了 `SystemMode = COOL`
- 成功写了 `OccupiedCoolingSetpoint = 2000`

这些都可以是“驱动成功”。

但这不等于：

- 房间温度立刻降到 20°C
- 用户目标已经完成

因为温度是后续由 `TemperatureAggregator` 逐 tick 连续变化的。

所以这里要区分：

- **控制层成功**：命令被设备接受并写入状态
- **环境层成功**：后续环境变化朝目标方向演进
- **任务层成功**：最终观测结果满足 benchmark 目标

这三层不是一回事。

## 6. 用空调做一个设备建模示例

空调代码在 [air_conditioner.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py:1)。

### 6.1 它怎么建模

空调这个设备在构造时挂了三个 cluster：

- `OnOff`
- `Thermostat`
- `FanControl`

也就是说，空调不是一个“大而全的自定义类逻辑”，而是把能力拆成了三个 Matter 风格能力块。

这其实很接近 Matter 的思想：

- 开关归 `OnOff`
- 温控归 `Thermostat`
- 风速归 `FanControl`

### 6.2 它怎么做约束

空调最关键的设备级逻辑是“电源依赖”。

在 [air_conditioner.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py:24)：

- 如果电源没开
- 你就不能去改 `Thermostat.SystemMode`
- 也不能改 `OccupiedCoolingSetpoint`
- 也不能改 `FanControl.PercentSetting`

这说明项目不是只做字段写入，而是会模拟“操作先后顺序要求”。

这也正是论文里说的：

- 某些设备操作必须按顺序来
- agent 不能只知道“目标值”，还得知道“先开什么、再调什么”

### 6.3 一个“成功”的空调控制序列是什么样

如果 agent 想让空调开始降温，合理序列通常是：

1. `OnOff.On`
2. `Thermostat.SystemMode = COOL`
3. `Thermostat.OccupiedCoolingSetpoint = 某个低于当前温度的值`
4. `FanControl.PercentSetting = 非零`

这四步里，前两三步只是让设备处于“可工作的控制状态”，最后还要满足温度聚合器识别条件，环境温度才会真正往下降。

所以空调这个例子很适合说明：

- **Matter 风格命令成功**
- 不等于
- **环境结果立刻成功**

## 7. 用调光灯做一个“时间过程”示例

调光灯代码在 [dimmable_light.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dimmable_light.py:1)，核心逻辑依赖 [level_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/level_control.py:7)。

### 7.1 为什么它不是纯静态属性写入

`LevelControlCluster` 不只是存一个 `CurrentLevel`。

它还维护：

- 过渡目标
- 剩余时间
- 每 tick 增量
- move/step 状态

所以当你发送 `MoveToLevel` 时，很多情况下不是“瞬时改到目标亮度”，而是：

- 进入一个过渡过程
- 每个 tick 更新 `CurrentLevel`
- 同步更新 `RemainingTime`

这就是很典型的**局部状态机/过程机**行为。

### 7.2 这说明什么

它说明项目里并不是所有设备都只有“命令来了 -> 立刻写值”这一种模式。

有些 cluster 本身就在模拟：

- 过程
- 渐变
- 时间依赖

所以设备模型是“静态属性 + 动态过程”混合的。

## 8. 用洗碗机做一个“更像状态机”的示例

洗碗机代码在 [dishwasher.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dishwasher.py:1)。

这是一个很好的例子，因为它比空调更像一个典型状态机系统。

### 8.1 它挂了哪些 cluster

洗碗机有这些核心 cluster：

- `OnOff`
- `OperationalState`
- `DishwasherMode`
- `DishwasherAlarm`

你可以把它理解成四块：

- 电源状态
- 运行状态机
- 模式选择
- 报警子系统

### 8.2 OperationalState 本身就是状态机

`OperationalStateCluster` 的四个主状态是：

- `STOPPED`
- `RUNNING`
- `PAUSED`
- `ERROR`

命令规则也很明确：

- `Start`：只有在 `STOPPED` 合法
- `Pause`：只有在 `RUNNING` 合法
- `Resume`：只有在 `PAUSED` 合法
- `Stop`：会进入 `STOPPED`

这意味着：

- 对同一个命令，是否成功不仅取决于参数，还取决于当前状态

这就是标准的状态机思路。

### 8.3 DishwasherMode 还会检查“运行中不能改模式”

`DishwasherModeCluster` 在 [dishwasher_mode.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/dishwasher_mode.py:89) 明确检查：

- 如果设备正在 `RUNNING`
- 则 `ChangeToMode` 返回失败

这说明 cluster 之间不是完全孤立的。

它们会通过设备引用互相感知，从而形成更复杂的约束逻辑。

### 8.4 它如何随时间推进

洗碗机在 [dishwasher.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dishwasher.py:116) 的 `on_time_tick()` 里，会：

1. 推进 `OperationalState` 倒计时
2. 更新 cycle progress
3. 更新 phase
4. 处理完成态

这比空调更明显地体现了“状态机 + 时间流程”的特征。

所以如果你问“这套设备模型有没有状态机”，洗碗机是最适合回答“有，但不是统一框架，而是局部实现”的例子。

## 9. 什么样的指令算“符合 Matter”并被接受

在 SimuHome 里，一个指令要被接受，通常要过这几关：

### 9.1 路由和对象存在

首先必须存在：

- `device_id`
- `endpoint_id`
- `cluster_id`
- `command_id` 或 `attribute_id`

否则会报：

- `DEVICE_NOT_FOUND`
- `ENDPOINT_NOT_FOUND`
- `CLUSTER_NOT_FOUND`
- `COMMAND_NOT_FOUND`
- `ATTRIBUTE_NOT_FOUND`

### 9.2 参数格式对

Cluster 基类会检查命令函数签名，如果参数名或类型形态不对，就会报 `COMMAND_EXECUTION_ERROR`。

比如：

- `OnOff.On` 不需要参数
- 你硬塞参数进去也可能失败
- `LevelControl.MoveToLevel` 则要求 `Level` 等特定字段

### 9.3 参数值对

很多 cluster 还会做值域约束。

例如：

- `Thermostat` 要求温度设定值在合法范围内，见 [thermostat.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/thermostat.py:35)
- `TemperatureControl` 会检查目标温度是否在 `MinTemperature ~ MaxTemperature` 范围内，见 [temperature_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/temperature_control.py:42)
- `RelativeHumidityMeasurement` 会检查值不能超过 100%，见 [relative_humidity_measurement.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/relative_humidity_measurement.py:81)

### 9.4 当前状态允许

即使命令名和参数都对，也可能因为当前状态不允许而失败。

例如：

- 空调没开机，不能调模式
- 洗碗机运行中，不能改模式
- `Pause` 不能在 `STOPPED` 态执行

### 9.5 只读属性不能直接写

很多 attribute 被标成 `readonly_attributes`，例如：

- `Thermostat.LocalTemperature`
- `RelativeHumidityMeasurement.MeasuredValue`
- `OnOff.OnOff`

这些值往往是：

- 由 cluster 命令维护
- 或由环境聚合器同步

不是随便写入就能改。

## 10. 它怎么判断“驱动成功”

### 10.1 系统判定标准

最终标准就是 `Result` 对象，定义在 [result.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/result.py:31)。

如果返回：

- `Result.ok(...)`

那这次驱动就算成功。

如果返回：

- `Result.fail(...)`

那就是失败，并且会带：

- `error_code`
- `error_message`
- `error_detail`

HTTP 层再把它映射成 200 / 400 / 404 / 409 等状态码。

### 10.2 成功的本质：设备状态被合法更新

所以这里的“驱动成功”本质上是：

- 该操作被模拟器认定为**合法**
- 并且导致了**预期的设备内部状态更新**

例如：

- `OnOff.On` 成功后，`OnOff` attribute 变成 `True`
- `DishwasherMode.ChangeToMode(3)` 成功后，`CurrentMode` 变成 `QUICK_WASH`
- `LevelControl.MoveToLevel(Level=200)` 成功后，会启动一段过渡状态

### 10.3 但这不保证 benchmark 任务成功

这里一定要再次强调：

- **驱动成功 != 用户目标成功**

举例：

- 空调开机成功、模式切换成功、设定成功
- 但如果设定值没有低于当前温度，温度聚合器就不会产生降温 effect

这时：

- 控制层是成功的
- 环境目标层可能是失败的

这也是论文为什么要单独评估：

- 是否命令正确
- 是否环境按预期变化
- 是否最终满足任务目标

## 11. 一句话总结这套设备模型

如果用一句话概括：

**SimuHome 里的设备不是一个统一 FSM，而是一组按 Matter 风格组织的设备对象；每个设备由多个 cluster 组成，cluster 负责属性、命令和约束，部分 cluster 再额外实现局部状态机和时间过程。**

再把你最关心的三个问题收束成最短答案：

- **是不是状态机**：整体不是统一状态机框架，但很多 cluster 和设备流程本身就是局部状态机。
- **怎么匹配 Matter**：通过 endpoint / cluster / attribute / command 这一套应用层抽象来匹配 Matter 语义。
- **什么叫驱动成功**：当命令或属性写入在对应设备/cluster 的语义和约束下被接受，并返回 `Result.ok(...)`，就算驱动成功；但这不等于环境目标或任务目标已经成功。

## 12. 建议你接下来重点看的文件

- [base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:1)
- [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:1)
- [result.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/result.py:1)
- [air_conditioner.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py:1)
- [dimmable_light.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dimmable_light.py:1)
- [level_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/level_control.py:1)
- [dishwasher.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dishwasher.py:1)
- [operational_state.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/operational_state.py:1)
- [dishwasher_mode.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/dishwasher_mode.py:1)
