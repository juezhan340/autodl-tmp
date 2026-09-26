# `data_processed/v1.2/manifest.json` 说明

该文件记录 V1.2 场景与 Oracle 轨迹的版本、规模、任务覆盖、统一评测统计和稳定指纹。

```text
dataset_version: v1.2
format_version:  v1.2-turn
seed:            20260924
train: 80 条，Oracle 成功 60 条，SFT 接收 60 条
val: 20 条，Oracle 成功 16 条，SFT 接收 16 条
eval: 40 条，Oracle 成功 30 条，SFT 接收 30 条
dataset_fingerprint: 5ffd45205f1d7f42fff68be7d3b5ede099765b619de30b1ffed8bf64d9c02af9
```

场景文件是静态输入；Oracle 文件是由 C 驱动 A/B 后得到的完整 turn-level 轨迹。不可行任务保留为 rejected 轨迹，不进入 SFT。
