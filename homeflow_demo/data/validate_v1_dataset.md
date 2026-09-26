# `homeflow_demo/data/validate_v1_dataset.py` 说明

## 职责

对冻结的 `data_processed/v1/` 做只读文件级检查，不再用 V1.2 的 HomeEnv 解释旧协议。

```text
检查：文件存在、JSONL 可解析、场景与 Oracle 数量一致
      scenario_id 唯一、场景与轨迹 ID 对齐
不做：重写旧数据、运行旧环境、把旧轨迹迁移成 V1.2
```

V1.2 的语义、重放和评测验收请使用：

```bash
python -m homeflow_demo.data.validate_v1_2_dataset
```
