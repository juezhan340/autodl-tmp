# `homeflow_demo/data/trajectory_format.py` 说明

## 职责

定义 V1.1 turn-level 轨迹和旧 V1 动作级轨迹共用的 JSONL 序列化格式，避免数据生成、SFT 和评测各自维护不同字段。

## `TrajectoryRecord` 字段

```text
format_version：v1.1-turn 表示新契约
scenario_id：   场景 ID
source：        planner 或 deepseek
feasible：      场景是否可行
success：       本次执行是否完成目标
turns：         每个 assistant 输出一条，包含 assistant_output、tool_calls、tool_events、reward
final_result：  环境终局结果，包含 turns 和兼容字段 steps
metadata：      任务类型、split、seed 等元数据
```

旧字段保留：

```text
actions：      原子动作序列，供旧规划器和调试脚本读取
transitions：  旧动作级返回记录，不能作为新 RL 的策略步依据
```

新训练和在线 rollout 只读取 `turns`；`tool_events` 是审计事件，不是额外 transition。

## 输入输出

```text
write_jsonl(path, records) -> 写入条数
read_jsonl(path) -> 字典列表
```

文件编码固定为 UTF-8，JSONL 中保留中文，不写 Python 对象 repr。
