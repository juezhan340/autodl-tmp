# B_models.py

职责：
  定义家庭、场景、工具调用和 B 一步结果的数据结构。user_request 在 Scenario 顶层，不进 task。

输入：
  已通过 schema 的 JSON 字典。

输出：
  不可变的 Home / Scenario / ToolCall / ToolEvent / EnvStepResult。

读取：
  无外部文件。

写入：
  无。只做内存对象。

不负责：
  校验对错（B_schema）、执行动作（B_state_engine）、打 C 标签。

对应文件：
  new_demo/env/B_models.py

Scenario 六项：

```text
scenario_id
blueprint_id     循环不读，只追溯
home             s0
user_request     顶层
task             intent / conditions / keep / required_observations / expected_finish
episode_config   默认 max_turns=10，每轮 1 个工具
```

runtime_state 用的设备字典不含 actions。finish 公开字段是 summary + outcome，拒绝再加 reason_code。
