# `homeflow_demo/data/build_v1_dataset.py` 说明

## 职责

批量执行 V1.1 场景生成和规则 Oracle 轨迹执行，生成后续 DeepSeek 教师数据流水线的 turn-level 结构化输入。

## 输入

```text
--output-dir：输出目录，默认 homeflow_demo/data_processed/v1
--seed：      场景随机种子，默认 20260921
```

## 输出

```text
scenarios_train.jsonl
scenarios_val.jsonl
scenarios_eval.jsonl
oracle_trajectories_train.jsonl
oracle_trajectories_val.jsonl
oracle_trajectories_eval.jsonl
manifest.json
```

轨迹版本：

```text
format_version = v1.1-turn
scenarios 使用 max_turns
oracle 使用 turns 和 tool_events
```

## 生成规模

```text
train：80 条场景
val：20 条场景
eval：40 条场景
```

## 运行方式

```bash
python -m homeflow_demo.data.build_v1_dataset
```

## 失败行为

```text
场景 schema 不通过：直接抛出 SchemaValidationError
规划器判断不可行：保留场景和失败 Oracle 记录，不伪造成功轨迹
```
