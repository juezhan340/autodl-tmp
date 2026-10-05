# run_stage.py 中文说明

2026-10-06：100任务入口保持历史行为。共用`save_checkpoint`改为追加/按名称更新checkpoint索引，不丢弃已有里程碑记录；500入口复用该函数保存第32更新、覆盖500、结束及异常权重。大权重不会逐批保存。

职责：执行用户批准的第一阶段100任务，micro16累计1，完成后自动原固定200任务评测。复用已验证的采样/奖励/损失函数，不在启动前另跑GPU冒烟。

```text
输入：stage1_config、独立run-dir、训练与API两个确认
读取：train_scenarios；验证/测试group；epoch3 adapter和HF模型
输出：25个更新批次、400条轨迹；阶段结束模型；固定200评测
写入：selected_tasks、逐批rollouts/packed/evidence/rewards/advantages/logprobs
      update_report、metrics/status、checkpoint-stage1、training_report
不负责：自动降micro、自动OOM重试、完整500任务训练、自动断点恢复
```

五类各20项抽样并混合，严格检查训练与验证/测试不重叠。每批4任务×4轨迹，rollout同组4路；完成评审后16条一次反向。整个阶段共享一份AdamW，不在每批重置动量。初始policy必须等于SFT参考，更新后允许两者不同；参考逐批核对冻结指纹。

逐更新落盘真实reward、成功/安全/finish/预算、同分组比例、loss/KL/梯度、吞吐、耗时与分阶段显存。全部同分仍可能有参考KL梯度；实际零梯度才跳过optimizer.step，批次进度与optimizer更新数分别记录。

只在阶段结束保存`checkpoint-stage1`，含policy adapter、tokenizer、optimizer、Python/Torch/CUDA随机状态和选择指纹；不逐批保存大权重。若异常前已有实际更新，另保留一次checkpoint-interrupted；首次更新OOM只保存证据和失败日志，原epoch3仍在。当前未提供自动resume入口。

GPU OOM/非有限loss/参考变化/基础设施错误都会终止，写failure及页面failed。待审结尾不能变成0分进入更新。成功后释放训练对象，再交给evaluate_stage评测。训练、页面和评测日志在仓库外，密钥只读根目录。
