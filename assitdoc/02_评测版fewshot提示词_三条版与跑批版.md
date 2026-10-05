# 评测版 few-shot 提示词：三条版与跑批版（对齐评测代码）

> 记录时间：2026-10-05；对齐仓库状态：commit a38ceee
> 来源：`new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py`（现行评测代码）、
> `fewshot_by_task/T1..T5.json`（现仓库现存的跑批版注入文件）、
> `newdoc/1003及之前的文档/06_fewshot装配_设计稿与跑批版.md`（两版全文的历史记录）
> 本文只记录，不修改代码、不跑评测。

## 0 共同装配结构（两版共用）

```text
A 侧 messages = [system（A_policy.md 渲染 + 工具表）]
             + [该类别 few-shot 消息]
             + [包装后的真实任务 user]

开关：--few-shot 打开；--few-shot-dir 默认 fewshot_by_task/
      T1..T5.json 缺文件时回退到代码内置 FEWSHOT_MESSAGES（全局三例）
轮数：--max-turns（当年跑批 = 12）；每条 episode 独立 reset
```

代码原文（REAL_TASK_TEMPLATE + FewShotPolicy + few-shot 加载）：

```python
REAL_TASK_TEMPLATE = (
    "以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：\n"
    "[TASK] {user_request}\n"
    "按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；"
    "一次只调一个工具；最多 12 步，尽快交 finish。"
)

class FewShotPolicy(DeepSeekPolicy):
    """评测用策略：system + 该类示例 + 包装好的真实任务（对齐 SimuHome 的 one-shot 写法）。"""

    def __init__(self, client: DeepSeekClient, messages: list[dict] | None = None) -> None:
        """注入客户端与这一类专用的示例消息；缺省用内置全局示例。"""
        super().__init__(client)
        self._fewshot = list(messages) if messages else list(FEWSHOT_MESSAGES)

    def _start_episode(self, observation: dict, context: dict) -> None:
        """先按父类建 system+user，再插示例，并把真实用户话包成带规则的真实任务。"""
        super()._start_episode(observation, context)
        if len(self._messages) >= 2:
            user_request = str(self._messages[-1].get("content", ""))
            wrapped = {"role": "user", "content": REAL_TASK_TEMPLATE.format(user_request=user_request)}
            self._messages = [self._messages[0]] + self._fewshot + [wrapped]

def load_fewshot_map(fewshot_dir: str | Path) -> dict[str, list[dict]]:
    """按类别读 few-shot JSON；缺文件时回退到内置全局示例。"""
    base = Path(fewshot_dir)
    mapping: dict[str, list[dict]] = {}
    for category in ("T1", "T2", "T3", "T4", "T5"):
        path = base / f"{category}.json"
        if path.exists():
            mapping[category] = json.loads(path.read_text(encoding="utf-8"))
        else:
            mapping[category] = list(FEWSHOT_MESSAGES)
    return mapping
```

包装后的真实任务实际渲染（{user_request} 填入真实请求）：

```text
以上都是示例，示例环境和设备不是真实的。现在处理你的真实任务：
[TASK] {user_request}
按示例执行：每次只输出一个 JSON；先观察再操作；device_id、room_id 必须来自真实观察；一次只调一个工具；最多 12 步，尽快交 finish。
```

## 1 版本一：三条版（每类 3 个 few-shot 示例）

```text
结构：T1~T5 每类 3 个示例；设计稿标注消息数：
      T1 ≈30 条 / T2 ≈46 条 / T3 ≈30 条 / T4 ≈24 条 / T5 ≈22 条
用途：qwen15b_eval_100_fs_by_task3（41/100）+ qwen15b_eval_100b_fs3（44/100）
成绩：85/200
说明：当年注入目录（fewshot_by_task）后来被跑批版覆盖；
      现存全文以 newdoc/1003及之前的文档/06 第一部分（设计稿 v3）为准。
```

### 三条版全文（逐字引用，自 newdoc/06 第一部分）

### 一、每类三条设计稿（v3）

> 来源：newdoc/10_每类三条fewshot_设计稿.md（原文逐字，仅标题层级下调一级）

#### 每类三条 few-shot 设计稿（v3，待审）

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

##### T1（3 例，共约 30 条消息）

###### T1-1  示例一（eq·开关）：把卧室台灯关掉。

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

###### T1-2  示例二（eq·模式）：把客厅主灯调暗。

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

###### T1-3  示例三（le·方向）：卧室有点热，空调调低一点。

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

##### T2（3 例，共约 46 条消息）

###### T2-1  示例一（两条件 + keep）：关电视、调低空调、加湿器别动。

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

###### T2-2  示例二（开关 + 模式）：关电视、洗衣机快洗、冰箱别动。

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

###### T2-3  示例三（混合 eq + le）：主灯调暗、空调调低、台灯别动。

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

##### T3（3 例，共约 30 条消息）

###### T3-1  示例一（热/闷）：屋里像蒸笼，睡不着。

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

###### T3-2  示例二（潮）：身上黏糊糊的，潮得难受。

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

###### T3-3  示例三（刺眼）：灯刺得睁不开眼。

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

##### T4（3 例，共约 24 条消息）

###### T4-1  示例一（数值越界）：把卧室空调调到三度。

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

###### T4-2  示例二（传感器只读）：把卧室温湿度传感器的温度设成二十度。

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

###### T4-3  示例三（数值越界）：把厨房冰箱调到零下五度。

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

##### T5（3 例，共约 22 条消息）

###### T5-1  示例一（房间读数）：卧室现在多少度？

```text
[ 1] user      卧室现在多少度？
[ 2] assistant {"name":"observe_home","arguments":{}}
[ 3] user      observation: {"ok": true, "data": {"rooms": [{"room_id": "room_bedroom", "display_name": "卧室"}]}, "error": null}
[ 4] assistant {"name":"inspect_room","arguments":{"room_id":"room_bedroom"}}
[ 5] user      observation: {"ok": true, "data": {"room": {"room_id": "room_bedroom", "environment": {"temperature": 24.5}, "devices": [{"device_id": "sensor_bedroom_env", "display_name": "卧室温湿度传感器"}]}}, "error": null}
[ 6] assistant {"name":"finish","arguments":{"summary":"卧室现在约 24.5 度。","outcome":"completed"}}
```

###### T5-2  示例二（传感器读数）：卫生间现在湿度多少？

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

###### T5-3  示例三（设备状态）：客厅电视现在开着吗？

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

## 2 版本二：跑批版（11 版；T1 两个示例，T2~T5 各一个示例）

```text
结构：消息数 T1 20 / T2 16 / T3 10 / T4 8 / T5 6
文件：new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/T1..T5.json（现仓库现存）
用途与成绩：qwen15b_eval_100_fs_by_task（46/100）+ 100b（44/100）→ 90/200；
            qwen3_17b_eval_200_fs 63/200；qwen35_2b_eval_200_fs 112/200
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

## 3 两版对比

```text
维度            三条版                跑批版（11 版）
示例数          每类 3 个              T1 两个，T2~T5 各一个
消息数          T1≈30/T2≈46/T3≈30/     T1 20/T2 16/T3 10/T4 8/T5 6
                T4≈24/T5≈22
200 条成绩      85/200                 90/200
T4 差异         拒绝理由码抄工具错误     T4 更稳（same 结构）
                11 → 27 条（退化）
结论            示例内容与类别难点的匹配度是关键，不是条数越多越好
```

## 4 附：内置全局 few-shot（回退示例，非上述两版）

```text
run_local_eval.py 的 FEWSHOT_MESSAGES：三例（台灯关灯 / 越界拒绝 / 温度查询）；
仅在某类别 JSON 缺失时作为回退使用；历史全局版成绩 34/100（对照）。
```

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

