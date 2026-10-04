# train.py 中文说明

```text
职责：调用TRL SFTTrainer和PEFT LoRA；逐epoch保存、登记检查点并写实时状态。
输入：config、mode=check/smoke/train、可选恢复检查点。
输出：计划，或adapter/检查点索引/训练摘要/进度与指标及同名md。
读取：已冻结的数据manifest、训练/验证消息、已有HF基础权重。
写入：output_root/smoke-时间戳，或output_root/sft-main。
不负责：最终测试、D6、数据合成、下载模型。
```

默认`check`只核验数据与配置。`train`必须同时给`--confirm-full-training`；恢复也必须指向当前运行目录，并且配置及data_manifest指纹不变。同路径的数据被重新导出后，旧检查点不能静默接着训练新数据。

正式配置为micro-batch=4、梯度累计2次，单卡有效batch=8。`smoke`取一个micro-batch的最长训练样本，默认四条，加两条验证样本，跑两个epoch、两次更新；冒烟的梯度累计独立设为1。它不消耗完整500条训练循环，也不读取测试样本成绩。此次配置修改未运行新的GPU冒烟。

冒烟摘要中的effective_batch按其实际累计1次报告，默认是4；正式训练和check计划仍报告8。

```text
每个epoch
  -> 验证loss
  -> checkpoint-N/
       adapter_model.safetensors、adapter_config.json
       optimizer.pt、scheduler.pt、rng_state.pth
       trainer_state.json、训练参数和tokenizer
  -> checkpoint_index.json：epoch、step、配置/数据指纹、adapter校验值

结束
  -> 载入验证loss最好的adapter
  -> selected_adapter/与training_summary.json
```

不限制检查点保留数量。使用BF16、SDPA、非重入梯度检查点，LoRA作用于q/k/v/o及gate/up/down线性层。预先构建的labels通过官方collator补齐，padding标签为-100；关闭Trainer再次预处理，防止掩码被覆盖。

正式训练结束还检查checkpoint_index数量等于epoch数。selected_adapter是验证最优adapter的独立副本，保留它不会替换或删除其他epoch目录。

`progress.py`回调每个优化器step写进度，每step记录真实loss与学习率，逐epoch记录eval_loss；状态及日志保存在运行目录。入口捕获训练异常，写failed/interrupted后仍抛出原异常。启动监控服务不调用本训练入口。
