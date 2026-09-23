# SimuHome 完整案例贯穿梳理

## 0. 为什么要写这份文档

前两份文档已经把整体机制和设备建模讲清楚了，但如果只看“结构”和“规则”，还是会有一种抽象感。  
真正要理解 SimuHome，最有效的方式往往不是再多看几个类名，而是**顺着一个完整案例，把命令、设备状态、环境变量、时间推进、传感器回写这一整条链路走一遍**。

这份文档就做这一件事。

我会先用一个主案例贯穿：

- **案例 A：把客厅空调打开并设成制冷，房间温度如何逐 tick 下降**

然后再补一个短案例，说明“设备内部也可能有时间过程”：

- **案例 B：调光灯不是瞬时变亮，而是亮度在多个 tick 中逐步变化**

## 1. 主案例：空调制冷让房间温度下降

### 1.1 我们到底要模拟什么

假设一个房间当前状态是：

- 房间：`living_room`
- 当前温度：`28.00°C`
- 房间基线温度：`28.00°C`
- 房间里有一个空调：`living_room_ac_1`

用户或 agent 的目标是：

- 打开空调
- 设置成制冷模式
- 把制冷目标温度设为 `24.00°C`
- 设置一个非零风速

论文里对这种任务的预期不是“命令发出后温度立刻变 24°C”，而是：

```text
as an air conditioner runs, the room temperature gradually decreases toward the target
temperature, and the simulator must reflect these changes continuously.
```

也就是说，真正要观察的是这条链：

1. agent 发出结构化命令
2. 设备接收命令并更新内部状态
3. 聚合器识别设备已经进入工作状态
4. 温度 effect 在后续每个 tick 持续生效
5. 房间温度逐步下降
6. 设备上的 `LocalTemperature` 传感器也跟着变

## 2. 第一步：agent 发出的不是自然语言，而是结构化控制命令

### 2.1 API 层的入口长什么样

从 [routes.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/api/routes.py:164) 可以看到，设备控制对外分成两类：

- `execute_command`
- `write_attribute`

代码如下：

```python
@router.post("/devices/{device_id}/commands")
def execute_command(device_id: str, req: ExecuteCommandRequest):
    resp = _queue_api(
        "execute_command",
        device_id=device_id,
        endpoint_id=req.endpoint_id,
        cluster_id=req.cluster_id,
        command_id=req.command_id,
        args=req.args or {},
    )
    return _result_or_raise(resp)


@router.post("/devices/{device_id}/attributes/write")
def write_attribute(device_id: str, req: WriteAttributeRequest):
    resp = _queue_api(
        "write_attribute",
        device_id=device_id,
        endpoint_id=req.endpoint_id,
        cluster_id=req.cluster_id,
        attribute_id=req.attribute_id,
        value=req.value,
    )
    return _result_or_raise(resp)
```

这说明在 SimuHome 里，agent 真正发出去的不是一句“把空调调到 24 度”，而是更底层的结构化操作。

### 2.2 对应到空调，这组控制通常会拆成四步

在这个实现下，一个合理的空调制冷序列大概是：

1. 开机
2. 设置 `SystemMode = COOL`
3. 设置 `OccupiedCoolingSetpoint = 2400`
4. 设置 `FanControl.PercentSetting = 50` 或其他非零值

它们分别可能长成这样：

```json
{
  "device_id": "living_room_ac_1",
  "endpoint_id": 1,
  "cluster_id": "OnOff",
  "command_id": "On",
  "args": {}
}
```

```json
{
  "device_id": "living_room_ac_1",
  "endpoint_id": 1,
  "cluster_id": "Thermostat",
  "attribute_id": "SystemMode",
  "value": 3
}
```

```json
{
  "device_id": "living_room_ac_1",
  "endpoint_id": 1,
  "cluster_id": "Thermostat",
  "attribute_id": "OccupiedCoolingSetpoint",
  "value": 2400
}
```

```json
{
  "device_id": "living_room_ac_1",
  "endpoint_id": 1,
  "cluster_id": "FanControl",
  "attribute_id": "PercentSetting",
  "value": 50
}
```

从这里就能直接看出，这个系统里的 Matter 不是“底层报文协议”，而是：

- endpoint
- cluster
- command
- attribute

这一整套**应用层能力建模方式**。

## 3. 第二步：这些命令如何进入模拟主循环

### 3.1 API 请求不会直接改状态，而是进队列

在 `Home` 里，外部控制请求先进入 `api_queue`，然后由模拟主循环统一处理。

主循环见 [home.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/home.py:170)：

```python
def __simulation_loop(self):
    try:
        while self.is_running:
            tick_start = time.perf_counter()

            self.__process_time_aware_devices()
            self.__process_aggregators()
            self.__process_schedular_queue()
            self.__process_api_queue()
            ...
            self.current_tick += 1
```

很重要的一点是：**API 命令不是优先于环境更新执行，而是在这个 tick 的后半段统一处理。**

这意味着：

- 先推进已有设备的时间状态
- 再根据已有设备状态更新环境
- 然后才处理新命令

所以一个刚刚发进来的空调命令，通常会在该 tick 的 API 阶段生效，并在后续 tick 真正开始影响环境。

## 4. 第三步：空调这个设备本身是怎么建模的

### 4.1 空调不是一个“大对象”，而是多个 Matter 风格 cluster 的组合

空调定义在 [air_conditioner.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py:9)：

```python
class AirConditioner(Device):

    def __init__(self, device_id):
        super().__init__(
            device_id,
            "air_conditioner",
            BasicInformationCluster(
                vendor_name="LG Electronics",
                vendor_id=1,
                product_name="Air Conditioner",
                product_id=1,
            ),
        )

        self.add_cluster(1, OnOffCluster())
        self.add_cluster(1, ThermostatCluster())
        self.add_cluster(1, FanControlCluster())
```

这个结构非常关键。它说明：

- 开关能力归 `OnOffCluster`
- 温控能力归 `ThermostatCluster`
- 风速能力归 `FanControlCluster`

也就是说，空调不是“一个自定义 if-else 大类”，而是按 Matter 风格拆成了多个可组合能力块。

### 4.2 设备层还会叠加“操作依赖”

空调类额外实现了一个很重要的约束：**没开机之前，不能调温控和风速**。

代码如下：

```python
def _check_power_dependency(self) -> Result:
    power_status = self.get_attribute(1, "OnOff", "OnOff")
    if not power_status:
        return Result.fail(
            ErrorCode.DEPENDENCY_VIOLATION,
            "Power dependency violation",
            "Cannot perform operation when power is OFF. Turn on the air conditioner first.",
        )
    return Result.ok()
```

对属性写入的约束：

```python
def _check_power_dependency_for_attribute(
    self, cluster_id: str, attribute_id: str
) -> Result:
    power_dependent_attributes = {
        "Thermostat": [
            "OccupiedCoolingSetpoint",
            "OccupiedHeatingSetpoint",
            "SystemMode",
        ],
        "FanControl": ["FanMode", "PercentSetting"],
    }

    if (
        cluster_id in power_dependent_attributes
        and attribute_id in power_dependent_attributes[cluster_id]
    ):
        return self._check_power_dependency()

    return Result.ok()
```

因此，如果 agent 直接先写：

- `Thermostat.SystemMode = COOL`

但空调还没开机，这次操作在设备层面就会失败。

这正是论文里说的：

```text
operating an air conditioner may require
multiple steps in a specific order, such as powering on the device before adjusting its temperature
```

## 5. 第四步：cluster 层是怎么判定“这次驱动成功”的

### 5.1 成功的第一层是 cluster 级合法执行

`Cluster` 基类在 [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:6) 里定义了统一执行逻辑：

```python
def execute_command(self, command_id: str, **args) -> Result:
    if command_id not in self.commands:
        return Result.fail(
            error_code=ErrorCode.COMMAND_NOT_FOUND,
            error_message=f"Command '{command_id}' not found in cluster '{self.cluster_id}'",
            error_detail=f"Available commands: {available_commands}",
        )

    try:
        command_func = self.commands[command_id]
        result = command_func(**args)

        if isinstance(result, Result):
            return result
        ...
```

而属性写入逻辑是：

```python
def write_attribute(self, attribute_id: str, value: Any) -> Result:
    if attribute_id not in self.attributes:
        return ResultBuilder.attribute_not_found(
            attribute_id=attribute_id, cluster_id=self.cluster_id
        )

    if attribute_id in self.readonly_attributes:
        return Result.fail(
            ErrorCode.READ_ONLY,
            f"Attribute '{attribute_id}' is read-only",
            f"Attribute '{attribute_id}' in cluster '{self.cluster_id}' is managed by environment aggregator",
        )

    old_value = self.attributes.get(attribute_id)
    self.attributes[attribute_id] = value
    return Result.ok(
        {
            "cluster": self.cluster_id,
            "attribute": attribute_id,
            "old_value": old_value,
            "new_value": value,
        }
    )
```

从这里能得出一个很重要的结论：

**在 SimuHome 里，“驱动成功”首先是语义成功。**

也就是：

- endpoint 存在
- cluster 存在
- command 或 attribute 存在
- 参数格式对
- 当前状态允许
- 约束校验通过
- 返回 `Result.ok(...)`

这时，这次控制就算“成功驱动了设备”。

### 5.2 成功驱动不等于立刻达到用户目标

这是理解 SimuHome 的关键。

比如空调这里，四步控制都可能成功：

1. `OnOff.On`
2. `SystemMode = COOL`
3. `OccupiedCoolingSetpoint = 2400`
4. `PercentSetting = 50`

这表示：

- 设备内部状态被合法更新了

但它不表示：

- 房间温度此刻已经到 24°C

真正的环境变化要等温度聚合器在后续 tick 中慢慢计算。

## 6. 第五步：温控和风速 cluster 具体把哪些状态改掉了

### 6.1 开机命令改变 `OnOff`

`OnOffCluster` 在 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:14) 中：

```python
self.attributes = {
    "OnOff": False,
}

self.commands = {"Off": self._off, "On": self._on, "Toggle": self._toggle}
```

执行 `On` 时：

```python
def _on(self) -> Result:
    was_off = not self.attributes["OnOff"]
    self.attributes["OnOff"] = True
    ...
    return Result.ok(
        {
            "cluster": self.cluster_id,
            "command": "On",
            "result": "Device turned on",
        }
    )
```

所以开机成功后，空调最基础的运行前提才成立。

### 6.2 温控属性改变 `SystemMode` 和 setpoint

`ThermostatCluster` 在 [thermostat.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/thermostat.py:17) 里：

```python
self.attributes = {
    "LocalTemperature": 2500,
    "OccupiedCoolingSetpoint": 2000,
    "OccupiedHeatingSetpoint": 2800,
    "ControlSequenceOfOperation": ControlSequenceOfOperationEnum.COOLING_AND_HEATING,
    "SystemMode": SystemMode.OFF,
}
```

它对温度设定值做约束：

```python
if attribute_id in ("OccupiedHeatingSetpoint", "OccupiedCoolingSetpoint"):
    if not isinstance(value, int):
        return Result.fail(...)

    if not (700 <= value <= 3200):
        return Result.fail(...)
```

并且还检查 cooling/heating deadband。

所以：

- `SystemMode = 3`
- `OccupiedCoolingSetpoint = 2400`

这两步成功之后，空调就在设备内部进入“允许制冷”的控制状态。

### 6.3 风速属性改变 `PercentCurrent`

`FanControlCluster` 在 [fan_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/fan_control.py:19) 里：

```python
self.attributes = {
    "FanMode": FanMode.OFF,
    "FanModeSequence": fan_mode_sequence,
    "PercentSetting": 0,
    "PercentCurrent": 0,
}
```

当你写 `PercentSetting` 时：

```python
def _update_percent_setting(self, new_percent: int) -> Result:
    if new_percent < 0 or new_percent > 100:
        return Result.fail(ErrorCode.VALIDATION_ERROR, "Invalid percentage range")

    self.attributes["PercentSetting"] = new_percent
    self.attributes["PercentCurrent"] = new_percent
    ...
```

所以如果你把风速设成 `50`，那么聚合器后面看到的就是：

- `PercentCurrent = 50`

这会直接影响环境更新速度。

## 7. 第六步：为什么空调现在“算开始工作了”

温度聚合器在 [temperature.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/aggregators/temperature.py:75) 左右，会重新读取空调状态：

```python
is_operating = device.get_attribute(1, "OnOff", "OnOff")
if is_operating:
    fan_percent_value = device.get_attribute(
        1, "FanControl", "PercentCurrent"
    )
    fan_percent = (
        50
        if fan_percent_value is None
        else max(0, min(100, fan_percent_value))
    )
    fan_intensity = fan_percent / 100.0
```

然后再读取温控状态：

```python
system_mode = device.get_attribute(
    thermostat_endpoint, "Thermostat", "SystemMode"
)
cooling_setpoint = device.get_attribute(
    thermostat_endpoint, "Thermostat", "OccupiedCoolingSetpoint"
)
```

只有当这些条件都满足时，空调才会被视为“对环境有有效作用”：

- 电源开
- `SystemMode == COOL`
- 当前房间温度高于 `OccupiedCoolingSetpoint`
- 风速非零时效果更强

所以这个系统不是“空调开机就立刻降温”，而是要满足一整组状态条件。

## 8. 第七步：房间温度在后续 tick 中如何真正下降

### 8.1 每个 tick 先读取 effect

制冷逻辑核心代码：

```python
if system_mode == 0x03:
    if self.current_value > cooling_setpoint:
        temp_diff = (
            self.current_value - cooling_setpoint
        ) / 100.0
        cooling_rate_per_second_c = min(0.0005, temp_diff * 1.0) * fan_intensity
        self.continuous_effects[device_id] = (
            -(cooling_rate_per_second_c * 100.0) * self.tick_interval
        )
    else:
        self.continuous_effects.pop(device_id, None)
```

把它翻译成人话就是：

- 当前温度越高于目标温度，降温动力越强
- 风速越大，降温更快
- 但这个速度有上限
- 一旦当前温度已经不高于目标值，空调 effect 就停掉

### 8.2 然后 effect 会真正叠加到房间温度上

每个 tick 的环境更新：

```python
total_effect = sum(self.continuous_effects.values())
self.current_value += total_effect

delta = self.baseline_value - self.current_value
restoration_rate_per_second = 0.0002
self.current_value += delta * restoration_rate_per_second * self.tick_interval
```

所以房间温度的变化不是一步跳到 24°C，而是：

1. 先减去空调的降温 effect
2. 再加上一点向 baseline 回归的“自然回弹”

因此，温度轨迹是一个逐步逼近过程。

### 8.3 如果两个空调同时工作会怎样

论文里说：

```text
This influence is additive
```

代码里正是通过：

```python
total_effect = sum(self.continuous_effects.values())
```

来实现的。

所以如果两个空调都在这个房间制冷：

- 两个设备都会在 `continuous_effects` 里各占一项
- `sum(...)` 后降温更快

这就是论文所说“两个空调高风速会比一个更快”在代码中的直接落地。

## 9. 第八步：为什么传感器读数也会跟着变

论文里还有一句很关键：

```text
Sensor attributes on devices, such as a temperature
sensor on an air conditioner, are also updated to reflect current environmental variables at each tick.
```

代码里对应的实现是：

```python
def sync_device_sensor_from_env(self, device):
    thermostat_endpoint = self._get_thermostat_endpoint(device)
    if thermostat_endpoint is None:
        return
    thermostat = device.endpoints[thermostat_endpoint].get("Thermostat")
    if thermostat:
        thermostat.attributes["LocalTemperature"] = int(self.current_value)
```

所以在这个案例里，随着房间温度逐 tick 下降：

- `living_room` 的房间级 `temperature` 在变
- 空调设备内部 `Thermostat.LocalTemperature` 也会被同步更新

这就让 agent 后续再查询设备属性时，看到的是新的环境温度，而不是旧值。

## 10. 这个案例里，“成功”一共分几层

这是理解 SimuHome 最重要的地方之一。

### 10.1 第一层：控制成功

例如：

- `OnOff.On` 返回 `Result.ok`
- `SystemMode = COOL` 返回 `Result.ok`
- `OccupiedCoolingSetpoint = 2400` 返回 `Result.ok`
- `PercentSetting = 50` 返回 `Result.ok`

这表示：  
**控制命令在设备语义上被接受了。**

### 10.2 第二层：设备进入工作状态

即：

- 电源开了
- 模式对了
- setpoint 合理
- 风速合理

这表示：  
**设备现在处于会影响环境的状态。**

### 10.3 第三层：环境确实开始变化

即：

- `TemperatureAggregator` 计算出负的 cooling effect
- 房间温度开始下降

这表示：  
**控制命令已经从设备层传导到了环境层。**

### 10.4 第四层：用户目标达成

例如：

- 房间温度最终下降到了足够低
- 或至少朝目标方向显著变化

这表示：  
**任务意义上的成功。**

SimuHome 的厉害之处就在于，它把这四层拆开了，而不是把它们混成一个“按钮按了就算成功”的黑箱。

## 11. 短案例：为什么调光灯能表现出连续变化

上面的空调案例主要说明“设备控制如何影响环境”。  
这里再补一个短案例，说明“**设备本身也可能按 tick 演化**”。

### 11.1 调光灯设备结构

调光灯定义在 [dimmable_light.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/dimmable_light.py:8)：

```python
self.add_cluster(1, OnOffCluster(features=OnOffCluster.FEATURE_LT))

level_cluster = LevelControlCluster(time_aware=True)
level_cluster.set_device_reference(self)
self.add_cluster(1, level_cluster)
```

这里最关键的是：

- `LevelControlCluster(time_aware=True)`

这表示亮度控制不是纯静态属性写入。

### 11.2 亮度变化会进入一个过渡状态

`MoveToLevel` 命令如果带时间，会启动 transition，而不是立刻跳到目标值：

```python
if resolved_time == 0 or not self._time_aware:
    self.attributes["CurrentLevel"] = level
    self.attributes["RemainingTime"] = 0
else:
    self._start_transition(level, resolved_time, with_onoff=with_onoff)
```

transition 的内部状态：

```python
self._transition_state = {
    "active": True,
    "start_level": current_level,
    "target_level": target_level,
    "total_time": transition_time,
    "ticks_required": ticks_required,
    "processed_ticks": 0,
    "delta_per_tick": delta_per_tick,
    "tick_interval": tick_interval,
    "with_onoff": with_onoff,
}
```

### 11.3 每个 tick 真正把亮度往前推一点

```python
def _handle_time_tick(self):
    delta = self._get_tick_interval()
    self.update(delta)
```

最终在 `_process_transition()` 里逐步更新：

```python
new_level = state["start_level"] + state["delta_per_tick"] * state["processed_ticks"]
self.attributes["CurrentLevel"] = int(round(new_level))
```

### 11.4 这又怎样影响房间光照

光照聚合器读的是：

```python
state = (
    device.get_attribute(1, "OnOff", "OnOff"),
    device.get_attribute(1, "LevelControl", "CurrentLevel"),
)
```

并且把亮度换成贡献：

```python
level = device.get_attribute(1, "LevelControl", "CurrentLevel") or 0
brightness_percent = level / 254.0
return brightness_percent * 500
```

所以这个短案例说明的是：

- 设备内部亮度在多个 tick 中逐步变化
- 光照聚合器每个 tick 看到的 `CurrentLevel` 都可能不同
- 因此房间光照也会表现为连续变化

这里的“连续性”不是光照聚合器自己做出来的，而是由设备内部 time-aware cluster 提供的。

## 12. 这份案例给出的最核心认识

如果你只从这份案例里带走一个认识，那应该是：

**SimuHome 的模拟不是“命令 -> 直接给出结果”，而是“命令 -> 改设备状态 -> 设备状态被聚合器解释 -> 环境逐 tick 演化 -> 传感器回写 -> 后续再被 agent 观测”。**

把这个链路记住，你就能一下子看懂为什么它和很多“静态 benchmark”不一样：

- 它不是只检查命令对没对
- 它还检查命令是否让设备进入正确状态
- 还检查环境是否在后续时间里按预期变化

也正因为这样，它才适合评估：

- agent 是否理解设备依赖
- agent 是否理解环境反馈
- agent 是否理解时间过程

## 13. 如果你接下来还想继续看什么

这份文档已经把“一个完整案例的核心链路”串起来了。  
如果还要继续往下深挖，最值得做的有两个方向：

1. 再写一个“**workflow 调度案例**”
   例如：洗碗机结束时打开厨房灯，看看绝对时间、due_tick、快进和执行失败语义是怎么串起来的。

2. 再写一个“**反例案例**”
   例如：先写 `SystemMode = COOL` 但没开机，看看为什么它在设备层面就失败，从而更清楚地展示依赖约束的作用。
