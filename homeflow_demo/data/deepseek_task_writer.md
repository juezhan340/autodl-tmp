# `homeflow_demo/data/deepseek_task_writer.py` 说明

## 职责

调用 DeepSeek TaskWriter，把程序化 Blueprint 改写成三个自然语言用户请求候选。这个模块不修改隐藏真值、不编译 Scenario，也不判断候选是否真正覆盖目标。

```text
TaskBlueprint.writer_view
  -> DeepSeekTaskWriter
  -> TaskWriterResult.candidates
  -> StaticTaskValidator
  -> DeepSeekTaskReviewer
```

## 输入输出

```text
输入：TaskBlueprint 列表、DeepSeekClient、并发上限
输出：TaskWriterResult 列表
      ├── candidates
      ├── request_id
      └── error_code / error_message
```

`TaskBlueprint.writer_view.category` 会作为输入语义提示提供给 DeepSeek，帮助模型理解任务属于哪一类；它不是模型需要回填的字段。每个候选的输出契约只有一个字段：

```json
{
  "candidates": [
    {"text": "把卧室主灯关掉。"},
    {"text": "准备睡觉了，请关掉卧室的灯。"}
  ]
}
```

如果候选额外返回 `category` 或其他字段，`StaticTaskValidator` 会报 `CANDIDATE_EXTRA_FIELDS`，不再把它解释为任务类别错误。

请求日志和响应日志由 `DeepSeekClient` 写入调用方指定的 `data_raw/v2/task_writer/` 目录。API 错误保留在结果中，后续数据路由为 `system_failure` 或待重试，不直接生成 Scenario。
