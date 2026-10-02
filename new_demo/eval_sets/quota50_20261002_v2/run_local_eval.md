# run_local_eval.py 说明

用途：用本地 OpenAI 兼容服务（llama.cpp `llama-server`）在评测任务集上跑 C.run，
按 `workers` 并发，逐条输出 C-1..C-4。

```text
输入
  tasks.jsonl        模型可见部分（home / user_request / episode_config / tools）
  ground_truth.jsonl 隐藏 task，用来重建 Scenario
  --server           本地服务地址，默认 http://127.0.0.1:18080
  --model            服务里的模型名，默认 qwen2.5-1.5b-instruct
  --workers          并发数，默认 2
  --max-turns        轮次上限，默认 12（覆盖评测集里的 10）
  --limit / --task-ids  只跑前 N 条或指定 task_id
  --few-shot         打开 few-shot：system → 该类示例 → 包装过的真实任务
                     （真实任务里重申：示例不是真实环境、一次只输出一个 JSON、最多 12 步）
  --few-shot-dir     按类别存放示例的目录，默认 fewshot_by_task/（T1–T5 各一个 JSON）
                     缺文件时回退到内置全局示例；只影响评测会话，不改 D0_templates

输出（--output-dir）
  local_model.env    指向本地服务的 DeepSeek_* 配置
  api/               每条请求的原始响应记录
  results.jsonl      每条任务：labels / turn_count / finish / elapsed_sec
  trajectories.jsonl 每条任务的完整 record（turns / final_state / protocol）
  summary.json       总条数、C 全过条数、错误数、耗时

命令示例
  python new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py \
    --output-dir new_demo/runs/qwen15b_eval_250 --workers 2 --max-turns 12
```

说明：本脚本只跑 A 侧（C.run）拿 C-1..C-4；D6 三票复核需要单独跑，
T1/T2 本来跳过 D6。
