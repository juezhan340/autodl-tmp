# `homeflow_demo/data/trajectory_format.py` 说明

## 职责

定义 V1.2 turn-level 轨迹记录和稳定 JSONL 读写。新格式直接保存 C 的统一评测结果，不再保留 V1 的动作级 `transitions` 双轨结构。

```text
TrajectoryRecord
  format_version = v1.2-turn
  scenario_id / model_id / source / feasible
  turns[]
  final_state
  evaluation
  metadata / reset_info
```

## 输入输出

```text
write_jsonl(path, records) -> 写入条数
read_jsonl(path) -> 字典列表
stable_fingerprint(record) -> 忽略 elapsed_ms 后的稳定 SHA-256
```

文件使用 UTF-8，JSON 键稳定排序。指纹排除机器负载相关的 `elapsed_ms`，因此相同 seed 的重复构建不会因耗时波动改变摘要。读取到非对象记录或无效 JSON 时，异常包含文件名和具体行号。
