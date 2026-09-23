# `homeflow_demo/data_processed/v1/manifest.json` 说明

## 功能

记录 V1.1 数据集的生成种子、数据划分、文件路径和每个 split 的统计信息。

## 数据内容

```text
format_version：v1.1-turn
seed：20260921
train：80 条场景，67 条可行 Oracle 成功轨迹
val：20 条场景，17 条可行 Oracle 成功轨迹
eval：40 条场景，33 条可行 Oracle 成功轨迹
总计：140 条场景，117 条可行 Oracle 成功轨迹
```

## 轨迹格式

```text
场景文件使用 max_turns 和 max_tool_calls_per_turn
Oracle 文件使用 turns 作为模型决策步主字段
每个 turn 内使用 tool_events 保存原子工具执行审计
旧 actions/transitions 字段仅用于兼容和调试
```

## 生成与验证

```bash
python -m homeflow_demo.data.build_v1_dataset \
  --output-dir homeflow_demo/data_processed/v1 \
  --seed 20260921

python -m homeflow_demo.data.validate_v1_dataset \
  --root homeflow_demo/data_processed/v1
```
