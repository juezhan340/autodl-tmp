# `homeflow_demo/env/demo_scenario.py` 说明

## 功能

提供一个固定 V1.2 smoke 场景，验证完整发现链和隐藏评测。

```text
房间：卧室、客厅
卧室：温湿度传感器、主灯、空调
客厅：主灯

目标：关闭卧室灯；空调 target=24
保持：客厅灯继续开启
```

初始 observation 不包含设备 ID。策略需要先调用 `observe_home` 和 `inspect_room`，再通过 `inspect_device` 获取动作 schema。
