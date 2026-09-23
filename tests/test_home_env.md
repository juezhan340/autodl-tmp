# `tests/test_home_env.py` 说明

## 功能

验证 HomeEnv V1.1 的 turn-level 行为契约，并覆盖旧 Action 兼容路径。

## 测试内容

```text
test_successful_episode：       合法控制后 finish 成功
test_invalid_action_does_not_mutate_state：非法动作不改状态
test_snapshot_restore：         快照可以恢复设备和轨迹
test_fork_is_independent：      rollout 分支相互隔离
test_max_steps_truncates_episode：达到最大步数正确截断
test_finish_before_goal_terminates_with_failure：提前 finish 返回失败
test_already_satisfied_goal_can_finish：初始目标已满足时允许 finish
test_invalid_json_is_recorded_without_state_change：非法 JSON 不改状态
test_query_unknown_field_is_rejected：未知查询字段被拒绝
test_step_after_termination_requires_reset：终止后必须 reset
test_normalize_action_accepts_json：JSON 动作可标准化
test_multi_tool_turn_creates_one_transition：多个工具调用只生成一条策略转移
test_new_max_turns_reports_turn_failure_reason：新字段按 MAX_TURNS 截断
test_empty_turn_is_recorded_as_one_invalid_transition：空 turn 被记录为非法转移
test_tool_call_limit_rejects_whole_turn_without_state_change：超限 turn 不执行
```

## 运行方式

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

## 通过标准

```text
测试全部通过，且没有网络请求
不会读取或打印 DeepSeek API 密钥
```
