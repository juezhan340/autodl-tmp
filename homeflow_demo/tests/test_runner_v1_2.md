# `homeflow_demo/tests/test_runner_v1_2.py` 说明

## 覆盖范围

```text
Oracle 成功轨迹：success + replayable + accepted_for_sft
只读传感器失败：strategy_error + replayable + rejected
finish 后多余调用：post_terminal_action
同一 turn 内 observe 后 inspect 允许执行
OpenAI function call 与纯文本 finish 规范化
缺失 call_id：协议错误
UNKNOWN_DEVICE / DEVICE_UNAVAILABLE / SERVICE_ERROR 三类归因分离
设备离线导致 environment_failure 和 episode 截断，不惩罚策略；截断轨迹仍可确定性重放
```

测试通过 `EpisodeRunner` 走完整 A/C/B 路径，不直接伪造最终评测结果。
