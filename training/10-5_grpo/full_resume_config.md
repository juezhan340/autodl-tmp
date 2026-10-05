# full_resume_config.json 中文说明

这是正式训练OOM后的明确续跑配置，不是自动降批或测试版。500池、32条更新、micro16累计2、G4、奖励r2、beta=.02和原200评测均保持。

```text
原正式运行full500-20261005T180454543706Z：首步完成，第二步softmax OOM
policy/AdamW：读取该运行checkpoint-interrupted，保留首步结果
resume_run：恢复52项覆盖、采样反馈和首步指标，丢弃未提交候选
reference：仍为原SFT epoch3；previous_stage_run仍供历史100分类/179评测对照
logprob_token_chunk=128：完整16轨迹decoder，LM head按128真实生成token分块重算
候选总预算1500、更新总上限64，包含中断前已完成部分
新输出full500-resume-*，保留原失败日志与checkpoint
```

其他值与`full_config.json`同口径：温度.7、上下文3072、输出192、学习率1e-5、seed20261006、复核16路及D6评测100路。没有API key。运行状态以active_run和新目录training_status为准。
