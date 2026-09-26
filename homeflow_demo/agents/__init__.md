# `homeflow_demo/agents/__init__.py` 说明

集中导出 A 模块的本地 Oracle、DeepSeek 客户端和 DeepSeek 策略适配器。

```text
OraclePolicy.respond(context) -> OpenAI 兼容 assistant message
DeepSeekClient.complete(messages) -> DeepSeekResponse
DeepSeekPolicy.respond(context) -> OpenAI 兼容 raw response
```
