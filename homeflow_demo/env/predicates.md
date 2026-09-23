# `homeflow_demo/env/predicates.py` 说明

## 职责

根据当前设备状态评估场景中的目标谓词，提供环境完成度和终局成功判定。

## 输入

```text
GoalPredicate 列表
StateEngine.devices 返回的设备状态
```

## 输出

```text
PredicateResult.completion：满足谓词数量 / 总谓词数量
PredicateResult.satisfied：已满足条件明细
PredicateResult.unsatisfied：未满足条件明细
PredicateResult.success：是否全部满足
```

## 示例

```text
目标：bedroom.light.power == off
实际：bedroom.light.power == on
结果：completion=0.0，success=False
```

## 不负责

```text
不修改设备状态
不解析工具调用
不计算非法动作惩罚
```

