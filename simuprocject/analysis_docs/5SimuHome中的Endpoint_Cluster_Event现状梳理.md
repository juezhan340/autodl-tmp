# SimuHome 中的 Endpoint / Cluster / Attribute / Command / Event 实现梳理

这份文档不再按“一个问题一个回答”的方式组织，而是直接从代码结构出发，顺着实现往下讲：

```text
设备在代码里是怎么组织的
-> endpoint 在哪里出现
-> cluster 在哪里落地
-> attribute 和 command 在 cluster 里如何实现
-> event 这一层到底有没有
-> heat_pump 为什么是最典型的多 endpoint 例子
```

核心判断先放在最前面：

```text
SimuHome 明显借用了 Matter 风格的
device -> endpoint -> cluster -> attribute/command
这一套骨架，

但在当前代码里，
真正完整落地的是 endpoint / cluster / attribute / command，
event 这一层基本没有被实现成设备语义层的一等公民接口。
```

---

## 1. 整个设备骨架在代码里是怎么立起来的

要理解 SimuHome 里的 endpoint、cluster、attribute、command，最重要的入口不是某个具体设备，而是设备基类 [base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:1)。

这个基类里最关键的一行是：

```python
self.endpoints: dict[int, dict[str, Cluster]] = {0: {}}
```

这句话几乎已经把整个设备骨架说完了：

```text
一个 Device
  -> 有若干 endpoint_id
      -> 每个 endpoint_id 下面挂一个 { cluster_id -> cluster_instance } 映射
```

也就是说，设备在代码里并不是被建成：

```text
device.power
device.temperature
device.fan_speed
```

这样一组直接平铺的字段，而是被建成：

```text
device
  -> endpoints
      -> cluster objects
```

这和 Matter 风格的数据模型是一致的。

另外还有一个非常容易漏掉的点：

```text
每个设备一创建出来，就默认带有 endpoint 0
```

而 `endpoint 0` 里默认挂的是 `BasicInformationCluster`。  
这部分不是各个设备文件里自己显式写出来的，而是在 `Device.__init__()` 里直接放进去的。

所以如果你只看各个具体设备文件，很容易少算一层。  
从完整实现看，每类设备都至少有：

```text
endpoint 0
  -> BasicInformationCluster
```

---

## 2. endpoint 在当前项目里是怎么被用起来的

从实现上看，endpoint 在 SimuHome 里是真实存在的，不只是概念上的保留位。

按当前代码统计，设备层一共定义了 `17` 类设备。  
如果把默认的 `endpoint 0` 也算上，当前出现过的唯一 endpoint id 是：

```text
0, 1, 2, 3, 4
```

也就是说，当前代码里总共出现了 `5` 个不同编号的 endpoint。

不过，从设备分布上看，endpoint 的使用是很不均匀的。

大多数设备其实都比较简单，结构接近：

```text
endpoint 0 -> 基础信息
endpoint 1 -> 主功能面
```

例如：

```text
air_conditioner            -> [0, 1]
air_purifier               -> [0, 1]
dimmable_light             -> [0, 1]
dishwasher                 -> [0, 1]
fan                        -> [0, 1]
freezer                    -> [0, 1]
laundry_dryer              -> [0, 1]
laundry_washer             -> [0, 1]
on_off_light               -> [0, 1]
refrigerator               -> [0, 1]
rvc                        -> [0, 1]
tv                         -> [0, 1]
window_covering_controller -> [0, 1]
```

只有少数设备把 endpoint 显式展开得更多：

```text
dehumidifier -> [0, 1, 2]
humidifier   -> [0, 1, 2]
heat_pump    -> [0, 1, 2, 3, 4]
```

所以如果从实现感受上讲，当前 SimuHome 的 endpoint 呈现出一种很典型的特征：

```text
endpoint 机制是保留并使用了的，
但在大多数简单设备里，endpoint 这一层比较薄；
真正把它展开成多功能面的，主要是少数复合设备。
```

换句话说，当前项目里不是没有 endpoint，而是：

```text
大多数时候，设备的语义重心主要还是落在 cluster 上。
```

---

## 3. cluster 在代码里到底是什么

如果说 endpoint 是“设备内部的功能面容器”，那么 cluster 就是这个项目真正的能力实现核心。

cluster 的基类在 [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:6)。

它初始化时定义了三个最关键的槽位：

```python
self.cluster_id = cluster_id
self.attributes = {}
self.commands = {}
self.readonly_attributes = set()
```

这四个成员已经把 cluster 的实现方式说得非常清楚了：

```text
cluster = 一个能力对象
cluster_id = 这个能力对象的名字
attributes = 这个对象内部的状态集合
commands = 这个对象能执行的动作集合
readonly_attributes = 哪些状态只能被系统维护，不能被外部直接改
```

所以在 SimuHome 里，cluster 不是“概念上的能力分类”，而是真正的对象实例。

一个设备并不是说“它有 OnOff 这个概念”，而是说：

```text
它真的挂了一个 OnOffCluster() 对象
```

这也是为什么设备基类的 `add_cluster(...)` 能直接写成：

```python
self.endpoints[endpoint_id][cluster.cluster_id] = cluster
```

见 [devices/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:68)。

这说明 endpoint 下面挂的不是某种描述性配置，而是活的 cluster 实例。

按当前代码统计，`src/simulator/domain/clusters/` 下总共实现了 `29` 个 `Cluster` 子类，而且这 `29` 个都已经被至少一种设备实际用到了。

这 `29` 个 cluster 类分别是：

```text
BasicInformationCluster
ChannelCluster
DescriptorCluster
DeviceEnergyManagementCluster
DishwasherAlarmCluster
DishwasherModeCluster
ElectricalEnergyMeasurementCluster
ElectricalPowerMeasurementCluster
FanControlCluster
IdentifyCluster
KeypadInputCluster
LaundryDryerControlsCluster
LaundryWasherControlsCluster
LaundryWasherModeCluster
LevelControlCluster
MediaPlaybackCluster
OnOffCluster
OperationalStateCluster
PowerSourceCluster
PowerTopologyCluster
RelativeHumidityMeasurementCluster
RTCCModeCluster
RVCCleanModeCluster
RVCOperationalStateCluster
RVCRunModeCluster
TemperatureControlCluster
TemperatureMeasurementCluster
ThermostatCluster
WindowCoveringCluster
```

这说明项目的 cluster 层已经不是一个很薄的壳，而是一套相当完整的 Matter 风格能力集合。

从复用情况看，比较高频的通用 cluster 有：

```text
OnOffCluster                        -> 11 类设备
DescriptorCluster                   -> 7 类设备
FanControlCluster                   -> 5 类设备
OperationalStateCluster             -> 3 类设备
TemperatureControlCluster           -> 3 类设备
```

这也再次说明：

```text
cluster 在这个项目里不是按“设备型号”写死的，
而是真的在按“能力块”复用。
```

---

## 4. attribute 和 command 在 cluster 里到底是什么关系

这一块是最容易讲抽象、也最容易讲空的地方。  
但看代码以后，其实关系非常直接。

在 SimuHome 里，可以把三者理解成：

```text
cluster = 一个能力对象
attribute = 这个对象里的状态字段
command = 这个对象能执行的动作入口
```

不过再精确一点，它们不是“普通类成员变量/成员函数”那种最朴素写法，而是：

```text
attributes = 一个字典，保存状态值
commands = 一个字典，保存“命令名 -> 绑定方法”
```

### 4.1 command 是怎么执行起来的

cluster 基类里的 `execute_command()` 是整个命令调用链的核心，见 [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:15)。

它的逻辑非常直白：

1. 先检查 `command_id` 是否在 `self.commands` 里
2. 找到对应函数：

```python
command_func = self.commands[command_id]
```

3. 调这个函数：

```python
result = command_func(**args)
```

也就是说，在这个项目里，所谓 command 的本质就是：

```text
cluster 内部登记好的一组可调用动作
```

command 不是单独的一类对象，也不是某种外部路由表；  
它就是 cluster 自己暴露出来的动作接口。

### 4.2 attribute 是怎么写进去的

cluster 基类里的 `write_attribute()` 是属性写入的统一入口，见 [clusters/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/base.py:74)。

它的默认逻辑是：

1. 检查这个 attribute 是否存在
2. 检查它是不是只读
3. 如果允许写，就直接：

```python
self.attributes[attribute_id] = value
```

所以从实现上看，attribute 的本体就是：

```text
cluster.attributes 这个字典里的一个键值项
```

### 4.3 command 和 attribute 在运行时的关系

最重要的一点其实不是“一个是字段、一个是函数”，而是：

```text
command 往往通过执行逻辑去修改 attribute
attribute 则表示 command 执行后的当前状态
```

这才是代码里的真实关系。

---

## 5. 用 `OnOffCluster` 看最简单的一条实现链

`OnOffCluster` 是最容易看清楚这套模式的例子，见 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:6)。

它初始化时最关键的定义是：

```python
self.attributes = {
    "OnOff": False,
}

self.commands = {"Off": self._off, "On": self._on, "Toggle": self._toggle}
```

这意味着：

```text
OnOffCluster 这个对象里，
有一个叫 OnOff 的状态，
还有三个动作：On / Off / Toggle
```

然后这三个 command 的实现其实就是去修改这个 attribute。

例如：

- `_on()` 会把 `self.attributes["OnOff"] = True`  
  见 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:78)
- `_off()` 会把 `self.attributes["OnOff"] = False`  
  见 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:56)
- `_toggle()` 会把当前值取反  
  见 [onoff.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/onoff.py:99)

所以这条链可以非常直接地写成：

```text
cluster = OnOffCluster 对象
attribute = "OnOff" 当前状态
command = "On" / "Off" / "Toggle"
command 的作用 = 修改 "OnOff" 这个 attribute
```

这就是一个标准的“能力对象 + 状态字段 + 动作入口”实现。

---

## 6. 用 `FanControlCluster` 看稍复杂一点的能力对象

如果 `OnOffCluster` 说明的是最简单的情况，那么 `FanControlCluster` 展示的是：

```text
一个 cluster 可以不止有一个状态字段，
也可以在写某个 attribute 时联动修改其他 attribute。
```

`FanControlCluster` 见 [fan_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/fan_control.py:26)。

它的 `attributes` 是：

```text
FanMode
FanModeSequence
PercentSetting
PercentCurrent
```

它的 `commands` 目前主要是：

```text
Step
```

也就是说，这个 cluster 不是只管一个状态，而是把“风扇控制”这一整个能力块相关的状态和动作都包在一起了。

更关键的是，它重写了 `write_attribute()`，见 [fan_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/fan_control.py:59)。

这意味着：

```text
attribute 写入不一定只是“把字典值改掉”这么简单，
cluster 可以在写入时附带自己的业务规则。
```

例如当写入：

```text
attribute_id = "PercentSetting"
value = 66
```

它不是只做：

```text
attributes["PercentSetting"] = 66
```

而是会通过 `_update_percent_setting()` 联动更新：

- `PercentSetting`
- `PercentCurrent`
- `FanMode`

见 [fan_control.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/fan_control.py:259)

所以从实现上说，`attribute` 虽然是状态字段，但：

```text
cluster 决定这些状态字段之间有没有联动关系。
```

---

## 7. 用 `ThermostatCluster` 看 attribute 与 command 的职责分工

`ThermostatCluster` 很适合用来区分两类控制方式，见 [thermostat.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/thermostat.py:23)。

它的 `attributes` 包括：

- `LocalTemperature`
- `OccupiedCoolingSetpoint`
- `OccupiedHeatingSetpoint`
- `ControlSequenceOfOperation`
- `SystemMode`

它的 `commands` 包括：

- `SetpointRaiseLower`

从语义上看：

- `OccupiedCoolingSetpoint` 这种更像“目标状态”
- `SetpointRaiseLower` 这种更像“一次性动作”

所以在这个项目里，通常会形成这样一种分工：

```text
attribute
  -> 适合表达“当前值 / 目标值 / 配置值”

command
  -> 适合表达“执行一次动作”或“带参数动作”
```

`ThermostatCluster` 还展示了另一个实现细节：

它重写了 `write_attribute()`，在真正写入前会做校验，见 [thermostat.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/thermostat.py:46)。

比如：

- 温度值类型必须正确
- 温度值必须在范围内
- 制冷和制热设定之间必须满足 deadband

而 `SetpointRaiseLower` 这个 command 则是在自己的命令方法里完成参数校验和状态更新，见 [thermostat.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/clusters/thermostat.py:83)。

所以这类 cluster 的实现方式可以概括成：

```text
attribute 负责承载状态
command 负责驱动动作
cluster 负责把状态规则和动作规则包在一起
```

---

## 8. 从空调例子把整条调用链串起来

空调是最适合把整条路径看完整的设备，见 [air_conditioner.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py:23)。

它在 `endpoint 1` 下挂了三个 cluster：

```text
OnOffCluster
ThermostatCluster
FanControlCluster
```

所以空调在代码里的内部结构其实是：

```text
Device(air_conditioner)
  -> endpoint 0
      -> BasicInformationCluster
  -> endpoint 1
      -> OnOffCluster
      -> ThermostatCluster
      -> FanControlCluster
```

现在假设外部要执行一个动作：

```text
把空调打开
```

那调用链会是：

1. 设备层收到：

```text
endpoint_id = 1
cluster_id = "OnOff"
command_id = "On"
```

2. `Device.execute_command(...)` 先根据 `endpoint_id` 和 `cluster_id` 找到目标 cluster  
   见 [devices/base.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/base.py:82)

3. 然后转调：

```text
cluster.execute_command("On")
```

4. cluster 再从：

```text
self.commands["On"]
```

取出 `self._on` 方法执行

5. `_on()` 最终把：

```text
self.attributes["OnOff"] = True
```

写回 cluster 的状态里

这就是完整的一条链：

```text
设备路由到 cluster
-> cluster 执行 command
-> command 修改 attribute
-> attribute 成为新的当前状态
```

如果不是发命令，而是改制冷目标温度，那么链路类似，只不过会走：

```text
Device.write_attribute(...)
-> cluster.write_attribute(...)
-> cluster 校验规则
-> 更新对应 attribute
```

所以从空调这个例子看，最准确的理解方式是：

```text
cluster 是能力对象
attribute 是能力对象内部的状态
command 是能力对象对外暴露的动作入口
设备层只是负责把请求路由到正确的 cluster
```

---

## 9. event 在这套实现里处于什么位置

如果顺着前面的实现看下来，一个很明显的事实就是：

```text
endpoint / cluster / attribute / command
都有明确的数据结构和调用入口，
但 event 没有。
```

这一点从 cluster 基类最容易看清楚。

cluster 基类里有：

- `attributes`
- `commands`
- `readonly_attributes`
- `execute_command(...)`
- `write_attribute(...)`

但没有对应的：

- `events`
- `emit_event(...)`
- `read_event(...)`
- `subscribe_event(...)`

这说明在当前设备语义层实现里，Matter 里常见的 `event` 这一层并没有被真正建立成统一机制。

仓库里当然能搜到很多 `event` 字样，但大多数都属于别的层面：

- `threading.Event`
- Agent 的日志记录事件
- 调度器事件
- 进度事件

这些都不是：

```text
cluster 语义层里的 Matter-style event
```

所以更准确的说法不是：

```text
系统里完全没有任何“事件式过程”
```

而是：

```text
系统里有很多动态变化，
但这些变化大多被折叠进 attribute 更新、command 执行结果、
workflow 调度和仿真循环里了，
没有被单独抽象成 event 层。
```

---

## 10. heat_pump 是当前最能说明 endpoint 不是摆设的例子

如果只看灯、风扇、电视、空调这类简单设备，很容易得到一种感觉：

```text
endpoint 只是一个很薄的容器层，
真正有信息量的是 cluster。
```

对很多简单设备来说，这个感受确实成立。  
但 `heat_pump` 是一个明显的反例，它说明 endpoint 在当前项目里并不总是可有可无。

`heat_pump` 的定义见 [heat_pump.py](/d:/D_coderesource/simuhome/Simuhome_experiment/src/simulator/domain/devices/heat_pump.py:1)。

如果把默认的 `endpoint 0` 也算上，它总共有：

```text
5 个 endpoint
= 0, 1, 2, 3, 4
```

总共挂了：

```text
11 个 cluster
```

完整结构可以写成：

```text
endpoint 0
  -> BasicInformationCluster

endpoint 1
  -> PowerSourceCluster
  -> DescriptorCluster

endpoint 2
  -> PowerTopologyCluster
  -> ElectricalPowerMeasurementCluster
  -> ElectricalEnergyMeasurementCluster
  -> DescriptorCluster

endpoint 3
  -> DeviceEnergyManagementCluster
  -> DescriptorCluster

endpoint 4
  -> ThermostatCluster
  -> DescriptorCluster
```

这个例子非常关键，因为它说明：

```text
在 SimuHome 里，endpoint 不一定只是“把 cluster 包一下”；
当设备足够复杂时，endpoint 会真的承担“拆成功能面”的作用。
```

也正因为 `heat_pump` 的存在，我们不能简单把当前项目理解成：

```text
device -> cluster -> attribute/command
```

更准确的说法仍然是：

```text
device -> endpoint -> cluster -> attribute/command
```

只不过在大多数简单设备上，endpoint 没有被充分展开而已。

---

## 11. 用一句话总结当前实现

如果把整份文档压缩成一句话，我会这样说：

```text
SimuHome 在代码里把设备实现成
“device 下挂多个 endpoint，endpoint 下挂多个 cluster，
cluster 内部用 attributes 保存状态、用 commands 暴露动作”，
这套骨架和 Matter 的应用层组织方式非常接近；
但 event 这一层目前基本没有被单独实现出来。
```

如果再把 `cluster / command / attribute` 的关系单独压缩成一句，就是：

```text
cluster 是能力对象，
attribute 是这个对象内部的状态字段，
command 是这个对象对外暴露的动作入口，
而 command 往往通过执行逻辑去修改 attribute。
```

