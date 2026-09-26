# `homeflow_demo/agents/deepseek_client.py` 说明

## 职责

提供 HomeFlow Demo 的 DeepSeek OpenAI 兼容客户端。客户端只处理传输、重试、JSON 正文提取、并发计数和原始响应落盘，不决定任务是否正确。

```text
读取 homeflow_demo/.env.deepseek
  -> POST /chat/completions
  -> 返回 DeepSeekResponse
  -> 将 requests/responses 写入指定 data_raw 目录
```

## 输入

```text
messages：OpenAI chat messages
role：task_writer / task_reviewer / policy / trajectory_judge
request_id：幂等和审计用请求编号
temperature、max_tokens：本次调用覆盖参数
```

## 输出

`complete()` 返回 `DeepSeekResponse`，包括模型正文、usage、耗时和原始响应；`complete_json()` 进一步把正文解析成 JSON 对象。

传输失败、HTTP 429、网络超时和服务端错误会按配置有限重试。模型返回无法解析为 JSON 时返回 `INVALID_MODEL_JSON`，这属于模型输出或审查结果问题，不会伪装成网络错误。

## 安全边界

请求日志不写入 Authorization header 和 API key。客户端会记录模型正文和原始响应，供任务与轨迹审计使用；这些记录必须放在 `.gitignore` 覆盖的 `data_raw` 目录。

## 并发指标

`max_active_requests` 记录同一客户端观察到的最大并发请求数，用于本次五任务并发 smoke test 验证 DeepSeek 调用和本地 EpisodeRunner 是否真正并行。
