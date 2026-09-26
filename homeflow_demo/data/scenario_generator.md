# `homeflow_demo/data/scenario_generator.py` 说明

## 职责

按固定 seed 生成 V1.2 `Scenario`。每条数据包含完整 Home 快照、用户请求、隐藏 conditions/keep 和回合配置，生成后立即通过 `schema.py` 校验。

```text
固定家庭
  卧室：温湿度传感器、主灯、空调
  卫生间：湿度传感器、排风扇
  客厅：主灯
  厨房：插座
  书房：空房间，用于缺少目标设备任务

八类任务
  single_control / multi_control / query_then_control
  temperature_threshold / humidity_threshold
  correct_no_op / sensor_readonly / missing_device
```

温湿度阈值任务把传感器写入 `metadata.context_device_ids`，Oracle 会先发现并读取这些设备，再处理目标执行器。`sensor_readonly` 和 `missing_device` 标为不可行，用于验证拒绝轨迹和边界错误。

阈值初始值按同类任务的循环编号变化，训练、验证和测评中都会同时出现“超过阈值需要控制”和“未超过阈值正确不动作”分支。

## 输入输出

```text
ScenarioGenerator(seed).generate(count, split)
  输入：count，train|val|eval
  输出：通过 schema 校验的 Scenario 字典列表
```

同一个生成器连续生成三个 split 时，`scenario_id` 不重叠；相同 seed 和调用顺序得到相同数据。
