# fewshot_by_task：按任务类别的 few-shot

每个 T 一份专属示例，评测 runner 打开 `--few-shot` 时按任务类别取对应文件：

```text
T1.json  单设备控制：精确控制 + 方向控制两例
T2.json  多设备控制：两条 condition + 一台 keep
T3.json  模糊意图：只有感受句，助手自己找设备并落方向
T4.json  危险拒绝：先 inspect 被拒设备，再 refused + OUT_OF_SAFE_RANGE
T5.json  环境查询：读 environment/state，summary 带读数
```

结构：直接给消息数组（role/content），由 runner 插在 system 与包装过的真实任务之间。
真实任务仍用统一的 [TASK] 包装（示例不是真实环境、一次一个 JSON、最多 12 步）。
