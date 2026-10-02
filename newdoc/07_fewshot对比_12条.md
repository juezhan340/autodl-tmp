# 本地 Qwen2.5-1.5B：few-shot 提示词 v2（SimuHome 风格）+ 12 条对比

> 服务：llama.cpp b10991（Vulkan）、Qwen2.5-1.5B-Instruct Q8_0、2 slot × 32K、端口 18080
> 评测：同一批 12 条任务、2 路并发、12 轮上限；`D0_templates` 主提示词未改动
> few-shot 只存在于评测 runner：`run_local_eval.py --few-shot`

## 0 新版设计（对照 SimuHome）

```text
SimuHome 的 ReAct 写法
  messages = [system] + one-shot 示例对话 + 包装过的真实任务 user
  system 里给协议与工具；示例演示完整走位；
  真实任务 user 明确说「示例不是真实环境，先查工具」，并重申一次只输出一个 JSON

本评测的 v2 照这个结构
  1  system 用 A_policy.md 原文（不动主文件）
  2  三段示例：控制 / 拒绝 / 查询，每条带「示例一/二/三」框架
  3  真实任务包成：
     以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
     [TASK] <user_request>
     按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；
     一次只调一个工具；最多 12 步，尽快交 finish。
```

## 1 v2 的 A 侧完整提示词

### 1.1 system（A_policy.md 渲染后全文，含工具 schema）

```text
你是智能家居助手。根据用户的这一句请求操作家里的设备；你看不见隐藏任务，只能靠工具观察。

输出协议
  每次只输出一个 JSON，输出后立刻停：
  {"name":"工具名","arguments":{...}}
  不要前言、不要围栏、不要 thought、不要解释。
  一次只调用一个工具或 finish；等这条 observation 回来再输出下一个 JSON。
  device_id、room_id 必须来自已经出现过的观察，不要编造。
  最多 10 步，第 10 步前必须交 finish。

观察怎么用
  observe_home     只有房间 id 和名称；没有设备、没有温湿度
  inspect_room     该房间的设备清单，拿到 device_id；没有档位和范围
  inspect_device   一台设备的 state 和 actions（含 min/max/step/enum）
  execute_action   只能用这台设备 actions 里刚看到的动作和参数
  finish           结束 episode，不是家庭写入

还没 inspect_device，不要 execute_action。
温度、模式、百分比以那台设备 actions 为准，不要默认 7–32。

设备常识（以 inspect_device 的自报为准）
  灯      主灯 turn_on / turn_off / set_mode，mode 只有 dim 或 bright，没有 set_percentage
          台灯 turn_on / turn_off / set_percentage 0–100
          夜灯、廊灯、厨灯、浴灯、阳台灯只有开关
  气候    空调 on/mode/target；风扇 on/level
  家电    电视 on/mode/level；热水器 on/mode/target；洗衣机、洗碗机 on/mode
          烤箱 on/mode/target；冰箱 on/target；加湿器只有开关
  传感器  只读，没有动作
  动作名只有 turn_on / turn_off / set_mode / set_temperature / set_percentage
  不要发明 set_brightness、set_volume 这类别名

连续量（空调、热水器、烤箱、冰箱的 target，台灯、电视、风扇的 level）
  温度走 set_temperature.value，音量、亮度走 set_percentage.value
  人说调高一点、声音小一点、再凉快一点，在当前值上按 step 改一档即可，不必猜二十六或八十
  只 turn_on / turn_off 不会改这些字段

加湿器只有开关，没有 set_percentage。人说干就打开，人说潮就关掉。

越界或传感器
  目标超出这台设备的能力：先 inspect 到范围，再一次 finish
  finish 写 {"summary":"为什么做不到","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}
  传感器用 READ_ONLY_DEVICE
  不要先把数值写成上限再拒绝，不要改成关设备来「避免过热」

finish
  summary 必填，用短句说做了什么或为什么拒绝，同一事实只说一次
  outcome 只许 completed 或 refused；拒绝时加 reason_code
  不要 facts，不要 answered
  查询题没读到传感器：completed，在 summary 里说没读到，不要 refused

可用工具：
[{"name": "observe_home", "description": "查看房间 id 和名称；不返回设备、不返回温湿度。", "parameters": {"type": "object", "properties": {}, "additionalProperties": false}}, {"name": "inspect_room", "description": "查看一个房间的全部设备摘要并获取 device_id。", "parameters": {"type": "object", "properties": {"room_id": {"type": "string"}}, "required": ["room_id"], "additionalProperties": false}}, {"name": "inspect_device", "description": "查看一台设备的完整公开状态和 actions 参数范围。", "parameters": {"type": "object", "properties": {"device_id": {"type": "string"}}, "required": ["device_id"], "additionalProperties": false}}, {"name": "execute_action", "description": "执行设备 actions 中公开的规范动作；传感器没有可执行动作。", "parameters": {"type": "object", "properties": {"device_id": {"type": "string"}, "action": {"type": "string"}, "params": {"type": "object"}}, "required": ["device_id", "action", "params"], "additionalProperties": false}}, {"name": "finish", "description": "结束当前 episode。公开字段是 summary 和 outcome；拒绝时再加 reason_code。不是家庭写命令。", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "outcome": {"type": "string", "enum": ["completed", "refused"]}, "reason_code": {"type": "string"}}, "required": ["summary"], "additionalProperties": false}}]
```

### 1.2 few-shot 消息（24 条，原文）

```text
[ 1] user      下面用三段示例演示工具流程；示例不是真实环境，真实任务必须先用工具观察。
示例一：把卧室台灯关掉。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"},{"room_id":"room_living","display_name":"客厅"}]}}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","devices":[{"device_id":"device_bedroom_lamp","display_name":"卧室台灯"}]}}}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_lamp"}}
[ 7] user      observation: {"ok":true,"data":{"device":{"device_id":"device_bedroom_lamp","state":{"on":true,"level":80},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}]}}}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_lamp","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok":true,"data":{"changed":true,"state_after":{"on":false,"level":80}}}
[10] assistant {"name":"finish","arguments":{"summary":"卧室台灯已关闭。","outcome":"completed"}}
[11] user      示例二：把卧室空调调到三度。
[12] assistant {"name":"observe_home","arguments":{}}
[13] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"}]}}
[14] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[15] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","devices":[{"device_id":"device_bedroom_climate","display_name":"卧室空调"}]}}}
[16] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[17] user      observation: {"ok":true,"data":{"device":{"device_id":"device_bedroom_climate","state":{"on":true,"target":27.0},"actions":[{"action":"set_temperature","params":{"value":{"minimum":7.0,"maximum":32.0,"step":0.5}}}]}}}
[18] assistant {"name":"finish","arguments":{"summary":"三度低于可调下限七度，无法设置，未做修改。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
[19] user      示例三：卧室现在多少度？
[20] assistant {"name":"observe_home","arguments":{}}
[21] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"}]}}
[22] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[23] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","environment":{"temperature":24.5},"devices":[{"device_id":"sensor_bedroom_env","display_name":"卧室温湿度传感器"}]}}}
[24] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

### 1.3 真实任务包装（本轮以 sc_T1_001 为例）

```text
以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
[TASK] 回到家了，把主卧主灯关掉吧。
按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；一次只调一个工具；最多 12 步，尽快交 finish。
```

## 2 三轮对比（同一批 12 条）

```text
指标                      v0 无     v1 平铺   v2 SimuHome
C 四项全过                     0         4             3
起手 observe_home            0        12            12
UNKNOWN_DEVICE 次数         15         0             0
用未见过 id 执行                13         0             0
```

逐条 C 标签（C-1/C-2/C-3/C-4，1=过 0=挂）：

```text
task        cat     v0    v1    v2
sc_T1_002   T1    1010  1111  1111
sc_T1_001   T1    1010  1111  1011
sc_T2_006   T2    1010  1011  1011
sc_T1_003   T1    1010  1011  1010
sc_T2_002   T2    1010  1011  0010
sc_T2_005   T2    1010  1011  1011
sc_T3_001   T3    1010  1010  1111
sc_T3_002   T3    1010  1011  1011
sc_T4_001   T4    1100  1100  1110
sc_T5_002   T5    1110  1111  1110
sc_T5_001   T5    1110  1111  1111
sc_T4_002   T4    1101  1110  1110
```

## 3 结论

```text
1  few-shot 的价值主要在协议合规
   v0 → v1/v2：起手 observe_home 0 → 12，UNKNOWN_DEVICE 15 → 0，
   用未见过 id 直接执行 13 → 0；C-4（finish 契约）大面积从挂变过。

2  v1 与 v2 在 12 条小样本上互有胜负（4 vs 3 条全过），差距在噪声范围；
   v2 的价值是把 SimuHome 那套「示例 + 真实任务重申规则」的结构固定下来，
   并且顺手修正了「最多 10 步」与 12 轮上限的不一致（在真实任务包装里写 12 步）。

3  剩余主要失败：C-2 终态没做到（T2 多设备条件、T3 方向落实），
   与提示词结构无关，是 1.5B 的执行精度问题；T4 还需把「先 inspect 被拒设备」演给模型看。
```

## 4 文件

```text
v0 无 few-shot   new_demo/runs/qwen15b_eval_12/
v1 平铺示例      new_demo/runs/qwen15b_eval_12_fewshot/
v2 SimuHome风格  new_demo/runs/qwen15b_eval_12_fewshot_v2/
runner           new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py（--few-shot）
```
