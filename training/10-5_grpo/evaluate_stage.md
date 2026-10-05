# evaluate_stage.py 中文说明

职责：第一阶段训练成功后，用已有SFT的`evaluate.py`加载新adapter，在原固定200任务greedy评测；使用原D6模板三票并发补审，与已保存SFT epoch3的176/200结果对照。训练reward审查提示词不用于最终D6。

```text
输入：第一阶段配置、运行目录、最终adapter、LiveProgress
读取：test_scenarios、baseline_review、原SFT评测代码和D6模板
输出：200轨迹、C+D6完整成功率、五类结果、改善/退步数与待确认数
写入：evaluation/generation.log、grpo_stage1、d6_cache/api
      reviewed_trajectories、grpo_summary、comparison及同名md
不负责：参数更新、重新训练基线、把API失败记成模型错误
```

启动前核对两个版本是完全相同的200个Scenario，并核对已有epoch3基线权重文件与本次训练起点一致。环境生成使用原A提示词及内嵌示例，不加另一套few-shot；max_length和生成参数沿用原SFT评测配置。主进程每2秒更新评测进度，子进程日志独立保存。

T1/T2按C四项，T3/T4/T5仅C四项全过才进原D6，最多100任务并发、每任务串行三票。非法票保留system_failure/null。源轨迹指纹在评审前后不变；新汇总明确`few_shot_mode=current_A_embedded_examples_no_extra_wrapper`，避免旧summary的false字段被误解为无内嵌示例。

既有200集曾被分析，用于固定对照，不声称是完全未查看的新最终测试。比较按sample_id对齐。完整summary保留任务数、C成功、D6待确认及成功率；不能将训练reward成功率直接与旧88%比较。
