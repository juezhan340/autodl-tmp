# `homeflow_demo/env/predicates.py` 说明

## 职责

给 C 的 `EpisodeEvaluator` 提供隐藏条件计算。它读取 B 的运行状态深拷贝，不修改设备。

```text
输入：conditions / keep + runtime_state
支持：eq、ne、gt、ge、lt、le、in
输出：completion、satisfied、unsatisfied、success
```

空 `keep` 视为全部保持成功；可行任务的 `conditions` 在 schema 层要求非空。
