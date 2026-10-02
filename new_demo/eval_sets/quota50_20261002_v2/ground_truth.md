# ground_truth.jsonl 说明

一行一个任务，与 `tasks.jsonl` 按 `task_id` 一一对应。**这个文件只给评测器。**

```json
{
  "task_id": "sc_T1_001",
  "category": "T1",
  "task": {
    "intent": "夜里想看看书，台灯暗一点",
    "conditions": ["..."],
    "keep": ["..."],
    "required_observations": ["..."],
    "expected_finish": {"outcome": "completed", "allowed_reason_codes": []}
  },
  "labels": {"C-1": true, "C-2": true, "C-3": true, "C-4": true},
  "d6": "跳过"
}
```

```text
task.intent                 隐藏意图，仅作背景，不参与 C 判定
task.conditions             目标条件：C-2 的对照；eq 精确命中，ge/le 相对 s0 初值看方向
task.keep                   保持条件：只许 eq，C-2 一并检查
task.required_observations  仅 T4 非空；C-3 要求成功 inspect 被拒设备
task.expected_finish        C-4 的 finish 契约：completed/refused 与 reason_code
labels / d6                 参考轨迹的原始判定（C-1..C-4 与 D6），用于对照评测器
```

不要把这个文件的内容喂给被测模型。
