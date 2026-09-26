# `homeflow_demo/data/build_v1_2_dataset.py` 说明

## 职责

构建 V1.2 的 80/20/40 场景和 Oracle 参考轨迹，并生成统计清单。旧 `data_processed/v1/` 不读取、不修改。

```text
ScenarioGenerator
  -> scenarios_train/val/eval.jsonl
  -> OraclePolicy + EpisodeRunner
  -> oracle_trajectories_train/val/eval.jsonl
  -> manifest.json + manifest.md
```

## 输入输出

```text
输入：--output-dir，--seed，--generated-on
默认输出：homeflow_demo/data_processed/v1.2/

train：80 条
val：  20 条
eval： 40 条
```

manifest 保存八类任务分布、可行/不可行数量、Oracle 成功率、SFT 接收率、错误统计和整个数据集的稳定 SHA-256。
`--generated-on` 默认是本次 V1.2 交付日期 `2026-09-23`。

## 运行

```bash
cd /root/autodl-tmp
python -m homeflow_demo.data.build_v1_2_dataset
```
