# `homeflow_demo/eval/episode_runner.py` 说明

## 职责

这是 C 模块的总控器，包住 A 和 B：

```text
C.reset -> B reset
循环：
  C -> A：observation、工具 schema、历史
  A -> C：厂商 assistant 响应
  C：解析为 AssistantTurn / ToolCall
  C -> B：规范化 ToolCall
  B -> C：ToolEvent、state_diff、下一 observation
C：记录 turn、计算 shaping reward、判断是否继续
C -> EpisodeEvaluator：隐藏目标、最终 reward、质量门禁
```

## 输入输出

```text
输入：Policy.respond(context)、Scenario
输出：EpisodeRun
      ├── trajectory：turn-level 全轨迹
      └── evaluation：EpisodeEvaluation
```

## 解析边界

支持统一 `{name, arguments}`、单个 JSON 调用和 OpenAI 兼容 `function.name/function.arguments`。模型消息解析由 C 完成；设备动作含义和参数范围由 B 校验。

纯文本终答会规范化为 `finish`，与结构化 finish 调用进入同一终止路径。

如果 DeepSeek 以 `message.content` 返回 JSON 工具调用，C 会先尝试解码为统一 `ToolCall`；普通纯文本仍然规范化为 summary-only 的 `finish`。格式错误和工具错误会进入下一回合的 `protocol_feedback`，并消耗当前 turn。

厂商或统一响应必须提供 `id/call_id`；C 不为缺失 ID 的工具调用静默补值，缺失时按 `BAD_REQUEST` 记录协议错误。

C 不拦截同一输出里的 observe / inspect / execute。发现链不是状态机规则。外部模型仍然需要先查，因为 `observe_home` 不返回 `device_id`。

`finish` 由 C 处理，不发送给 B。它只结束 episode，不属于家庭设备语义写操作。

`finish` 的完整参数会保存到轨迹的 `finish_payload` 和终止事件中，供 answered/refused 的确定性契约检查以及后续语义裁判读取。

`valid_action` 只奖励实际产生 `state_diff` 的合法控制；重复设置相同状态只承担工具成本，避免无效动作获得正收益。

`goal_progress` 使用 conditions 完成度的有符号变化：推进目标为正，破坏已完成目标为负。
