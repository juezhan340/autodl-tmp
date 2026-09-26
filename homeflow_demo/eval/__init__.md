# `homeflow_demo/eval/__init__.py` 说明

集中导出 C 模块的回合、解析和隐藏评测接口。

```text
EpisodeRunner：管理 A/B 回合
EpisodeEvaluator：读取隐藏真值并统一评测
EpisodeEvaluation：跨数据筛选、SFT、RL、冻结测评复用
parse_assistant_response：厂商消息 -> AssistantTurn
apply_trajectory_quality：重放验证 + SFT 数据门禁
summarize_episode_records：小批量统一指标
audit_episode：确定性结果摘要
DeepSeekTrajectoryJudge：查询、拒绝和模糊意图语义裁判
```
