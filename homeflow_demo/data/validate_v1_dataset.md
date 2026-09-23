# `homeflow_demo/data/validate_v1_dataset.py` 说明

## 职责

检查 V1/V1.1 场景和 Oracle 轨迹能否作为下一版本 DeepSeek 教师数据流水线的输入，并重放所有可行 turn-level Oracle 轨迹。

## 输入

```text
--root：V1 数据目录，默认 homeflow_demo/data_processed/v1
```

## 输出

报告字段包括：

```text
每个 split 的场景数和 Oracle 数
Oracle 成功数
Oracle 轨迹重放结果
turn_index 连续性、assistant_output 和 tool_events
重复 scenario_id
可行场景失败记录
valid
```

## 运行方式

```bash
python -m homeflow_demo.data.validate_v1_dataset
```
