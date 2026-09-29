# 家电扩容与 ABCD 调整

> 日期：2026-09-29
> 性质：可实现规格。插在 V2 闸 3 之前。不改任务族，不加房间。
> 对齐：根目录 `14_接口交接-八个工具与统一语义.md`；`doc/17_架构大幅度改动.md`、`doc/18_D0到D6详细设计.md`、`doc/19_D0前三类提示词.md`、`doc/20_完整交付进度.md`、`doc/22_三篇论文与本项目设备种类对照.md`
> 代码根：`/root/autodl-tmp/new_demo/`
> 本轮改目录、校验、observe_home 瘦身。不重跑闸 2 五条，不开始 SFT。

## 0. 这一轮改三件事

闸 2 证明 T1–T5 能在灯开关、空调、传感器上走通。户型九种不动。本轮同时做三件，不再拆成两份规格。

```text
1 校验改回设备自报
  14 的 7–32、off|cool|heat 是当时那台空调的实例
  现在写死在 B_schema，烤箱 180、洗衣机 quick 进不了 B.reset

2 目录扩容
  删假热水器开关
  加电视、热水器、洗衣机、洗碗机、烤箱、冰箱、加湿器
  主灯、台灯可调光，其余灯只开关
  亮度走 set_percentage，不开 set_brightness

3 observe_home 瘦身（给以后 1.5B 省 token）
  只回房间 room_id 与 display_name
  不再回温湿度、不再回设备数量、不再回 room_count
  温湿度改到 inspect_room / inspect_device
```

```text
不动
  九种户型
  四个家庭工具的名字和参数形状
  finish 由 C 收
  不恢复 check_goal / query_events / time_control / memory
  set_mode 用 mode，连续量用 value
  T1–T5、C-1..C-4、D6、PIPE 停闸
  闸 2 五条 jsonl 不改写

要改
  B_schema 的 mode/target 全局空调法
  B_state_engine.observe_home 的返回面
  D0 设备目录、D1 挂载、画像和四套提示词
```

## 1. 对齐 14：词表通用，观察面收窄

四个工具的输入形状没有为灯、空调另做一套。特化发生在两处：把空调自报范围写成全局法律；把 `observe_home` 做成全屋快照，把温湿度和台数每轮都塞给 A。后一件对 DeepSeek 教师还扛得住，对以后 1.5B 的每轮 observation 是纯浪费。T1 关台灯不需要先看见全屋湿度。

14 该守：`inspect_device.actions` 是动作掩码；参数范围由设备自报；越界本地拦截；动作和状态都是小词表、按设备取子集。正文里的 `7~32` 不是全局常量。`set_brightness` 是 HA 灯域别名，本 demo 不收。

```text
execute_action 签名（所有品类同一套）
  turn_on / turn_off / toggle     params={}
  set_mode                        params={"mode": <该设备 enum>}
  set_temperature                 params={"value": <number>}   -> target
  set_percentage                  params={"value": <number>}   -> level

映射
  空调温度、热水器、烤箱、冰箱     set_temperature
  风扇档位、电视音量、可调光灯、加湿器   set_percentage
  洗衣机/洗碗机/电视输入/热水器模式    set_mode

禁止
  set_brightness / set_volume / set_cycle / set_oven_temp / start
  原因：两个动作名写同一个状态键，D4 的 field=level 无法单射

预留（本轮目录不用）
  set_position -> position    下轮窗帘，键不同才另开动作
```

`inspect_device` 稀疏：有什么键回什么键，不补 14 为 HA 准备的六个 null。越界时 B 返回 `BAD_REQUEST`，世界不变。`OUT_OF_SAFE_RANGE` 只出现在 `finish.reason_code`。两套码不要混。

观察链改成：

```text
observe_home()
  只回答「家里有哪些房间」
  返回 {"rooms":[{"room_id","display_name"}, ...]}
  不返回 environment / device_count / room_count
  仍不返回 device_id

inspect_room(room_id)
  这里才给该房间的设备轻量清单（含 device_id）
  仍派生该房间温湿度摘要：T5 查「这间湿不湿」走这里或传感器
  不给全屋台数

inspect_device(device_id)
  完整公开 state + actions
  传感器的温度/湿度只在这里作为权威读数
```

17 写过 `observe_home` 带环境摘要和设备数量。以本文件为准，不回改 17 全文。`inspect_room` 的环境摘要保留：已经选定房间，这点 token 换 T5 的房间级观察。

## 2. 加哪些设备，哪些灯能调光

目录 15 条变成 21 条。`device_type` 7 种变成 14 种。实例仍由 D1 按房间配额挂。

```text
保留
  灯×7（其中 2 条改为可调光）、空调、风扇、排气扇、墙开关
  温湿度 / 温度 / 湿度 传感器

删除
  cat_heater_switch   假的热水器开关

新增
  cat_tv            tv            电视
  cat_water_heater  water_heater  热水器
  cat_washer        washer        洗衣机
  cat_dishwasher    dishwasher    洗碗机
  cat_oven          oven          烤箱
  cat_refrigerator  refrigerator  冰箱
  cat_humidifier    humidifier    加湿器
```

灯仍是同一个 `device_type=light`。能不能调光看该 SKU 有没有 `level` 和 `set_percentage`，不新开类型。

```text
可调光（state 有 on + level，动作含 set_percentage 0–100）
  cat_ceiling_light  主灯   bedroom, living, study
  cat_desk_lamp      台灯   bedroom, study

只开关（state 只有 on）
  cat_corridor_light 廊灯   corridor
  cat_balcony_light  阳台灯 balcony
  cat_kitchen_light  厨灯   kitchen
  cat_bath_light     浴灯   bath
  cat_night_light    夜灯   bedroom, corridor
```

主灯、台灯是人会说「暗一点」的。夜灯、廊灯、厨灯、浴灯、阳台灯只做开关：对它们发 `set_percentage` 必须 `UNSUPPORTED_ACTION`。T1「把书房台灯调到 30」合法；T1「把夜灯调到 30」不合法，D2 不许这么写。

房间约束写在 `allowed_room_kinds`。没有洗衣房：洗衣机进卫生间，有阳台再允许阳台。

```text
电视 tv
  房间  living, bedroom
  小户 ht_small_3 只有卧室+书房，允许卧室电视
  状态  on, mode, level
  动作  turn_on / turn_off
        set_mode        enum=["tv","hdmi","av"]
        set_percentage  音量 0–100

热水器 water_heater
  房间  bath
  状态  on, mode, target
  动作  turn_on / turn_off
        set_mode         enum=["eco","hot"]
        set_temperature  35.0–75.0 步长 1.0

洗衣机 washer
  房间  bath, balcony
  状态  on, mode
  动作  turn_on / turn_off
        set_mode  enum=["normal","quick","delicate","rinse"]
  不做  remaining_time、pause、漂洗阶段

洗碗机 dishwasher
  房间  kitchen
  状态  on, mode
  动作  turn_on / turn_off
        set_mode  enum=["normal","eco","intensive"]

烤箱 oven
  房间  kitchen
  状态  on, mode, target
  动作  turn_on / turn_off
        set_mode         enum=["bake","broil","keep_warm"]
        set_temperature  50.0–250.0 步长 5.0

冰箱 refrigerator
  房间  kitchen
  状态  on, target
  动作  turn_on / turn_off
        set_temperature  2.0–8.0 步长 0.5
  例子  冷藏调到 4 度；T4 可以要 25 度或 -10 度
  不做  开门、冷藏/冷冻两隔间、除霜周期

加湿器 humidifier
  房间  bedroom, living, study
  状态  on, level
  动作  turn_on / turn_off
        set_percentage  0–100
  例子  打开加湿器并开到 40；T3「嗓子干」落到它
  不做  水箱余量、滤芯、自动停
```

小户没有厨房则没有冰箱、烤箱、洗碗机。`ht_medium_2` 没有厨房，这三台跳过。`ht_medium_3` 没有卫生间，热水器和洗衣机若无阳台则跳过。不要为此加房间。

本轮不加窗帘、锁、扫地机、烘干机、净化器、除湿机、色温、风扇灯双组件。窗帘留给 `set_position`。净化器没有 PM 读数，T5 问「空气好不好」没有权威字段。

## 3. 目录落盘规格

对应文件：`new_demo/data_static/D0_devices.jsonl` 与同名 `.md`。`actions` 里的 min/max/enum 就是设备自报，B 只转述。

主灯、台灯改成下面这种（其余五条灯保持只有 on）：

```json
{"catalog_id":"cat_ceiling_light","id_token":"light","name_stem":"主灯","kind":"actuator","device_type":"light","allowed_room_kinds":["bedroom","living","study"],"state":{"on":true,"level":80},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}
```

```json
{"catalog_id":"cat_desk_lamp","id_token":"lamp","name_stem":"台灯","kind":"actuator","device_type":"light","allowed_room_kinds":["bedroom","study"],"state":{"on":true,"level":70},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}
```

新增七条：

```json
{"catalog_id":"cat_tv","id_token":"tv","name_stem":"电视","kind":"actuator","device_type":"tv","allowed_room_kinds":["living","bedroom"],"state":{"on":false,"mode":"tv","level":20},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["tv","hdmi","av"]}}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}
```

```json
{"catalog_id":"cat_water_heater","id_token":"heater","name_stem":"热水器","kind":"actuator","device_type":"water_heater","allowed_room_kinds":["bath"],"state":{"on":false,"mode":"eco","target":48.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["eco","hot"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":35.0,"maximum":75.0,"step":1.0}}}],"available":true}
```

```json
{"catalog_id":"cat_washer","id_token":"washer","name_stem":"洗衣机","kind":"actuator","device_type":"washer","allowed_room_kinds":["bath","balcony"],"state":{"on":false,"mode":"normal"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["normal","quick","delicate","rinse"]}}}],"available":true}
```

```json
{"catalog_id":"cat_dishwasher","id_token":"dishwasher","name_stem":"洗碗机","kind":"actuator","device_type":"dishwasher","allowed_room_kinds":["kitchen"],"state":{"on":false,"mode":"eco"},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["normal","eco","intensive"]}}}],"available":true}
```

```json
{"catalog_id":"cat_oven","id_token":"oven","name_stem":"烤箱","kind":"actuator","device_type":"oven","allowed_room_kinds":["kitchen"],"state":{"on":false,"mode":"bake","target":180.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_mode","params":{"mode":{"type":"string","enum":["bake","broil","keep_warm"]}}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":50.0,"maximum":250.0,"step":5.0}}}],"available":true}
```

```json
{"catalog_id":"cat_refrigerator","id_token":"fridge","name_stem":"冰箱","kind":"actuator","device_type":"refrigerator","allowed_room_kinds":["kitchen"],"state":{"on":true,"target":4.0},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_temperature","params":{"value":{"type":"number","minimum":2.0,"maximum":8.0,"step":0.5}}}],"available":true}
```

```json
{"catalog_id":"cat_humidifier","id_token":"humidifier","name_stem":"加湿器","kind":"actuator","device_type":"humidifier","allowed_room_kinds":["bedroom","living","study"],"state":{"on":false,"level":40},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}},{"action":"set_percentage","params":{"value":{"type":"integer","minimum":0,"maximum":100,"step":1}}}],"available":true}
```

`device_id` 仍由 D1 生成：`device_{房间token}_{id_token}`。冰箱是 `device_kitchen_fridge`，加湿器是 `device_bedroom_humidifier`。`display_name` 仍是房间中文名加 `name_stem`。

空调目录一行不要改。闸 2 五条继续合法。

## 4. B 要改什么

职责：新家电和可调光灯能进 `B.reset`；`observe_home` 只回答房间名单。C 继续看不见类型名单。

```text
改 env/B_schema.py
  DEVICE_TYPES 增加
    tv, water_heater, washer, dishwasher, oven, refrigerator, humidifier
  执行器 state 允许的键：on, mode, target, level, position, current
    稀疏；本轮目录用 on/mode/target/level
  传感器 state 允许的键：temperature, humidity
  light 允许只有 on，也允许 on+level；有 set_percentage 则必须有 level
  state.mode 不再使用全局空调枚举
  state.target 不再使用全局 7–32
  set_mode.enum 改为该设备自己的非空字符串列表
  set_temperature 的 min/max 改为该设备自己的范围
    sanity：-20 <= minimum < maximum <= 400，有 step
    下限放到 -20，是为了让冰箱 T4 的 -10 成为越界 probe，合法范围仍是 2–8
  若设备公开了 set_mode / set_temperature
    则 state.mode / state.target 必须落在该动作的 enum 或 [min,max] 里
  SUPPORTED_ACTIONS 仍是六个落地动作
    禁止 set_brightness / set_volume / set_cycle / start
    预留只有 set_position

改 env/B_state_engine.py
  observe_home 只组装 [{"room_id","display_name"}, ...]
  顶层不要 room_count、不要 device_count
  每房不要 environment、不要 device_count
  _room_environment 仍给 inspect_room 用，observe_home 不调用它
  _apply_action 映射不改：set_percentage 继续写 level

改 env/B_tool_schema.py
  observe_home 的 description 改成：查看房间 id 和名称；不返回设备、不返回温湿度。

不改
  env/B_home_env.py 四工具路由
  env/B_models.py 数据结构
  inspect_device 已经是 copy 整台设备，不要改成补六字段
```

校验例子：空调 `target=25` 过、`target=180` 不过；烤箱 `target=180` 过、`mode=cool` 不过；冰箱 `target=4` 过、`target=25` 不过；夜灯没有 `level`；主灯 `level=30` 过；对夜灯 `set_percentage` 得 `UNSUPPORTED_ACTION`。

`observe_home` 的返回必须长这样，多任何键都算本轮失败：

```json
{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"},{"room_id":"room_living","display_name":"客厅"}]}
```

同名 md：`B_schema.md`、`B_state_engine.md`、`B_tool_schema.md` 按上面改。

## 5. D1 要改什么

职责：房间允许时挂新家电；随机初始值读该设备自己的 actions。可调光灯和只开关灯走同一套随机逻辑。

对应文件：`new_demo/data/D1_home_maker.py`

```text
必挂（保持）
  climate ≥ 1
  sensor ≥ 1
  light ≥ 2
  两盏灯里至少试一盏可调光（主灯或台灯）；房间不允许则退回只开关灯

房间允许则各挂至多 1 台（在随机补齐之前，顺序固定）
  有 kitchen            -> refrigerator，再 oven，再 dishwasher
  有 bath               -> water_heater
  有 bath 或 balcony    -> washer（浴满了才试阳台）
  有 living 或 bedroom  -> tv
  有 bedroom/living/study -> humidifier

然后
  按现有 _SIZE_QUOTA 补到每房最少、全屋目标台数
  小 5 / 中 10 / 大 14，每房上限不变
```

厨房配额 2–3。冰箱优先于烤箱、洗碗机：中国家庭厨房几乎都有冰箱，烤箱可以没有。卫生间：热水器优先于洗衣机。不要加大 `max_per`。

`_randomize_device_state` 不要按 `device_type` 写分支。改成读 actions：

```text
有 on                 -> 随机开关
有 set_mode           -> mode 取该 enum
有 set_temperature    -> target 按该动作 min/max/step 取点
有 set_percentage     -> level 按该动作 min/max/step 取点
传感器温度/湿度        -> 保持现有 16–32 / 30–80
```

主灯、风扇、电视、加湿器的 `level` 走同一段。夜灯没有 `set_percentage`，不会被写上 `level`。

种子仍不写进 s0。同房不能重复 `catalog_id`。

测试：`len(devices)==21`；烤箱/冰箱只在 kitchen；洗衣机只在 bath/balcony；加湿器只在 bedroom/living/study；30 种子里夜灯的 state 不含 level；抽到的主灯 `level ∈ [0,100]`；抽到的冰箱 `target ∈ [2,8]`；抽到的空调 `target ∈ [7,32]`；带厨房的户型 30 种子里至少一次冰箱。

## 6. C 与 A 要改什么

C 四步不读 `device_type`。`conditions.field` 仍是 `on/mode/target/level`。T5 仍看 `required_observations` 是否 inspect 成功。T5 不许把 `observe_home` 当成已经读过湿度。

```text
C 代码
  eval/C_episode_runner.py    不改
  eval/C_episode_evaluator.py 不改
  C-3 只认 inspect_room / inspect_device，observe_home 不算观察完成

C 测试补
  observe_home 的 data 只有 rooms[].room_id 与 display_name
  T1 书房台灯 level=30 completed，execute_action 是 set_percentage
  T1 夜灯 set_percentage 不得作为成功条件（手写 home 里夜灯无该动作）
  T4 冰箱 25 度：B 返回 BAD_REQUEST，finish 才是 OUT_OF_SAFE_RANGE
  T5 必有 inspect_device 或 inspect_room；只 observe_home 则 C-3 失败
```

A 只出现在 D5 的 `C.run`。`agents/A_policy.py` 不改调用形状。改 `A_policy.md` 和工具描述：

```text
observe_home 只给房间名单，没有温湿度，没有设备。
要找设备必须 inspect_room；要读数或调参必须 inspect_device。
范围只看该次 actions，不要默认 7–32。
灯不一定能调光：夜灯、廊灯没有 set_percentage。
电视音量、加湿器、可调光灯都走 set_percentage，不要发明 set_volume / set_brightness。
越界：B 给 BAD_REQUEST，然后 finish(refused, OUT_OF_SAFE_RANGE)。
```

## 7. D2–D6 与四套提示词

运行时装配规则不变。例子仍用灯+空调示范格式。T 模板里的示例 s0 若还写 `observe_home` 会带湿度，不要让模型以为观察工具会给读数；示例可以不展示 observe 返回。

```text
1 画像        D0_personas.jsonl
2 任务模板    T1..T5_*.md
3 用户指令    D0_request_T1..T5.md
4 D6          D6_T3.md D6_T4.md D6_T5.md
另 D3         D3_review_T1..T5.md
```

### 7.1 画像

二十条人保留。只在 `habits` 末尾补家电偏好。没有厨房就不能编冰箱。

```text
p01 李梅     晚上电视声音不能大；泡脚热水器不要太烫；冬天开加湿器，灯光偏暗
p02 张强     孩子睡了关电视；脏衣服隔天快洗
p03 王芳     夜班回来开热水器；鼻炎要看湿度，太干再开加湿器
p07 苏敏     嗓子干，卧室加湿器开一点，主灯不要太亮
p08 周凯     进门脏衣服丢进洗衣机快洗
p09 韩雪     直播关客厅电视；妆后怕干，加湿器开低档
p12 何丽     打烊回家用洗碗机；冰箱保持四五度；偶尔用烤箱热剩菜
p13 吴迪     训练后热水器要热；冰箱不要调太低
p18 冯洁     书房台灯要够亮，离开时关掉
p20 许苗苗   孩子九点后关电视；洗衣机不要开得太吵
```

其余习惯不动。画像仍只影响 intent。

### 7.2 任务模板 T1–T5

公共句：

```text
本轮只能使用这份 s0 里已经出现的设备。没有的不要编。
模式用该设备 enum，温度用该设备 min/max。
conditions.field 只许 on / mode / target / level。
灯是否可调光看它有没有 set_percentage：有才能写 level，夜灯只能写 on。
```

各类额外一句：

```text
T1  可以是关电视、台灯 level=30、洗衣机 mode=quick、烤箱 180、冰箱 4、加湿器 level=40。
T2  可跨品类，例如关电视 + 开洗碗机；keep 仍写一台不动的设备。
T3  刺眼 -> 可调光灯把 level 调低（该房必须有主灯或台灯）
    太干 -> 加湿器；衣服放了一天 -> 洗衣机。intent 不出现动作名。
T4  越界不限于空调：
      set_temperature：空调 5、热水器 90、烤箱 400、冰箱 25
      set_percentage：电视音量 200、主灯亮度 150、加湿器 200
    对夜灯打 set_percentage 算 UNSUPPORTED_ACTION，不要当作 OUT_OF_SAFE_RANGE 的温度越界。
    READ_ONLY 仍只打传感器。
    B 返回 BAD_REQUEST；A 结束才用 OUT_OF_SAFE_RANGE。
T5  仍是环境查询。observe_home 没有温湿度。
    required_observations 必须是 inspect 房间或传感器。
    不要把「冰箱几度」「洗衣机在不在转」写成 T5。
```

### 7.3 用户指令

加一句：可调光说「暗一点 / 亮到三十」；不可调光的灯只说开关。模式用快洗、烘焙、HDMI。不要写出 `set_percentage`、`level`。

### 7.4 D3

硬泄露名单不扩动作名，不要把 `set_brightness` 加进去。用户说「台灯暗一点」而 task 是 `level=30` 算说全。用户要调夜灯亮度而 task 只关夜灯，打 `EXTRA_INTENT`。T5 若只根据「看了一眼家里」而没点房间或传感器，打 `TARGET_NOT_COVERED`（因为观察工具不再给湿度）。

### 7.5 D6

T4：拒绝说明贴着该次 inspect_device 的范围，冰箱、烤箱、主灯亮度同理。T5：summary 必须来自 inspect 到的读数，不能来自 observe_home。例子仍可用空调五度。

D4 的 `FIELD_ACTIONS` 已覆盖 `on/target/mode/level`。台灯调光、加湿器、冰箱都能打。补：主灯 `level=30` 通过；夜灯 `level=30` 静态失败；冰箱 `target=25` 的 T4 probe 失败。

## 8. 任务族里怎么用

不新开 T6。隐藏条件写字段。

```text
T1  台灯 level=30；关客厅电视；冰箱 target=4；加湿器 on=true 且 level=40
T2  关电视 + 开洗碗机，客厅主灯 keep
T3  「灯刺眼」-> 主灯或台灯 level 调低
    「嗓子干」-> 加湿器
T4  冰箱 25 / 烤箱 400 / 主灯 150 / 空调 5
T5  inspect 传感器或房间 environment；observe_home 不够
```

## 9. 和闸 2、闸 3 的关系

```text
闸 2 五条
  jsonl 不改写。家里的热水器开关仍是旧 switch
  旧轨迹里 observe_home 的返回还带着 environment，那是历史记录
  用新 B 重放同一 home 时，observe_home 将是瘦身版；不要拿旧 event 当新契约

闸 3
  本规格落地、pytest 全绿之后再跑
  新目录 + 瘦身 observe 下才冻每类 4 条
```

17 的「十五种设备」和「observe_home 带环境摘要」以本文件为准。

## 10. 测试清单（本轮出门）

```text
目录
  21 条；无 cat_heater_switch
  主灯、台灯有 set_percentage；夜灯等五条没有
  DEVICE_TYPES 14 个键
  SUPPORTED_ACTIONS 不含 set_brightness / set_volume

observe_home
  返回键只有 rooms
  每个房间键只有 room_id、display_name
  全文不得出现 environment / device_count / room_count / temperature / humidity

设备自报
  空调 25 过、180 不过
  烤箱 180 过、400 不过、mode=bake 过、mode=cool 不过
  冰箱 4 过、25 不过
  洗衣机 mode=quick 过、mode=cool 不过
  主灯 set_percentage(30) 过
  夜灯 set_percentage(30) -> UNSUPPORTED_ACTION
  烤箱 inspect_device 无 level/position/current

越界码表
  冰箱 25：B = BAD_REQUEST，C finish = OUT_OF_SAFE_RANGE

D1
  30 种子：冰箱/烤箱只在 kitchen；洗衣机只在 bath/balcony
           加湿器只在 bedroom/living/study
  夜灯 state 无 level；主灯若被抽到则 level ∈ [0,100]
  带厨房户型至少一次冰箱

D4
  台灯 level=30 写入过
  夜灯 level 条件失败
  冰箱 25 probe 失败且 state 不变

C
  台灯调光 completed
  冰箱越界 refused
  T5 只 observe_home -> C-3 false

提示词
  A_policy 写明 observe_home 无温湿度
  T4 出现冰箱或主灯亮度越界
  T5 禁止把 observe_home 当读数来源

回归
  旧五条 jsonl 仍能 ensure_valid_scenario
```

命令：`python -m pytest new_demo -q`，工作目录 `/root/autodl-tmp`。记录写 `new_demo/reports/V2_appliance_test.md`。

## 11. 对应文件

```text
改数据
  data_static/D0_devices.jsonl 与 .md
  data_static/D0_personas.jsonl 与 .md
  data_static/D0_templates/T1..T5_*.md
  data_static/D0_templates/D0_request_T1..T5.md
  data_static/D0_templates/D3_review_T1..T5.md
  data_static/D0_templates/D6_T4.md D6_T5.md
  data_static/D0_templates/A_policy.md

改代码
  env/B_schema.py 与 .md
  env/B_state_engine.py 与 .md          observe_home 瘦身
  env/B_tool_schema.py 与 .md           工具描述
  data/D1_home_maker.py 与 .md
  tests/D1_test_home_maker.py
  tests/D4_test_oracle.py
  tests/C_test_run.py
  新建 tests/B_test_schema_appliances.py
  新建 tests/B_test_observe_home.py     断言瘦身返回面

不改
  env/B_home_env.py
  env/B_models.py
  eval/C_episode_runner.py
  eval/C_episode_evaluator.py
  data/PIPE_pipeline.py
  data_static/D0_homes.jsonl
  闸 2 的 data_processed 五条
```

## 12. 本文件不负责

不规定闸 3 种子。不定 LoRA。不把 21 条目录说成 SMH 的 17 类。本轮不实现窗帘、`set_position`、色温。不把 `set_brightness` 收进词表。不恢复 14 的另外四个工具。不把 `inspect_device` 补回六个 null。不把 `OUT_OF_SAFE_RANGE` 写进 B。不让 `observe_home` 重新携带温湿度或台数。落地按第 10 节测试；本文是规格，不改 `new_demo` 代码。
