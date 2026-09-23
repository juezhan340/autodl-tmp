# `homeflow_demo/data/scenario_generator.py` 说明

## 职责

生成 V1 的训练、验证和测评场景。生成过程只使用本地规则和固定随机种子，不调用 DeepSeek。

## 输入

```text
seed：随机种子
count：场景数量
split：train、val 或 eval
```

## 输出

每条场景包含：

```text
scenario_id
seed
user_request
devices
goal.predicates
max_turns
max_tool_calls_per_turn
metadata
```

`metadata` 记录任务类型、设备组合、目标组合、语言变体组和是否可行。

## V1 任务类型

```text
single_control
multi_control
query_then_control
brightness_control
lock_control
impossible_temperature
```

## 可复现要求

```text
同一 seed、同一 count、同一 split 顺序 -> 相同场景内容
不修改 Python 全局随机数状态
每个场景的设备状态使用深拷贝，避免嵌套状态共享
```
