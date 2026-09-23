# 从 Matter 到 SimuHome：完全用例子梳理

这份笔记不再优先讲抽象定义，而是尽量只用例子回答一个问题：

```text
Matter 里的 Node / Endpoint / Cluster / Attribute / Command
到了 SimuHome 里，究竟分别落成了什么？
```

如果先说结论，可以先记这一句：

```text
Matter 负责把“设备能力怎么组织”讲清楚，
SimuHome 负责把“这些能力会怎样持续改变家里的环境”讲清楚。
```

下面我们只靠例子往前推。

---

## 1. 先看一个最重要的例子：一台空调

假设家里有一台空调，你想做三件事：

1. 打开空调电源
2. 把制冷目标温度设到 20°C
3. 把风速调高

如果不用 Matter 风格建模，很多系统会写成这样：

```text
air_conditioner.turn_on()
air_conditioner.set_mode("cool")
air_conditioner.set_target_temperature(20)
air_conditioner.set_fan_speed("high")
```

这当然能用，但问题是：

- 换成风扇、空气净化器、地暖，接口名字就会变
- Agent 学到的是“这台设备的私有 API”
- 很难把“开关能力”“温控能力”“风速能力”抽成可复用模块

Matter 不这么做。Matter 会把这台空调拆成下面这个结构：

```text
一个设备实例
  -> 一个 endpoint
      -> OnOff cluster
      -> Thermostat cluster
      -> FanControl cluster
```

在 SimuHome 里，这个映射几乎是直接落地的。空调设备源码就是：

```python
self.add_cluster(1, OnOffCluster())
self.add_cluster(1, ThermostatCluster())
self.add_cluster(1, FanControlCluster())
```

也就是说，SimuHome 里的空调不是“一个大对象里面塞满各种专用方法”，而是：

```text
Device(空调)
  -> endpoint 1
      -> OnOff
      -> Thermostat
      -> FanControl
```

这个例子一旦看明白，后面的层级就都好理解了。

---

## 2. 这个例子里，Matter 的四层到底分别在干什么

还是只看这台空调。

### 2.1 第一层：Node 在例子里是什么

你可以先把 Node 粗暴理解成：

```text
“我要操作的这一台设备实例本身”
```

例如家里有两台空调：

- 客厅空调
- 卧室空调

那你发命令时，第一件事永远不是“设温度”，而是：

```text
你到底在和哪一台设备说话？
```

在真实 Matter 里，这件事落在 Node 这个层级上。

在 SimuHome 里，这个层级没有完整还原成网络协议节点，但保留成了：

```text
一个 Device 实例
```

比如：

```text
living_room_air_conditioner_1
bedroom_air_conditioner_2
```

所以在 SimuHome 语境里，可以先把：

```text
Matter 的 Node
≈
SimuHome 里的一个 device_id 对应的一台设备
```

这里注意一个边界：

- Matter 的 Node 强调“网络里可寻址设备”
- SimuHome 的 Device 强调“仿真系统里的一台设备对象”

它们不完全等价，但在“怎么组织设备能力”这个问题上，足够对应。

---

### 2.2 第二层：为什么空调下面还要有 Endpoint

继续看这台空调。

很多人第一次看到这里会想：

```text
空调不就是一台设备吗？
为什么还要多出一个 endpoint 1？
```

最容易懂的办法不是背定义，而是看反例。

#### 反例 A：如果没有 endpoint

那空调可能只能被建成一个巨大的平面对象：

```text
{
  power: ...,
  system_mode: ...,
  cool_setpoint: ...,
  heat_setpoint: ...,
  fan_mode: ...,
  fan_percent: ...
}
```

这样短期看省事，但坏处马上出现：

- 开关能力和温控能力揉在一起
- 风扇相关字段和温控字段没有边界
- 别的设备很难复用这一套结构

#### 反例 B：把一台空调硬拆成三台假设备

也可以这样拆：

- 一个“空调开关设备”
- 一个“空调温控设备”
- 一个“空调风扇设备”

这又会带来另一个问题：

```text
明明是同一个物理设备，
却被伪装成三台设备。
```

这会让设备发现、状态归属、后续联动都变得奇怪。

#### Matter 的做法

Matter 取中间路线：

```text
一台设备还是一台设备
但它内部可以有一个或多个 endpoint
每个 endpoint 表示一个相对独立的功能面
```

放到这台空调上，可以先这么理解：

```text
Node / Device = 整台空调
Endpoint 1    = 这台空调对外暴露的主控制面
```

在 SimuHome 里，空调把主要能力都挂在 `endpoint 1` 下面，这正是这种思路。

#### 再看一个更适合 endpoint 的例子：多孔插线板

如果是一个 4 孔插线板，最自然的表示不是：

```text
power_socket_1_on
power_socket_2_on
power_socket_3_on
power_socket_4_on
```

全塞进同一个字段堆里。

而是：

```text
一台插线板
  -> endpoint 1 = 第一个插孔
  -> endpoint 2 = 第二个插孔
  -> endpoint 3 = 第三个插孔
  -> endpoint 4 = 第四个插孔
```

这样每个插孔都能独立寻址，但它们又仍然属于同一个设备整体。

所以 endpoint 这一层，最适合记成：

```text
“同一台设备内部，可单独建模、可单独寻址的功能面”
```

---

### 2.3 第三层：为什么 endpoint 下面不是字段，而是 Cluster

继续看空调的 `endpoint 1`。

现在它下面有三个 cluster：

- `OnOff`
- `Thermostat`
- `FanControl`

为什么不直接把这些字段挂在 endpoint 上？

因为 Matter 想复用的是“能力块”，不是“设备整包定义”。

#### 例子 1：`OnOff` 为什么要独立成 cluster

空调能开关，灯也能开关，风扇也能开关，净化器也能开关。

如果开关只是每个设备私有字段的一部分，那么：

- 灯有一套开关写法
- 风扇有一套开关写法
- 空调又有一套开关写法

Agent 学不到统一语义。

而如果把它抽成 `OnOff` cluster，含义就统一了：

```text
这是一个标准的“开关能力块”
```

谁支持这个 cluster，谁就按这套语义来。

#### 例子 2：`Thermostat` 为什么要独立成 cluster

空调、热泵、恒温器，虽然外形不同，但都可能有：

- 当前温度
- 制冷目标温度
- 制热目标温度
- 系统模式

这些东西天然属于同一组语义。

所以它们不应该散落成一些不相关字段，而应该被组织进：

```text
Thermostat cluster
```

#### 例子 3：`FanControl` 为什么不并进 `Thermostat`

因为“温控”和“风扇档位”不是一回事。

看这个区别最简单的方式是问两个问题：

1. 有没有设备支持风速调节，但根本没有温控？
有，比如普通风扇。

2. 有没有设备支持温控，但风扇控制很弱或根本不是核心能力？
也有。

所以最合理的办法不是做一个“超级空调 cluster”，而是拆成：

- 温控是 `Thermostat`
- 风速是 `FanControl`

这样这些能力块才能跨设备复用。

所以 cluster 最好记成：

```text
“可复用的标准能力模块”
```

---

### 2.4 第四层：为什么 Cluster 下面还要分 Attribute 和 Command

还是拿 `OnOff` 来看。

如果你问“空调现在开着吗”，你要的是状态。

如果你说“把空调打开”，你要的是动作。

这两件事看起来都和“开关”有关，但它们本质不同：

```text
当前开关状态
!=
请求设备执行打开动作
```

所以在 Matter 里，它们被分成：

- `Attribute`：状态
- `Command`：动作

在这个项目里也正是这样：

```text
OnOff cluster
  attribute: OnOff
  command: On / Off / Toggle
```

再看 `Thermostat`：

- `LocalTemperature` 是状态
- `OccupiedCoolingSetpoint` 是可写目标
- `SetpointRaiseLower` 是动作命令

这就比“所有东西都叫字段”清楚得多，因为控制器可以区分：

- 我现在是在读现状
- 我现在是在改目标值
- 我现在是在发一个动作命令

至于 `Event`，这份项目里不是重点，但在 Matter 语义上它表示：

```text
“某件已经发生过、可被报告/订阅的事情”
```

所以第四层最好记成：

```text
同一个能力块内部，再把状态、动作、历史分开
```

---

## 3. 把刚才那台空调，完整映射到 SimuHome

现在我们把例子完全落到 SimuHome 上。

### 3.1 结构映射

对这台空调，可以直接写成：

```text
Matter 视角
---------
Node
  -> Endpoint 1
      -> OnOff
      -> Thermostat
      -> FanControl

SimuHome 视角
-------------
一个 Device 实例
  -> device.endpoints[1]
      -> "OnOff" cluster 对象
      -> "Thermostat" cluster 对象
      -> "FanControl" cluster 对象
```

仓库里的基类也非常直接：

```python
self.endpoints: dict[int, dict[str, Cluster]] = {0: {}}
```

这句话几乎就已经把整个映射说完了：

```text
endpoint_id -> { cluster_id -> cluster_instance }
```

也就是说，这个项目底层不是“设备名 -> 专用方法表”，而是：

```text
设备 -> endpoint -> cluster
```

---

### 3.2 操作映射

如果你想打开空调，Matter 风格的思路不是：

```text
call air_conditioner.turn_on()
```

而是按路径去找：

```text
这台设备
-> endpoint 1
-> OnOff cluster
-> On command
```

在 SimuHome 里，对应的就是：

```python
execute_command(endpoint_id, cluster_id, command_id, **args)
```

所以一条动作可以理解成：

```text
device_id = living_room_air_conditioner_1
endpoint_id = 1
cluster_id = "OnOff"
command_id = "On"
```

如果你不是发命令，而是改制冷目标温度，那么路径会变成：

```text
device_id = living_room_air_conditioner_1
endpoint_id = 1
cluster_id = "Thermostat"
attribute_id = "OccupiedCoolingSetpoint"
value = 2000
```

这里的 `2000` 表示 20.00°C。

所以 SimuHome 的接口形式，本质上就是一个 Matter 风格路径：

```text
device_id
+ endpoint_id
+ cluster_id
+ command_id / attribute_id
```

它不是在模拟报文细节，但确实在模拟 Matter 的能力寻址方式。

---

## 4. 再补一个关键问题：Cluster 的“可复用”在代码里真的有体现吗

有，而且体现得很直接。

前面我们说：

```text
cluster 不是“某台设备私有的一组字段”，
而是“可复用的标准能力模块”。
```

这句话在这个仓库里不是停留在概念层，而是已经写进代码结构里了。

### 4.1 最直观的复用：同一个 cluster 类被多个设备直接挂载

还是先看最熟悉的两个 cluster：

- `OnOffCluster`
- `FanControlCluster`

它们不是只属于空调，而是被很多设备直接复用。

例如：

- 空调挂了 `OnOffCluster`、`ThermostatCluster`、`FanControlCluster`
- 风扇挂了 `OnOffCluster`、`FanControlCluster`
- 加湿器挂了 `OnOffCluster`、`FanControlCluster`
- 除湿器挂了 `OnOffCluster`、`FanControlCluster`
- 空气净化器也挂了 `OnOffCluster`、`FanControlCluster`

也就是说，代码里真实发生的是这种事：

```text
空调需要“开关能力”  -> 挂 OnOffCluster
风扇需要“开关能力”  -> 挂 OnOffCluster
净化器需要“开关能力”-> 挂 OnOffCluster

空调需要“风速能力”  -> 挂 FanControlCluster
风扇需要“风速能力”  -> 挂 FanControlCluster
加湿器需要“风速能力”-> 挂 FanControlCluster
```

这就不是“大家刚好都各自写了一个 power 字段”，而是：

```text
同一个能力块类，被多个设备复用。
```

### 4.2 空调和风扇为什么是最好的对照例子

空调和风扇外观看起来很不一样，但它们都需要：

- 开关
- 风速/档位调节

所以它们在代码里都挂了：

```text
OnOffCluster
FanControlCluster
```

这件事特别能说明 cluster 复用的价值。

因为如果没有 cluster 复用，代码大概率会变成：

```text
AirConditioner.set_power(...)
AirConditioner.set_fan_speed(...)

Fan.turn_on(...)
Fan.set_speed(...)
```

这样“风速控制”虽然表面意思接近，但底层不会共享统一语义。

而现在的结构更像是：

```text
空调：我支持 OnOff + FanControl + Thermostat
风扇：我支持 OnOff + FanControl
```

差异体现在“设备挂了哪些 cluster”，而不是“每台设备都重新发明一套接口”。

### 4.3 冰箱和冷冻柜也是另一个复用例子

除了开关/风速这种例子，温控也有复用。

例如冰箱和冷冻柜都复用了：

- `TemperatureControlCluster`
- `TemperatureMeasurementCluster`

但它们通过不同初始值表达不同设备语义：

- 冰箱把目标温度初始化在 7°C 附近
- 冷冻柜把目标温度初始化在 -15°C 附近

也就是说：

```text
复用的是“温控能力块”本身，
变化的是“这个设备的默认参数和运行逻辑”。
```

这正是 Matter 风格设计想要的效果。

### 4.4 设备基类也在配合这种复用

如果你看设备基类，会发现它根本不关心“你是空调还是风扇”，它只关心：

```text
某个 endpoint 上挂了哪些 cluster
```

然后统一通过下面两个入口与 cluster 交互：

- `execute_command(endpoint_id, cluster_id, command_id, **args)`
- `write_attribute(endpoint_id, cluster_id, attribute_id, value)`

这意味着：

```text
只要设备挂了这个 cluster，
系统就能沿着统一路径去操作它。
```

从这个角度看，复用不只是“类名复用”，还是：

- 结构复用
- 调用路径复用
- 能力语义复用

### 4.5 但要注意：复用 cluster，不等于所有设备行为完全一样

这一点也很重要。

比如空调和风扇虽然都复用了 `FanControlCluster`，但它们外层设备逻辑还是可以不同。

例如这个项目里，空调和风扇都额外加了“电源没开时，不能改风速相关能力”的检查。

所以更准确地说，代码里的模式是：

```text
cluster 负责提供可复用的标准能力块
device 负责补充这个设备自己的依赖约束、默认值和环境含义
```

换句话说：

```text
复用的是“能力模块”，
不是把所有设备强行做成完全一样。
```

### 4.6 用一句话记这个问题

```text
在 SimuHome 里，cluster 的复用不是停留在概念上，
而是直接体现为：多个设备把同一个 cluster 类挂到自己的 endpoint 上，
再通过统一的 execute_command / write_attribute 路径去操作它。
```

---

## 5. 再用三个具体动作，把映射彻底走一遍

### 例子 A：打开空调

用户意图：

```text
把客厅空调打开
```

Matter 风格理解：

```text
目标设备：客厅空调
目标 endpoint：1
目标 cluster：OnOff
目标 command：On
```

SimuHome 里的效果：

```text
OnOff.OnOff attribute 从 False 变成 True
```

这时你可以把它理解成：

```text
“开空调”不是调用一个设备专属 API，
而是在标准 OnOff 能力块上发了一个 On 命令。
```

### 例子 B：把制冷目标温度设到 20°C

用户意图：

```text
把客厅空调设到 20°C 制冷
```

Matter 风格理解：

- 电源得先开
- 温控能力在 `Thermostat`
- 制冷目标值是 `OccupiedCoolingSetpoint`

在 SimuHome 里，这不是一个叫 `set_temperature()` 的私有方法，而更像：

```text
write_attribute(
  endpoint_id=1,
  cluster_id="Thermostat",
  attribute_id="OccupiedCoolingSetpoint",
  value=2000
)
```

而且项目里还额外做了一个非常真实的限制：

```text
如果空调还没开机，
你去改 Thermostat / FanControl 相关能力，会报依赖错误。
```

这件事特别适合说明：

```text
SimuHome 不只是“把 Matter 名字抄过来”，
而是在 Matter 风格骨架上继续加入设备行为约束。
```

### 例子 C：把风速调高

用户意图：

```text
把客厅空调风速调高
```

Matter 风格理解：

- 风速不属于 `Thermostat`
- 它属于 `FanControl`

所以对应动作可能是：

```text
write_attribute(
  endpoint_id=1,
  cluster_id="FanControl",
  attribute_id="PercentSetting",
  value=66
)
```

或者：

```text
execute_command(
  endpoint_id=1,
  cluster_id="FanControl",
  command_id="Step",
  Direction=0
)
```

这个例子最能体现 cluster 拆分的价值：

```text
同样是“空调这个设备”的能力，
开关、温控、风速并没有混成一个巨大命名空间，
而是分散在可复用的标准能力块里。
```

---

## 6. 再看一个例子：为什么 `LocalTemperature` 不能让用户随便写

这个例子最能说明：

```text
Matter 负责设备语义，
SimuHome 负责环境演化。
```

继续看空调。

很多人会自然地以为：

```text
如果 Thermostat 里有 LocalTemperature，
那我是不是可以直接把它改成 18°C？
```

在 SimuHome 里，这个思路是不对的。

原因不是技术上不能改，而是语义上不该这样改。

### 正确的故事应该是

1. 你打开空调
2. 你设定制冷目标温度
3. 房间温度随着时间一点点下降
4. 设备上的温度传感属性被环境系统回写

也就是说：

```text
LocalTemperature 不是“我想写多少就写多少”的控制值，
而是“环境现在是多少，设备就读到多少”的观测值。
```

项目代码里也确实是这么做的：

```python
thermostat.attributes["LocalTemperature"] = int(self.current_value)
```

这行代码不是在设备命令里执行的，而是在温度聚合器同步环境时执行的。

所以这个例子可以帮你明确区分两类量：

- `OccupiedCoolingSetpoint`：用户/Agent 可写的目标
- `LocalTemperature`：环境系统回写的当前观测

这恰好就是 Matter 和 SimuHome 的分工边界。

#### 用一句人话概括这个例子

```text
你能控制“空调想把房间变成几度”，
但你不能直接控制“房间此刻已经是几度”。
```

前者是设备控制语义，后者是环境演化结果。

---

## 7. 再看一个例子：为什么只讲 Matter 还讲不完 SimuHome

还是这台空调。

假设现在房间是 28°C，你做了下面这组操作：

1. 打开空调
2. `SystemMode = COOL`
3. `OccupiedCoolingSetpoint = 2000`
4. `FanControl.PercentSetting = 100`

如果只讲 Matter，我们最多只能讲到这里：

```text
设备有哪些能力
这些能力在哪个 cluster
应该读哪个 attribute
应该发哪个 command
```

但接下来最关键的问题其实是：

```text
30 秒之后，房间温度会怎样变化？
5 分钟之后呢？
空调停了之后，温度会不会慢慢回归环境基线？
```

这些问题 Matter 本身并不回答。

而 SimuHome 回答了。

从仓库实现可以看出，这个系统会：

- 根据设备状态计算持续影响
- 按 tick 推进温度变化
- 让当前温度缓慢回归 baseline
- 再把结果同步回设备传感属性

所以这个例子特别适合拿来区分：

```text
Matter 讲的是“控制结构”
SimuHome 讲的是“控制后果”
```

---

## 8. 再看一个例子：为什么 SimuHome 还多了 workflow

假设用户不是说“现在打开空调”，而是说：

```text
今晚 19:00 打开客厅空调，设成 20°C 制冷。
```

这时候问题已经不是单条命令怎么发了，而是：

```text
未来某个时间点，按顺序执行一串动作
```

这显然超出了 Matter 数据模型本身。

在 SimuHome 里，它会变成一条 workflow：

```text
19:00
  1. 对 OnOff 发 On
  2. 对 Thermostat 写 SystemMode=COOL
  3. 对 Thermostat 写 OccupiedCoolingSetpoint=2000
```

项目里也专门暴露了：

```text
schedule_workflow(start_time, steps)
```

这个例子能说明一个非常重要的边界：

- Matter 擅长表达“一个设备能力块如何被寻址和操作”
- SimuHome 额外表达“这些操作何时发生、以什么顺序发生、执行后如何验证”

所以如果有人说：

```text
只要把 Matter 应用层讲清楚，就等于把 SimuHome 讲清楚了
```

这个说法只能算讲对了一大半。

因为 workflow、虚拟时间、快进验证，这些都不是 Matter 自己负责的。

---

## 9. 用一个总表，把前面的例子压缩一下

### 8.1 结构映射表

```text
Matter 概念                  在空调例子里是什么                  在 SimuHome 里是什么
-----------------------------------------------------------------------------------------
Node                         这台客厅空调                        一个 Device 实例
Endpoint                     空调的主控制面                      device.endpoints[1]
Cluster                      开关/温控/风速三个能力块            OnOff / Thermostat / FanControl
Attribute                    当前值或目标值                      cluster.attributes[...]
Command                      主动执行动作                        cluster.commands[...]
Interaction path             按层级定位能力                      execute_command / write_attribute 参数
```

### 8.2 三种典型操作

```text
用户说“打开空调”
-> endpoint 1 / OnOff / On command

用户说“设成 20°C”
-> endpoint 1 / Thermostat / OccupiedCoolingSetpoint = 2000

用户说“风速调高”
-> endpoint 1 / FanControl / Step
   或 endpoint 1 / FanControl / PercentSetting = 66/100
```

### 8.3 两种不是 Matter 单独能解释完的事

```text
“现在房间温度为什么是 26.3°C？”
-> 要看 SimuHome 的环境聚合器和 tick 推进

“晚上 19:00 再执行这组操作”
-> 要看 SimuHome 的 workflow 调度和时间系统
```

---

## 10. 如果只记一句话，应该记哪一句

我建议记这句：

```text
Matter 把一台设备拆成“可寻址的能力块”，
SimuHome 再把这些能力块放进一个会随时间变化的家庭环境里。
```

如果换成更贴近前面空调例子的说法，就是：

```text
Matter 告诉你：
“开关、温控、风速分别属于哪个能力块，应该怎么寻址、怎么控制”

SimuHome 告诉你：
“这些控制发生以后，房间温度会怎样变化，多久变化，以及未来任务怎么执行”
```

这就是“从 Matter 到 SimuHome”的核心映射。

---

## 11. 这次对照过的资料

这次梳理主要对照了两类资料。

第一类是 Matter 官方或准官方资料，用来确认概念边界：

- Google Home Developers: Matter Primer  
  https://developers.home.google.com/matter/primer
- Google Home Developers: The Device Data Model  
  https://developers.home.google.com/matter/primer/device-data-model
- Google Home Developers: Interaction Model Concepts  
  https://developers.home.google.com/matter/primer/interaction-model
- Silicon Labs: Matter Data Model  
  https://docs.silabs.com/matter/latest/matter-fundamentals-data-model/
- CSA: Matter Application Cluster Specification  
  https://csa-iot.org/wp-content/uploads/2022/11/22-27350-001_Matter-1.0-Application-Cluster-Specification.pdf

第二类是本仓库里的实现，用来确认映射不是“概念上像”，而是“代码里确实这样落”：

- `Simuhome_experiment/src/simulator/domain/devices/base.py`
- `Simuhome_experiment/src/simulator/domain/devices/air_conditioner.py`
- `Simuhome_experiment/src/simulator/domain/clusters/base.py`
- `Simuhome_experiment/src/simulator/domain/clusters/onoff.py`
- `Simuhome_experiment/src/simulator/domain/clusters/thermostat.py`
- `Simuhome_experiment/src/simulator/domain/clusters/fan_control.py`
- `Simuhome_experiment/src/simulator/domain/aggregators/temperature.py`
- `Simuhome_experiment/src/agents/tools.py`
