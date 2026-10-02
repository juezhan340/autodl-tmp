# 评测任务集：quota50_20261002_v2

> 来源：`new_demo/runs/quota50_20261002_v2/data_processed/D_dataset.jsonl`（统一版提示词批次，250 条成功轨迹）
> 提示词版本：commit `bab3628`；seed 20261020
> 生成日期：2026-10-02

## 目录

```text
tasks.jsonl / tasks.md              给被测模型：s0 + 用户话 + 工具 schema，不含隐藏 task
ground_truth.jsonl / ground_truth.md 给评测器：隐藏 task（conditions/keep/expected_finish）+ 参考标签
manifest.json                       条数、来源、唯一性、泄漏检查结果
```

## 怎么用

```text
1  被测模型只拿 tasks.jsonl 的一行：
     home 当 s0，user_request 当用户话，tools 当工具 schema，
     episode_config 限轮数（10 轮、每轮 1 个工具）

2  评测器把 tasks 行与 ground_truth.jsonl 按 task_id 拼回 Scenario：
     {
       "scenario_id": task_id,
       "blueprint_id": reference_blueprint_id,
       "home": home,
       "user_request": user_request,
       "task": ground_truth.task,
       "episode_config": episode_config
     }
   交给 C（EpisodeRunner）复跑打分，得到 C-1..C-4

3  T3 / T4 / T5 可选跑 D6 三票复核；T1 / T2 标跳过

4  ground_truth.labels 与 d6 是这 250 条参考轨迹当年的判定结果，
   用来核对评测器行为；不要把这部分喂给被测模型
```

## 口径

```text
条数      250（T1 50 / T2 50 / T3 50 / T4 50 / T5 50）
task_id   沿用原 scenario_id，全局唯一
配对      与 ground_truth.jsonl 按 task_id 一一对应
工具      与 new_demo/env/B_tool_schema.py 的 available_tools() 一致
```
