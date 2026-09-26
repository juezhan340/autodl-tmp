# `homeflow_demo/data/static_task_validator.py` 说明

## 职责

这个模块只做程序可以可靠完成的硬校验，不调用 DeepSeek：

```text
候选 JSON 结构
文本非空和长度
候选只包含 text 字段
device_id / room_id / action / reason_code 硬泄露
工具调用 JSON 泄露
精确重复和 split 去重登记
```

自然语言是否真正表达了蓝图目标由 `deepseek_task_reviewer.py` 负责。代码不会假装理解“弄凉快一点”这类语义。

## 输入输出

```text
validate_task_candidate(blueprint, candidate, seen_texts)
  -> TaskValidation

register_candidate(registry, validation, scenario_id)
  -> 更新精确去重索引
```

`TaskValidation.codes` 使用稳定错误码，例如 `CANDIDATE_EXTRA_FIELDS`、`HARD_LEAKAGE`、`EXACT_DUPLICATE` 和 `TOOL_SCHEMA_LEAKAGE`。`category` 属于 Blueprint 和 `writer_view` 的任务元数据，不属于候选输出字段；如果模型额外返回它，会按多余字段拒绝。通过的候选才进入 DeepSeekTaskReviewer 和 Scenario 编译。
