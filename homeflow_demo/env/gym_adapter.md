# `homeflow_demo/env/gym_adapter.py` 说明

## 职责

提供可选的 Gymnasium 形状，不让核心 HomeEnv 依赖 Gymnasium。

```text
reset(options={scenario}) -> observation, info
step(ToolCall)            -> observation, 0.0, False, False, info
```

这里的 reward/terminated/truncated 固定为中性值，因为 V1.2 的回合、隐藏目标和奖励统一归 C 模块管理。RL 训练应直接接 C，不应把本适配器当作最终奖励源。
