# `homeflow_demo/tests/test_data_v1_2.py` 说明

## 覆盖范围

```text
八条最小样本覆盖八类任务
温度/湿度阈值都覆盖 control 与 no_op 分支
80/20/40 完整构建可执行
相同 seed 的两次构建得到相同 dataset_fingerprint
140 条场景和轨迹全部通过全量重放与确定性验证
```

完整构建使用临时目录，不修改仓库中的正式 `data_processed/v1.2/`。
