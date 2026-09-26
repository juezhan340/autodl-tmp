# HomeEnv 统一语义接口与只读传感器设计讨论稿

> 日期：2026-09-23
> 性质：V1.2 接口方案讨论稿
> 状态：仅分析与设计，未修改代码
> 依据：通用语义接口交接文档、当前 HomeFlow Demo 源码、SimuHome 本地源码

> 本文承接前期房间、设备与工具关系讨论。旧接口中的 `get_room_state`、`get_device_state`、`get_device_capabilities` 等拆分过细，不作为当前首选实现；旧字段 `capabilities` 在本文统一改称 `actions`。本文供讨论，审定前不改代码。

## 先看结论

```text
传感器建模：作为 Device 的只读类别，拥有自己的 ID、room_id、state；没有可写 action
温湿度唯一真值：温湿度存于温度/湿度传感器 state，不再重复存一份 Room.environment
房间工具：inspect_room 返回该房间全部设备摘要；设备不多时不要求模型先猜 device_type
设备详情：inspect_device 返回一台设备的状态和 actions；只读传感器 actions=[]
执行入口：execute_action 是唯一写接口；未知动作、只读设备写入都拒绝且不改状态
字段筛选：本 Demo 暂不暴露 fields 参数；设备状态少，完整返回更简单也更一致
策略工具：observe_home / inspect_room / inspect_device / execute_action 共四个
环境内部：check_goal 负责 reward/done，不暴露给被测模型
回合结束：当前 HomeEnv 暴露 finish；它只是 runner 终止控制，不是 HA 家庭语义工具
本轮不接入：query_events、time_control、memory
```

建议的实体关系与调用链：

```text
Home
  └─ Room
      ├─ Device(kind=actuator, actions=[...])
      │    └─ state: 可观察 + 部分字段可由 action 改变
      └─ Device(kind=sensor, actions=[])
           └─ state: 只观察，不可写

observe_home()                         全屋概览、房间列表、房间级传感读数摘要
  -> inspect_room(room_id)             该房间设备清单与环境摘要，获取精确 device_id
      -> inspect_device(device_id)       设备完整状态和可执行 action schema
          -> execute_action(...)         唯一设备写入口
              -> inspect_device(...)     必要时由策略再次读取确认
  -> assistant final response            HomeEnv runner 结束回合
  -> check_goal(...)                    环境内部奖励/终止检查，不提供给被测策略
```

## 1. 与八工具交接文档的对齐方式

交接文档确认真机 MCP 已有 6 个可用语义接口：`observe_home`、`inspect_room`、`inspect_device`、`execute_action`、`check_goal`、`query_events`；另有 `time_control` 和 `memory` 两个尚未实现的规划接口。它同时明确列出 13 个只读传感器、12 个可控设备，说明“传感器作为只读实体”已经是那边的实体语义，不需要 HomeEnv 再发明 `temperature_sensor` 的写命令。

HomeFlow Demo 的目标是验证小模型在工具交互轨迹上的 SFT/GRPO 可行性，并为后续迁移到同一语义接口留路。因此优先复用动作和状态的词表、工具职责及返回外壳，不复制 HA/MCP 的运行时依赖、真实服务调用、并发等待和时间机制。

| 语义 | 真机接口交接 | HomeEnv Demo 的裁剪 |
|---|---|---|
| 全局观察 | `observe_home`：房间、环境摘要、时间、计数 | 保留房间列表和传感器环境摘要；不建虚拟时钟，时间字段可省略 |
| 局部空间观察 | `inspect_room`：环境值、设备清单 | 保留；返回房间环境摘要与全部设备摘要，不要求 type 参数 |
| 设备观察 | `inspect_device`：状态字段、动作及参数边界 | 保留；传感器返回状态和空动作列表，执行设备返回状态与 actions |
| 动作执行 | `execute_action`：唯一写口、执行后回读 | 保留单一写口；模拟器内确定性更新并返回 `state_after`，不等待真实设备 |
| 目标检查 | `check_goal`：conditions + keep | 保留为环境内部 verifier/reward API，不暴露给策略模型 |
| 事件查询 | `query_events` | 轨迹已有 tool event 审计，本轮不增加策略工具 |
| 时间控制 | 尚未实现 | 不做 tick、预约或等待 |
| 长期记忆 | 尚未实现 | 不做 |

这里的“统一”指可迁移的语义，不意味着 RL 模型直接面对完全相同的 transport：

```text
共享：tool name、参数语义、device_id/kind/state/actions、动作词表、错误分类
模拟器侧：内存状态转移、固定种子、快速 reset、程序化 goal/reward
真机侧：MCP transport、HA entity、可用性检查、服务调用、异步回读
```

因此同一条语义轨迹可以把模拟器执行器换成真机适配器，但“模拟器达到目标”不能被表述成“真机动作一定成功”。真机还有 unavailable、服务失败、回读超时等运行时状态，模型和评测必须按错误类别区分策略失误与环境故障。

HomeEnv 的 `AssistantTurn` 允许多个工具调用，但依赖关系必须遵守 ReAct 顺序：如果后一个调用的参数或选择依赖前一个调用结果，就在下一次 assistant turn 再发起，不能把 `inspect_room(room_id)` 与依赖其结果的 `inspect_device(device_id)` 放进同一 turn。互相独立且参数已知的读取才可以批量调用。

## 2. 传感器作为只读设备

### 2.1 数据归属

Room 是一级实体和设备归属边界；传感器是 Room 内的一种 Device。温度、湿度由相应传感器的状态字段持有：

```json
{
  "device_id": "sensor_001",
  "room_id": "room_001",
  "display_name": "卧室温湿度传感器",
  "kind": "sensor",
  "device_type": "environment_sensor",
  "state": {
    "temperature": 29.0,
    "humidity": 72.0
  },
  "actions": []
}
```

这比把 `temperature` / `humidity` 再存一份 `Room.environment` 更稳妥：同一观测只有一个权威值，不会发生房间读数与传感器读数不一致。Room 可以通过传感器清单为 `observe_home` / `inspect_room` 生成环境摘要；摘要是派生输出，不是另一份可写状态。单设备检查仍返回传感器自身完整读数，保持和真机 `inspect_device` 的语义一致。

多个传感器时，不应把它们的读数静默合并成一个温湿度值。最小 Demo 暂时限定每个房间至多一个温度源和一个湿度源；若用组合式温湿度传感器，一个设备可以同时提供两个字段。后续若加入多个读数源，再显式定义选源、聚合、单位与新鲜度规则。

### 2.2 只读边界

`kind=sensor` 必须有空 `actions`。`execute_action` 在统一校验层执行两道检查：目标设备存在且可用；action 存在于该设备自身的 actions。传感器无 action，因此无论模型猜 `set_temperature`、`turn_on` 还是任意其他动作，均返回 `UNSUPPORTED_ACTION`，状态保持不变。

```text
inspect_device(sensor_001)
  -> state={temperature: 29.0, humidity: 72.0}
  -> actions=[]

execute_action(sensor_001, "set_temperature", {"value": 20})
  -> ok=false, error.code="UNSUPPORTED_ACTION"
  -> state 不变
```

传感器观测任务因此能自然形成 RL 轨迹：模型从房间摘要或单设备检查读取值，再依据条件控制空调或除湿设备；传感器自身不进入可控动作空间。

## 3. 房间枚举应返回什么

在用户消息中通常只有“卧室灯”“厨房风扇”这样的自然语言，没有内部 `device_id`，也未必知道项目里的 `device_type` 枚举。把 `device_type` 作为 `inspect_room` 的必填过滤条件，会把 schema 知识错误地变成模型先验。因此建议 `inspect_room(room_id)` 返回该房间**全部设备的轻量摘要**：

```json
{
  "ok": true,
  "data": {
    "room": {
      "room_id": "room_001",
      "display_name": "卧室",
      "environment": {"temperature": 29.0, "humidity": 72.0},
      "devices": [
        {"device_id": "sensor_001", "name": "卧室温湿度传感器", "kind": "sensor", "device_type": "environment_sensor"},
        {"device_id": "device_001", "name": "卧室空调", "kind": "actuator", "device_type": "climate"},
        {"device_id": "device_002", "name": "卧室主灯", "kind": "actuator", "device_type": "light"}
      ]
    }
  },
  "error": null,
  "meta": {"elapsed_ms": 42, "clock": "none"}
}
```

这样外围模型只需理解 `kind` 是传感器还是执行设备，并从名称、设备类型与房间上下文匹配用户意图，无须预先知道内部 ID。之后 `inspect_device` 再返回该 ID 的状态及 action schema，避免把全屋所有设备的全部状态和参数范围塞入每次 observation。

当前 Demo 单场景设备规模只有 4～8 台，一次返回某房间的设备摘要不会形成显著上下文负担；后续若扩大到几十/上百设备，再考虑 `kind`/`device_type` 可选过滤、分页或搜索。此阶段不加这些入口，避免模型在发现设备前还要猜过滤枚举。

## 4. `fields` 参数要不要保留

现有 `query_device(device_id, fields)` 让模型从状态字段中挑选子集。对本 Demo 的灯、空调、开关、门锁和传感器而言，每台设备公开状态只有少数字段，完整返回通常更适合作为训练协议：

```text
省略 fields：减少动作参数组合和格式错误
完整返回 state：让策略看到一致的观测，不需要模型猜字段名
控制能力单独放 actions：状态键和值不会被误认为可写 command
```

因此建议 V1.2 的 `inspect_device(device_id)` 无 `fields` 参数，始终返回完整公开状态和完整动作 schema。`inspect_room(room_id)` 返回设备摘要与房间级环境摘要；`observe_home()` 返回全屋房间目录与同源环境摘要，但不返回逐设备状态、内部 device_id 或 action schema。

这不是认定 fields 永远无用。设备状态增长、token 成本成为实测瓶颈，或任务确实需要选择性观测时，再考虑可选 fields；不要在当前规模为了“未来可扩展”增加模型需要学习的接口分支。

## 5. 建议保留的四个策略工具

策略实际可见、与真机语义对齐的工具建议为四个：

```text
observe_home()                         全局房间与环境摘要
inspect_room(room_id)                  房间设备清单和该房间环境摘要
inspect_device(device_id)              完整状态 + 可执行动作及参数范围
execute_action(device_id, action, params)唯一写接口，返回 state_after
```

四个共享策略工具是 `observe_home`、`inspect_room`、`inspect_device`、`execute_action`。当前 HomeEnv 还把 `finish` 暴露为模型可调用的终止入口；V1.2 可为兼容现有训练协议暂时保留，但应标记为 HomeEnv episode-control，不属于 HA/MCP 的家庭语义工具。适配真机时，runner 将它映射为 assistant final response，不发送设备命令。`check_goal` 是环境侧 verifier，不计入策略工具数量，也不放进策略 schema。它读取隐藏任务定义、最终状态及 keep 条件并产生 reward/done，策略不能调用 verifier 探测隐藏答案。

与 V1.1 旧接口的映射：

```text
get_rooms()                    -> observe_home() 提供 rooms[]；不再单独占一个策略 turn
get_room_devices(room_id)      -> inspect_room(room_id).devices[]
get_room_state(...)            -> observe_home/inspect_room 的传感器派生摘要；需要设备级来源时 inspect_device(sensor_id)
get_device_state(device_id)    -> inspect_device(device_id).state
get_device_capabilities(id)    -> inspect_device(device_id).actions
execute_device_action(...)    -> execute_action(device_id, action, params)
finish(answer, reported_values)-> assistant final response + runner terminal event；不是 HA/MCP 工具
```

查询类任务的结构化报告值由 runner 记录为轨迹元数据并交给 verifier，不因此新增一个 HA 语义工具。

## 6. 统一返回、状态和动作契约

四个共享语义工具、环境侧 `check_goal` 及 HomeEnv 显式 `finish` 调用统一使用交接文档的结果外壳，便于 parser 和轨迹记录器复用。适配到 HA 时，`finish` 归一化为 assistant final response，不作为外部工具调用。成功和失败返回分开纵向展示：

成功返回：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {"elapsed_ms": 42, "clock": "none"}
}
```

上例中的 `{}` 是“此处放工具实际结果”的占位，`42` 只是示例耗时，不是固定值。契约语义如下：

```text
ok          调用是否成功
data        成功时的工具结果；不同工具内容不同，空对象仅用于展示外壳
error       成功时为 null；失败时包含 code / message / hint
elapsed_ms  本次调用实测耗时，单位毫秒；不是场景时间，也不参与默认 reward
clock       none / virtual / real 表示该工具结果关联的时间域
```

HomeEnv 当前不推进虚拟时间，因此 `clock` 固定为 `none`；`elapsed_ms` 由单调时钟测量，测试只检查其为非负数，不断言精确值。该字段留在 tool event 和评测日志；构造下一轮策略 observation 时建议剔除 `elapsed_ms`，避免硬件快慢成为策略捷径。若未来增加模拟时间推进，工具状态时间使用 `virtual`；接入 HA 后由适配器按交接契约标记 `real`。耗时是诊断元数据，不能让同一逻辑动作因机器负载不同而获得不同训练奖励。

失败返回：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "UNSUPPORTED_ACTION",
    "message": "sensor_001 does not support turn_on",
    "hint": "inspect_device 返回的 actions 是合法动作集合"
  },
  "meta": {"elapsed_ms": 42, "clock": "none"}
}
```

失败示例里的 `42` 同样只是示例值；实际 `elapsed_ms` 由调用测得。

建议保留交接文档的规范动作名称，不继续用 `set_power` / `set_mode` 作第二套训练词表：

```text
light / switch: turn_on, turn_off, toggle
climate:        turn_on, turn_off, toggle, set_mode(mode), set_temperature(value)
fan:            turn_on, turn_off, toggle, set_percentage(value)
sensor:         无动作
```

HomeFlow 初版内部仍可从这些语义动作映射到现有状态字段：`turn_off` 写 `power=off`，`set_temperature` 写目标温度字段，传感器没有映射。未来 HA 适配器把相同语义映射到服务调用。动作参数范围应由 `inspect_device.actions` 提供并由执行器重复校验；不能仅依赖模型读过 schema。动作名和参数结构沿用交接文档中的契约，例如：

```json
{
  "device_id": "device_001",
  "actions": [
    {
      "action": "set_temperature",
      "params": {
        "value": {"type": "number", "minimum": 7, "maximum": 32, "step": 0.5}
      }
    },
    {
      "action": "set_mode",
      "params": {
        "mode": {"type": "string", "enum": ["off", "cool", "heat"]}
      }
    }
  ]
}
```

模型执行时提交 `{"device_id":"device_001","action":"set_temperature","params":{"value":24}}`。这里“六个字段”指设备状态字段 `on/mode/target/level/position/current`，不是动作参数种类；动作参数由具体 action 决定，并须通过该设备的 `actions` schema 校验。

错误结果至少区分：

```text
UNKNOWN_ROOM / UNKNOWN_DEVICE / UNSUPPORTED_ACTION / BAD_REQUEST
策略或协议错误：计入轨迹质量；若场景和工具 schema 本身有效，可按实验定义给负奖励

DEVICE_UNAVAILABLE / BACKEND_UNREACHABLE
执行环境错误：标记 episode/system failure，不与策略失误混算；可按实验规则重试或剔除该回合

SERVICE_ERROR
结合 message / hint / 后端日志归因：后端或设备服务异常按执行环境错误处理；有效设备收到不支持的服务参数时，按策略/schema 或场景定义错误处理。无法归因时标记为未决故障，不直接给策略负奖励。
```

错误码本身不会自动产生更丰富的强化学习梯度。它们提供“为什么失败”的可归因反馈；只有奖励函数把可归因的策略错误映射为明确奖励时，才会形成更细的学习信号。环境故障应从策略回报中隔离，否则模型可能学到“遇到后端掉线也要为此受罚”的错误关联。

纯模拟器中不会自然遇到 HA 掉线，但要保留错误契约形状，以便策略、数据 parser 和测评统计迁移。不要通过伪造随机故障来假装完成真机鲁棒性验证。

## 7. 一个完整例子：按传感器读数决定是否调空调

初始提示只给用户任务和工具定义，不给内部设备 ID 或完整库存：

```text
用户：卧室超过28度时，把空调目标温度设为24度。
```

调用轨迹：

```text
Turn 1  observe_home()
        -> rooms=[{room_id:"room_001", display_name:"卧室", env:{temperature:29.0, humidity:72.0}}]
        -> 房间读数是 sensor state 的派生摘要，不是第二份状态

Turn 2  inspect_room("room_001")
        -> [sensor_001: sensor/environment_sensor,
            device_001: actuator/climate,
            device_002: actuator/light]

Turn 3  inspect_device("sensor_001")
        -> kind=sensor, state={temperature:29.0, humidity:72.0}, actions=[]

Turn 4  inspect_device("device_001")
        -> kind=actuator, state={on:true, mode:"cool", target:26.0},
           actions=[turn_on, turn_off, toggle, set_mode, set_temperature(7..32, step=0.5)]

Turn 5  execute_action("device_001", "set_temperature", {value:24.0})
        -> state_after.target=24.0, verified=true

Turn 6  finish("已将卧室空调目标温度设为24度。")
        -> runner 结束 episode；环境内部 check_goal 检查目标条件与 keep 条件
```

若温度为 26°C，则正确策略不执行控制，只报告条件未触发。由于全屋摘要已包含温度，这类条件控制任务不测“是否主动寻找传感器”；若需测设备发现能力，应另设任务要求模型从 `inspect_room` 返回的设备清单中区分 sensor 与 actuator，并检查相关设备状态。Verifier 检查最终目标、必要状态保持及答复事实，不强求每条任务都产生设备写操作。

## 8. Room、Device、状态和 action 规格

### Room

职责：
  作为存在性、命名及设备归属的一级实体；提供房间内设备索引。

输入：
  `room_id`、`display_name`、设备 ID 集合。

输出：
  `observe_home.rooms[]` 的简要信息和 `inspect_room` 的设备摘要。

读取：
  发现工具、episode verifier、场景生成器。

写入：
  场景 reset 时建立；当前 Demo episode 内不改变房间及设备归属。

不负责：
  不复制保存传感器读数，不模拟户型、面积、邻接或环境传播。

### Device

职责：
  通过 `device_id` 唯一标识设备，通过 `room_id` 表达位置，通过 `kind` 区分传感源和执行设备。

字段：

```text
device_id       当前 Home 内唯一；模型只能从工具结果获得
room_id         所属 Room 外键
name            面向用户的自然名称
kind            sensor | actuator
device_type     temperature_sensor | humidity_sensor | environment_sensor | climate | light | switch | lock | fan
state           完整公开状态；传感器读数存于其 state，房间环境摘要由传感器状态派生
actions         允许的规范 action；sensor 必须为空数组
```

动作 schema 的唯一权威来源为 `actions`，它既供 `inspect_device` 展示，也由 `execute_action` 校验。交接文档明确了执行设备的六字段语义和房间环境指标，但当前交接摘要未列出 HA 传感器实体到模拟器 `state` 键的逐项映射。V1.2 实施前需从 MCP contract / 设计文档核定温度、湿度、亮度、PM10 的键名与单位，再冻结测试 fixture，不能仅凭示例猜字段。

写入：
  执行设备状态只能由 `execute_action` 经 `actions` schema 校验后修改；sensor 的任何字段都不可被模型写入。

### Action schema

职责：
  以单一数据源提供 action 名称、参数类型、范围、步长和枚举；同时用于 `inspect_device` 展示和 `execute_action` 校验。

实现边界：
  不在 prompt、场景模板和执行器里各维护一份 command 白名单。传感器 `actions=[]`；不支持动作返回 `UNSUPPORTED_ACTION` 且无状态副作用。

## 9. Observation 与 RL 的边界

`observe_home` 相当于统一 episode 起点观察。它返回房间目录与环境读数摘要，但不给设备 ID、执行设备完整状态和动作 schema。这样模型可以判断任务涉及哪个房间及当前环境，却仍需通过 `inspect_room` 发现设备，再通过 `inspect_device` 获得状态与 `actions` schema。

建议 observation 分层：

```text
observe_home
  房间 ID、display_name、每房间已知传感器指标摘要、设备总数；不含设备 ID

inspect_room(room_id)
  房间环境摘要及全部设备的 ID、名称、kind、device_type

inspect_device(device_id)
  单设备完整状态与 actions

execute_action(...)
  执行结果、state_after、verified 或确定性模拟器回执
```

传感器摘要会让基于温湿度阈值的任务直接使用全局观察，不强制调用 `inspect_device(sensor_id)`。这是有意的任务边界：本 Demo 训练目标优先验证策略能否将统一 observation、设备发现、动作 schema 查询和规范动作串成有效轨迹，不把“每次都调用传感器工具”当作奖励目标。后续可另建主动感知任务集，并在该 split 中限制全局摘要字段；不要在同一个任务分布中暗中切换 observation 规则。

`check_goal` 的 `conditions` 和 `keep` 只在环境/训练器侧使用：

```text
strategy output + tool results -> trajectory
trajectory + hidden conditions/keep -> verifier -> reward, completion, done
```

奖励规则应分开度量：目标满足、无关状态保持、合法动作、读取必要观测、策略调用成本。读取动作可作为轨迹质量或轻微成本信号，避免让 RL 学会盲目多查；不能把合法查询本身当作和设备状态修改同权的 reward。

## 10. 本轮先不做的东西

```text
不接 HA/MCP、不依赖真机，不运行外部服务
不实现时间推进、预约、长期记忆和事件查询工具
不实现 Matter Endpoint / Cluster / Attribute
不做多传感器融合、漂移、故障概率和连续热湿传播
不加 fields 筛选、分页、device_type 查询参数
不在策略可见工具里暴露 check_goal 或隐藏目标
不复制八个工具的全部后端、异步回读与错误恢复机制
```

## 11. V1.2 最小交付与验收建议

### 数据结构

```text
Scenario.home.rooms[] 为一级房间集合，含 room_id / display_name
Scenario.home.devices[] 为唯一设备表；每个 Device.room_id 外键指向 Room
inspect_room 的 devices[] 根据 room_id 派生，不在输入数据中重复维护
传感器用 kind=sensor + actions=[]，状态保存 temperature/humidity
执行设备用 kind=actuator + actions schema
ID 不含房间名称，不要求模型从自然语言猜 ID
```

### 工具闭环

```text
observe_home -> inspect_room -> inspect_device -> execute_action -> assistant final response
check_goal 由环境内部调用，不进入模型工具列表
```

### 必测情形

```text
房间名称解析失败 / room_id 不存在 -> UNKNOWN_ROOM，不泄漏设备
设备不在该房间 / device_id 不存在 -> UNKNOWN_DEVICE
同房间多个相似设备 -> inspect_room 明确列出所有摘要
sensor action=[] -> 任意 execute_action 都是 UNSUPPORTED_ACTION，状态不变
设备 action 不支持 / 参数越界 -> 明确拒绝，不产生部分状态写入
条件成立和不成立两种轨迹 -> verifier 分别判动作成功与正确不动作
未 inspect 的 ID / action -> 按策略协议违规处理或拒绝执行
每条 transition 对应一次 assistant turn，工具结果只在后续决策中使用
```

### 统一语义兼容测试

```text
同一个小型测试轨迹可在 Fake/HomeEnv backend 和 HA adapter 上完成序列化/反序列化
核心检查 tool name、参数、结果 envelope、状态字段、动作名与错误 code 一致
HA 侧服务映射与异常不纳入 HomeEnv 单元测试；由真机 adapter 测试负责
```

这里的目标是迁移语义和训练数据，不承诺策略在真机上零迁移直接成功。真机还存在传感器 unavailable、命令回读延迟、用户状态外部变化等模拟器没有覆盖的分布差异。

## 12. 文件对应与版本关系

本讨论稿若审定，建议以它替代前版“房间环境量单独存放、状态与动作 schema 拆分为独立工具、七个策略入口”的设计。正式实施时再同步更新版本计划及 `homeflow_demo` 代码文档；本轮未改代码。

初步对应：

```text
homeflow_demo/env/models.py          Home / Room / Device / Sensor / Scenario 数据结构
homeflow_demo/env/schema.py          Home、Room、设备 kind、只读和 action 参数校验
homeflow_demo/env/tool_schema.py     统一工具名、参数及返回语义
homeflow_demo/env/home_env.py        discovery ledger、observe/inspect/execute 事件和 turn transition
homeflow_demo/env/state_engine.py    规范 action 到设备状态字段的确定性映射
homeflow_demo/env/predicates.py      conditions + keep 的隐藏目标检查
homeflow_demo/data/scenario_generator.py 房间、传感器与执行设备组合及条件任务
```

前版 7 工具方案不应继续与本文并列作为实施规格；本文审定后，以本文和新的整体实验架构交付方案作为后续实现依据。
