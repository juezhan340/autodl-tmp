# `homeflow_demo/agents/deepseek_policy.py` 说明

## 职责

实现 A 模块的 DeepSeek 策略适配器。每个 C turn 发起一次独立 completion，模型输出交给 `EpisodeRunner.parse_assistant_response()` 解析；策略适配器不直接调用 HomeEnv，也不读取 hidden truth。

```text
C context
  ├── observation
  ├── tools
  ├── history
  └── protocol_feedback
       -> DeepSeekPolicy
       -> OpenAI 兼容 raw response
       -> C 解析、反馈、调用 B
```

## 输入输出

```text
respond(context)
  输入：当前 turn、公开 observation、工具 schema、历史和协议反馈
  输出：DeepSeek chat completion 原始字典
```

system prompt 强制一次只产生一个工具调用，并要求 `call_id` 和结构化 `finish`。它说明 `observe_home` 不返回 `device_id`，但不把发现链写成环境闸门。格式错误仍由 C 计为一个 turn，并通过 `protocol_feedback` 返回下一轮。
