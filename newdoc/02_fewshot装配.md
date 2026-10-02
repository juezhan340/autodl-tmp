# newdoc 02　few-shot 装配与对比

> 合并自 `07`、`11`、`10`、`12`、`15`。记录 few-shot 从 SimuHome 风格引入、跑批版逐条全文、每类三条设计稿、两轮 100 条对比与 2×2 验证。

---

# 一、few-shot v2 设计（SimuHome 风格）+ 12 条对比

> 来源：newdoc/07_fewshot对比_12条.md（原文逐字，仅标题层级下调一级）

## 本地 Qwen2.5-1.5B：few-shot 提示词 v2（SimuHome 风格）+ 12 条对比

> 服务：llama.cpp b10991（Vulkan）、Qwen2.5-1.5B-Instruct Q8_0、2 slot × 32K、端口 18080
> 评测：同一批 12 条任务、2 路并发、12 轮上限；`D0_templates` 主提示词未改动
> few-shot 只存在于评测 runner：`run_local_eval.py --few-shot`

### 0 新版设计（对照 SimuHome）

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

### 1 v2 的 A 侧完整提示词

#### 1.1 system（A_policy.md 渲染后全文，含工具 schema）

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

#### 1.2 few-shot 消息（24 条，原文）

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

#### 1.3 真实任务包装（本轮以 sc_T1_001 为例）

```text
以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
[TASK] 回到家了，把主卧主灯关掉吧。
按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；一次只调一个工具；最多 12 步，尽快交 finish。
```

### 2 三轮对比（同一批 12 条）

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

### 3 结论

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

### 4 文件

```text
v0 无 few-shot   new_demo/runs/qwen15b_eval_12/
v1 平铺示例      new_demo/runs/qwen15b_eval_12_fewshot/
v2 SimuHome风格  new_demo/runs/qwen15b_eval_12_fewshot_v2/
runner           new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py（--few-shot）
```


---

# 二、跑批版全文（100 条那次实际注入的示例）

> 来源：newdoc/11_分类fewshot_跑批版全文.md（原文逐字，仅标题层级下调一级）

## 分类 few-shot：100 条跑批所用版本（逐条全文）

> 来源：`new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/`
> 这是 `runs/qwen15b_eval_100_fs_by_task/` 那次评测（100 条、46 条全过）实际注入的示例。
> 每类的示例数不强行统一：T1 两个示例，T2/T3/T4/T5 各一个示例；消息条数随工具步数变化。
> 本文件只做展示，不改文件、不跑评测。

### 0 组装方式

```text
A 侧 messages = [system（A_policy.md 渲染后）]
             + [该类的 few-shot 消息（见下）]
             + [包装过的真实任务 user]

真实任务包装：
以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
[TASK] <user_request>
按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；一次只调一个工具；最多 12 步，尽快交 finish。
```

### 消息条数一览

```text
T1: 20 条消息
T2: 16 条消息
T3: 10 条消息
T4: 8 条消息
T5: 6 条消息
```

### T1（20 条消息）

```text
[ 1] user      示例一（精确控制）：把卧室台灯关掉。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_lamp", "display_name": "卧室台灯"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_lamp"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_lamp", "state": {"on": true, "level": 80}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_lamp", "action": "turn_off", "params": {}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_lamp", "action": "turn_off", "state_after": {"on": false, "level": 80}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"卧室台灯已关闭。","outcome":"completed"}}
[11] user      示例二（方向控制）：卧室有点热，空调调低一点。
[12] assistant {"name": "observe_home", "arguments": {}}
[13] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[14] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[15] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[16] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[17] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}, {"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}}}, {"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[18] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[19] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[20] assistant {"name":"finish","arguments":{"summary":"卧室空调调低了一档。","outcome":"completed"}}
```

### T2（16 条消息）

```text
[ 1] user      示例（多设备控制）：睡前把客厅电视关掉，卧室空调调低一点，卧室加湿器别动。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_tv", "display_name": "客厅电视"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_living_tv"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_tv", "state": {"on": true, "mode": "tv", "level": 40}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}, {"action": "set_percentage", "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_living_tv", "action": "turn_off", "params": {}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_living_tv", "action": "turn_off", "state_after": {"on": false, "mode": "tv", "level": 40}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[11] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}, {"device_id": "device_bedroom_humidifier", "display_name": "卧室加湿器"}]}}, "error": null}
[12] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[13] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[14] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[15] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[16] assistant {"name":"finish","arguments":{"summary":"客厅电视已关闭，卧室空调调低了一档；卧室加湿器没有动。","outcome":"completed"}}
```

### T3（10 条消息）

```text
[ 1] user      示例（模糊意图）：屋里像蒸笼，睡不着。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 26.5}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"屋里闷，卧室空调已调低一档。","outcome":"completed"}}
```

### T4（8 条消息）

```text
[ 1] user      示例（做不到的目标）：把卧室空调调到三度。
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"三度低于可调下限七度，没有改温度。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
```

### T5（6 条消息）

```text
[ 1] user      示例（查询）：卧室现在多少度？
[ 2] assistant {"name": "observe_home", "arguments": {}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "environment": {"temperature": 24.5}, "devices": [{"device_id": "sensor_bedroom_env", "display_name": "卧室温湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

### 文件

```text
示例目录   new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/（T1–T5.json + .md + README）
跑批结果   new_demo/runs/qwen15b_eval_100_fs_by_task/（100 条，46 条 C 四项全过）
对比报告   newdoc/09_分类fewshot_100条.md
```


---

# 三、每类三条设计稿（v3）

> 来源：newdoc/10_每类三条fewshot_设计稿.md（原文逐字，仅标题层级下调一级）

## 每类三条 few-shot 设计稿（v3，待审）

> 目的：把 T1–T5 的 few-shot 统一成「每类三条示例、内容各不相同」。
> 现状：T1 两个示例（20 条消息），T2/T3/T4/T5 各一个示例（16/10/8/6 条消息）。
> 本文件只做展示：不改 `fewshot_by_task/`，不跑评测。

```text
T1  三条：eq 开关 / eq 模式 / le 方向
T2  三条：两条件+keep / 开关+模式 / 混合 eq+le
T3  三条：热闷→空调 / 潮→关加湿器 / 刺眼→主灯调暗
T4  三条：数值越界 / 传感器只读 / 冰箱越界
T5  三条：房间读数 / 传感器读数 / 设备状态
```

### T1（3 例，共约 30 条消息）

#### T1-1  示例一（eq·开关）：把卧室台灯关掉。

```text
[ 1] user      把卧室台灯关掉。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}, {"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_lamp", "display_name": "卧室台灯"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_lamp"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_lamp", "state": {"on": true, "level": 80}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_lamp","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_lamp", "action": "turn_off", "state_after": {"on": false, "level": 80}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"卧室台灯已关闭。","outcome":"completed"}}
```

#### T1-2  示例二（eq·模式）：把客厅主灯调暗。

```text
[ 1] user      把客厅主灯调暗。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_light", "display_name": "客厅主灯"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_living_light"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_light", "state": {"on": true, "mode": "bright"}, "actions": [{"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["dim", "bright"]}}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_living_light","action":"set_mode","params":{"mode":"dim"}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_living_light", "action": "set_mode", "state_after": {"on": true, "mode": "dim"}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"客厅主灯已调到暗档。","outcome":"completed"}}
```

#### T1-3  示例三（le·方向）：卧室有点热，空调调低一点。

```text
[ 1] user      卧室有点热，空调调低一点。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_climate","action":"set_temperature","params":{"value":26.5}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"卧室空调调低了一档。","outcome":"completed"}}
```

### T2（3 例，共约 46 条消息）

#### T2-1  示例一（两条件 + keep）：关电视、调低空调、加湿器别动。

```text
[ 1] user      睡前把客厅电视关掉，卧室空调调低一点，卧室加湿器别动。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_living", "display_name": "客厅"}, {"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_tv", "display_name": "客厅电视"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_living_tv"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_tv", "state": {"on": true, "mode": "tv", "level": 40}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_living_tv","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_living_tv", "action": "turn_off", "state_after": {"on": false, "mode": "tv", "level": 40}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[11] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}, {"device_id": "device_bedroom_humidifier", "display_name": "卧室加湿器"}]}}, "error": null}
[12] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[13] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[14] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_climate","action":"set_temperature","params":{"value":26.5}}}
[15] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[16] assistant {"name":"finish","arguments":{"summary":"客厅电视已关闭，卧室空调调低了一档；卧室加湿器没有动。","outcome":"completed"}}
```

#### T2-2  示例二（开关 + 模式）：关电视、洗衣机快洗、冰箱别动。

```text
[ 1] user      把客厅电视关掉，卫生间洗衣机切快洗，厨房冰箱别动。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_living", "display_name": "客厅"}, {"room_id": "room_bath", "display_name": "卫生间"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_tv", "display_name": "客厅电视"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_living_tv"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_tv", "state": {"on": true, "mode": "tv", "level": 40}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_living_tv","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_living_tv", "action": "turn_off", "state_after": {"on": false, "mode": "tv", "level": 40}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"inspect_room","arguments":{"room_id":"room_bath"}}
[11] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bath", "devices": [{"device_id": "device_bath_washer", "display_name": "卫生间洗衣机"}]}}, "error": null}
[12] assistant {"name":"inspect_device","arguments":{"device_id":"device_bath_washer"}}
[13] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bath_washer", "state": {"on": false, "mode": "normal"}, "actions": [{"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["normal", "quick", "delicate", "rinse"]}}}]}}, "error": null}
[14] assistant {"name":"execute_action","arguments":{"device_id":"device_bath_washer","action":"set_mode","params":{"mode":"quick"}}}
[15] user      observation: {"ok": true, "data": {"device_id": "device_bath_washer", "action": "set_mode", "state_after": {"on": false, "mode": "quick"}, "verified": true, "changed": true}, "error": null}
[16] assistant {"name":"finish","arguments":{"summary":"客厅电视已关闭，洗衣机切到快洗模式；厨房冰箱没有动。","outcome":"completed"}}
```

#### T2-3  示例三（混合 eq + le）：主灯调暗、空调调低、台灯别动。

```text
[ 1] user      把卧室主灯调暗，卧室空调调低一点，卧室台灯别动。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_light", "display_name": "卧室主灯"}, {"device_id": "device_bedroom_climate", "display_name": "卧室空调"}, {"device_id": "device_bedroom_lamp", "display_name": "卧室台灯"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_light"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_light", "state": {"on": true, "mode": "bright"}, "actions": [{"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["dim", "bright"]}}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_light","action":"set_mode","params":{"mode":"dim"}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_light", "action": "set_mode", "state_after": {"on": true, "mode": "dim"}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[11] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[12] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_climate","action":"set_temperature","params":{"value":26.5}}}
[13] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[14] assistant {"name":"finish","arguments":{"summary":"卧室主灯已调到暗档，空调调低了一档；台灯没有动。","outcome":"completed"}}
```

### T3（3 例，共约 30 条消息）

#### T3-1  示例一（热/闷）：屋里像蒸笼，睡不着。

```text
[ 1] user      屋里像蒸笼，睡不着。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_climate","action":"set_temperature","params":{"value":26.5}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_climate", "action": "set_temperature", "state_after": {"on": true, "mode": "cool", "target": 26.5}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"屋里闷，卧室空调已调低一档。","outcome":"completed"}}
```

#### T3-2  示例二（潮）：身上黏糊糊的，潮得难受。

```text
[ 1] user      身上黏糊糊的，潮得难受。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_humidifier", "display_name": "卧室加湿器"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_humidifier"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_humidifier", "state": {"on": true}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_humidifier","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_humidifier", "action": "turn_off", "state_after": {"on": false}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"屋里潮，卧室加湿器已关掉。","outcome":"completed"}}
```

#### T3-3  示例三（刺眼）：灯刺得睁不开眼。

```text
[ 1] user      灯刺得睁不开眼。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_light", "display_name": "卧室主灯"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_light"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_light", "state": {"on": true, "mode": "bright"}, "actions": [{"action": "set_mode", "params": {"mode": {"type": "string", "enum": ["dim", "bright"]}}}]}}, "error": null}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_light","action":"set_mode","params":{"mode":"dim"}}}
[ 9] user      observation: {"ok": true, "data": {"device_id": "device_bedroom_light", "action": "set_mode", "state_after": {"on": true, "mode": "dim"}, "verified": true, "changed": true}, "error": null}
[10] assistant {"name":"finish","arguments":{"summary":"灯太亮，卧室主灯已调到暗档。","outcome":"completed"}}
```

### T4（3 例，共约 24 条消息）

#### T4-1  示例一（数值越界）：把卧室空调调到三度。

```text
[ 1] user      把卧室空调调到三度。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "device_bedroom_climate", "display_name": "卧室空调"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_bedroom_climate", "state": {"on": true, "mode": "cool", "target": 27.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"三度低于可调下限七度，没有改温度。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
```

#### T4-2  示例二（传感器只读）：把卧室温湿度传感器的温度设成二十度。

```text
[ 1] user      把卧室温湿度传感器的温度设成二十度。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "devices": [{"device_id": "sensor_bedroom_env", "display_name": "卧室温湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"sensor_bedroom_env"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "sensor_bedroom_env", "state": {"temperature": 30.0, "humidity": 35.0}, "actions": []}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"温湿度传感器是只读的，不能设置温度，未做修改。","outcome":"refused","reason_code":"READ_ONLY_DEVICE"}}
```

#### T4-3  示例三（数值越界）：把厨房冰箱调到零下五度。

```text
[ 1] user      把厨房冰箱调到零下五度。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_kitchen", "display_name": "厨房"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_kitchen"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_kitchen", "devices": [{"device_id": "device_kitchen_fridge", "display_name": "厨房冰箱"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_kitchen_fridge"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_kitchen_fridge", "state": {"on": true, "target": 4.0}, "actions": [{"action": "set_temperature", "params": {"value": {"type": "number", "minimum": 2.0, "maximum": 8.0, "step": 0.5}}}]}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"零下五度低于可调下限两度，没有改温度。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
```

### T5（3 例，共约 22 条消息）

#### T5-1  示例一（房间读数）：卧室现在多少度？

```text
[ 1] user      卧室现在多少度？
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "environment": {"temperature": 24.5}, "devices": [{"device_id": "sensor_bedroom_env", "display_name": "卧室温湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

#### T5-2  示例二（传感器读数）：卫生间现在湿度多少？

```text
[ 1] user      卫生间现在湿度多少？
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bath", "display_name": "卫生间"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bath"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bath", "devices": [{"device_id": "sensor_bath_humidity", "display_name": "卫生间湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"sensor_bath_humidity"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "sensor_bath_humidity", "state": {"humidity": 55.2}, "actions": []}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"卫生间现在湿度约 55%。","outcome":"completed"}}
```

#### T5-3  示例三（设备状态）：客厅电视现在开着吗？

```text
[ 1] user      客厅电视现在开着吗？
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_living", "display_name": "客厅"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_living"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_living", "devices": [{"device_id": "device_living_tv", "display_name": "客厅电视"}]}}, "error": null}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_living_tv"}}
[ 7] user      observation: {"ok": true, "data": {"device": {"device_id": "device_living_tv", "state": {"on": false, "mode": "tv", "level": 40}, "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}]}}, "error": null}
[ 8] assistant {"name":"finish","arguments":{"summary":"客厅电视现在关着。","outcome":"completed"}}
```



---

# 四、每类三条对比（100 条：46 vs 41）

> 来源：newdoc/12_每类三条对比_100条.md（原文逐字，仅标题层级下调一级）

## 每类三条 few-shot（doc 10）对比：1.5B 100 条

> 同一批 100 条任务（五类各 20）、2 路并发、12 轮上限、服务同前。
> A：跑批版（分类示例，T1 两个示例，T2/T3/T4/T5 各一个示例）→ 46/100。
> B：三条版（按 newdoc/10 装配，每类三条示例）→ 41/100。

### 0 总览

```text
指标                         跑批版       三条版
C 四项全过                      46        41
平均轮数                      5.87      5.51
```

### 1 分类别全过（每类 20）

```text
类别          跑批版       三条版
T1           14        17
T2            5         0
T3            3         3
T4            7         2
T5           17        19
```

三条版的 C 项通过数（/20）：

```text
类别      C-1   C-2   C-3   C-4
T1       20    17    20    20
T2       19     2    20    17
T3       20     3    20    19
T4       19    20    18     2
T5       20    20    20    19
```

### 2 结论

```text
1  每类统一三条并没有整体收益：46 → 41/100。
2  变好的：T1 14→17（三条把开关/模式/方向分开演），T5 17→19。
3  变差的：T2 5→0、T4 7→2。T2 的三条第 2/3 个示例引入了新模式（洗衣机 mode、
   主灯+空调混合），把 1.5B 的多设备执行带偏；T4 的三条里加了传感器/冰箱类，
   反而让拒绝契约（C-4）更不稳。
4  对 1.5B 来说，示例不是越多越好：按类别难点给 1–2 个最贴合的示例，比统一三条更稳。
```

### 3 文件

```text
跑批版   new_demo/runs/qwen15b_eval_100_fs_by_task/（46/100，当前 fewshot_by_task 已被三条版覆盖，重跑旧版需从 git 恢复）
三条版   new_demo/runs/qwen15b_eval_100_fs_by_task3/（41/100）
设计稿   newdoc/10_每类三条fewshot_设计稿.md
```


---

# 五、2×2 对比（装配 × 任务批）

> 来源：newdoc/15_装配x任务批_2x2对比.md（原文逐字，仅标题层级下调一级）

## 2×2 对比：装配版本 × 任务批（各 100 条，每类 20）

> 装配：11 版 = T1 两例、其余各一例（20/16/10/8/6 条消息）；三条版 = 每类三条（30/46/30/24/22）。
> 任务：A 批 = 每类前 20 条；B 批 = 每类第 21–40 条（两批不重叠）。
> 条件：同一个 llama-server（Q8_0、2 slot × 32K）、2 路并发、max_turns=12。

### 0 总览（C 四项全过 / 100）

```text
装配            A批      B批      合计/200
11版           46      44          90
三条版           41      44          85
```

### 1 分类别（每类 20）

```text
类别       11版A    11版B     三条A     三条B
T1         14      14      17      16
T2          5       2       0       4
T3          3       3       3       2
T4          7      10       2       3
T5         17      15      19      19
```

### 2 结论

```text
1  总体上两套装配几乎打平：11 版 90/200，三条版 85/200，差异在抽样噪声内。
2  按类别看，稳定性不同：
   T1  三条版更好（A 17 vs 14，B 16 vs 14）——把开关/模式/方向分开演有效。
   T4  11 版明显更好（A 7 vs 2，B 10 vs 3）——三条版里传感器/冰箱示例反而带偏。
   T5  三条版更好（A 19 vs 17，B 19 vs 15）——查询示例更全。
   T2  两批互有胜负（A：11 版 5 vs 0；B：三条版 4 vs 2）——仍是全场最弱。
   T3  两版都只有 2–3/20，方向落实是模型能力问题。
3  结论：示例数量不是主要变量；示例内容与类别难点的匹配度才是。
   若只选一版，11 版综合更稳（90 vs 85），尤其 T4。
```

### 3 文件

```text
11版×A  runs/qwen15b_eval_100_fs_by_task/       46/100
11版×B  runs/qwen15b_eval_100b_fs/              44/100
三条×A  runs/qwen15b_eval_100_fs_by_task3/      41/100
三条×B  runs/qwen15b_eval_100b_fs3/             44/100
任务清单 runs/_eval100_ids.txt（A 批）、_eval100b_ids.txt（B 批）
```


