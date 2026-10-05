# stage1_config.json 中文说明

用户批准的第一阶段配置：原500训练任务中T1至T5各20个，共100个；每个任务4条rollout，计划400条、25个更新批次。`micro_batch=16、accumulation=1`，每次16条一起反向。rollout仍为同组4路，不把micro16解释为16路生成。

```text
模型：已有Qwen2.5-1.5B BF16基座 + epoch3 FP32 LoRA
参考：共享基座的冻结epoch3 adapter；β=0.02
采样：temperature=0.7、完整上下文3072、单轮最多192 token
更新：AdamW lr=1e-5；clip ε=0.2；一次token全局归一化
奖励：r2，3S+2ΔΦ+0.5E+0.5H−0.25错误−2虚假结束−0.5预算
安全：严重过程违规覆盖为-5；普通奖励裁剪[-4,6]
评审：训练16并发、每轨迹三票；最终原D6最多100并发
评测：训练结束后原固定200测试；对照已有epoch3的C+D6轨迹
保存：第一阶段结束保留完整checkpoint，不逐更新保存大权重
OOM：停止并写失败状态，不自动降micro、不隐式重跑
```

`seed=20261005`。`smoke_categories`仅兼容既有配置校验，正式任务抽样覆盖五类。`stage_name/train_tasks/tasks_per_category/test_tasks`限定本轮范围；`evaluate_after_training=true`表示训练成功后自动评测。`sft_eval_config`复用现行A及原固定数据划分；`baseline_review`读取已完成epoch3语义评测，不重复训练基线。

路径为服务器现有HF模型、`training_runs/10-5_sft/data`、`sft-main/selected_adapter`和仓库外`training_runs/10-5_grpo`。完整键值见同名JSON；未包含密钥。旧`config.json`仍是micro2累计8的历史冒烟配置，正式启动只用本文配置。
