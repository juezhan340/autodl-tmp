# 本地 Qwen2.5-1.5B：few-shot 对比（12 条）

> 两轮完全相同的 12 条任务、同服务（Vulkan、Q8_0、2 slot × 32K）、2 路并发、12 轮上限。
> 唯一差别：第二次在评测会话的 system 与用户话之间插入了三段 few-shot（控制/拒绝/查询）。
> 主提示词文件 `new_demo/data_static/D0_templates/` 未改动；few-shot 只存在于评测 runner（`--few-shot`）。

## 0 总量对比

```text
指标                   无few-shot   有few-shot
C 四项全过                       0           4
起手 observe_home              0          12
UNKNOWN_DEVICE 次数           15           0
用未见过 id 执行                  13           0
```

## 1 逐条对比

```text
task        cat     轮数 无/有  C标签 无few-shot           C标签 有few-shot           
sc_T1_002   T1     3/4     1010                    1111                    
sc_T1_001   T1     1/5     1010                    1111                    
sc_T2_006   T2     1/5     1010                    1011                    
sc_T1_003   T1     9/4     1010                    1011                    
sc_T2_002   T2     1/5     1010                    1011                    
sc_T2_005   T2     1/5     1010                    1011                    
sc_T3_001   T3     2/6     1010                    1010                    
sc_T3_002   T3     2/5     1010                    1011                    
sc_T4_001   T4     4/5     1100                    1100                    
sc_T5_002   T5     1/3     1110                    1111                    
sc_T5_001   T5     1/5     1110                    1111                    
sc_T4_002   T4     5/5     1101                    1110                    
```

（C 标签顺序固定为 C-1/C-2/C-3/C-4；1 = 过，0 = 挂）

## 2 变化点

```text
变好
  sc_T1_001  0000 → 1111   先 observe→inspect→execute，finish 契约正确
  sc_T1_002  0100 → 1111
  sc_T5_001  1110 → 1111   查询链路走通，summary 带读数
  sc_T5_002  1110 → 1111
  sc_T1_003  0100 → 0111   不再编 id，C-2 仍差方向落实
  sc_T2/3 多条  末位 C-4 从 0 → 1，finish 契约被 few-shot 教会

仍挂的点
  T2 ×3      C-2：多设备条件没有全部做到（方向/模式落实不完整）
  T3 ×2      C-2：模糊意图的方向没落到目标字段
  T4 ×2      C-3/C-4：没先 inspect 被拒设备，或拒绝说明不贴范围
```

## 3 样例：sc_T1_001（无 → 有）

```text
无few-shot：1 轮  finish
    finish：{"summary": "{\"name\": \"execute_action\", \"arguments\": {\"device_id\": \"加湿器\", \"action\": \"turn_on\", \"params\": {}}}\n{\"name\": \"finish\", \"arguments\": {\"summary\": \"加湿器被开启\", \"outcome\": \"completed\"}}"}
有few-shot：5 轮  observe_home>inspect_room>inspect_device>execute_action>finish
    finish：{"summary": "客厅加湿器已开启。", "outcome": "completed"}
```

## 4 文件

```text
无 few-shot   new_demo/runs/qwen15b_eval_12/
有 few-shot   new_demo/runs/qwen15b_eval_12_fewshot/
              results.jsonl / trajectories.jsonl / api/completions.jsonl / summary.json
```

## 5 加完 few-shot 的 A 侧完整提示词

说明：`A_policy.md` 本体没有改。few-shot 是评测 runner 在 system 与真实用户话之间插入的
24 条消息；下面是实际发给本地模型的完整 A 侧结构。

### 5.1 system（A_policy.md 渲染后全文，含工具 schema）

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

### 5.2 few-shot 消息（24 条，原文）

```text
[ 1] user      把卧室台灯关掉。
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"},{"room_id":"room_living","display_name":"客厅"}]}}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","devices":[{"device_id":"device_bedroom_lamp","display_name":"卧室台灯"}]}}}
[ 6] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_lamp"}}
[ 7] user      observation: {"ok":true,"data":{"device":{"device_id":"device_bedroom_lamp","state":{"on":true,"level":80},"actions":[{"action":"turn_on","params":{}},{"action":"turn_off","params":{}}]}}}
[ 8] assistant {"name":"execute_action","arguments":{"device_id":"device_bedroom_lamp","action":"turn_off","params":{}}}
[ 9] user      observation: {"ok":true,"data":{"changed":true,"state_after":{"on":false,"level":80}}}
[10] assistant {"name":"finish","arguments":{"summary":"卧室台灯已关闭。","outcome":"completed"}}
[11] user      把卧室空调调到三度。
[12] assistant {"name":"observe_home","arguments":{}}
[13] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"}]}}
[14] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[15] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","devices":[{"device_id":"device_bedroom_climate","display_name":"卧室空调"}]}}}
[16] assistant {"name":"inspect_device","arguments":{"device_id":"device_bedroom_climate"}}
[17] user      observation: {"ok":true,"data":{"device":{"device_id":"device_bedroom_climate","state":{"on":true,"target":27.0},"actions":[{"action":"set_temperature","params":{"value":{"minimum":7.0,"maximum":32.0,"step":0.5}}}]}}}
[18] assistant {"name":"finish","arguments":{"summary":"三度低于可调下限七度，无法设置，未做修改。","outcome":"refused","reason_code":"OUT_OF_SAFE_RANGE"}}
[19] user      卧室现在多少度？
[20] assistant {"name":"observe_home","arguments":{}}
[21] user      observation: {"ok":true,"data":{"rooms":[{"room_id":"room_bedroom","display_name":"卧室"}]}}
[22] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[23] user      observation: {"ok":true,"data":{"room":{"room_id":"room_bedroom","environment":{"temperature":24.5},"devices":[{"device_id":"sensor_bedroom_env","display_name":"卧室温湿度传感器"}]}}}
[24] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

### 5.3 实际消息序列

```text
[system]      见 5.1
[few-shot]    第 1–24 条，见 5.2
[user]        本轮真实用户话（评测集里的 user_request）
之后每轮       assistant 输出 + observation 追加，直到 finish 或 12 轮
```
