# `homeflow_demo/data/deepseek_task_reviewer.py` 说明

## 职责

审查静态校验通过的自然语言候选。它解决代码无法可靠完成的语义问题：候选是否表达了蓝图目标、是否添加额外意图、是否存在软泄露、不同表述是否可能属于同一语义任务。

```text
TaskBlueprint.writer_view + candidate
  -> DeepSeekTaskReviewer
  -> TaskReviewResult
  -> accept 才能编译 Scenario
```

## 输入输出

```text
输入：TaskBlueprint、候选文本、DeepSeekClient、并发上限
输出：TaskReviewResult
      ├── decision
      ├── accepted
      └── error_code / error_message
```

该模块不读取 HomeEnv 最终状态，也不判断动作执行成功。模型 API 失败或审查 JSON 解析失败会保留为系统审查错误，不把候选静默当成合格数据。
