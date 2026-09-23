# `homeflow_demo/env/gym_adapter.py` 说明

## 职责

把框架无关的 `HomeEpisodeEnv` 包装成 Gymnasium 风格的 `reset` 和 `step` 接口，方便后续环境检查、评测和传统强化学习工具使用。

## 输入

```text
reset(options={"scenario": scenario})
step(assistant_turn 或旧版 action)
```

## 输出

```text
reset -> observation, info
step  -> observation, reward, terminated, truncated, info
render -> 当前设备状态和轨迹
```

## 设计边界

```text
不强制安装 Gymnasium
不把变长文本 observation 转成数值向量
不负责 token 生成、logprob 或 GRPO
step 的五元组以 assistant turn 为一个决策步
```
