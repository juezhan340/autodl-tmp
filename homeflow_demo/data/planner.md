# `homeflow_demo/data/planner.py` 说明

## 职责

在不调用语言模型的情况下，为 V1 场景生成一条规则 Oracle 动作序列，并通过 V1.1 HomeEnv 执行验证。每个规则动作会被兼容包装为一个 synthetic assistant turn。

## 输入

```text
Scenario 对象或场景字典
```

## 输出

```text
plan_scenario -> PlanResult
run_oracle_episode -> JSON 可序列化轨迹字典，主字段为 turns
```

## 规划规则

```text
目标字段已满足：跳过控制
requires_query=True：先生成 query_device
目标字段未满足：映射到 control_device
目标值超出工具范围：feasible=False
所有目标完成后：追加 finish
每个原子规划动作：包装为一个 assistant turn，保留 tool_events
```

## 不负责

```text
不处理自然语言
不调用 DeepSeek
不搜索复杂动作树
不生成随机错误轨迹
```
