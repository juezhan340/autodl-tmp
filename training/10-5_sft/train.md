# train.py 中文说明

```text
职责：调用TRL SFTTrainer和PEFT LoRA；逐epoch保存并登记检查点。
输入：config、mode=check/smoke/train、可选恢复检查点。
输出：计划，或adapter/检查点索引/训练摘要及同名md。
读取：已冻结的数据manifest、训练/验证消息、已有HF基础权重。
写入：output_root/smoke-时间戳，或output_root/sft-main。
不负责：最终测试、D6、数据合成、下载模型。
```

默认`check`只核验数据与配置。`train`必须同时给`--confirm-full-training`；恢复也必须指向当前运行目录，并且配置及data_manifest指纹不变。同路径的数据被重新导出后，旧检查点不能静默接着训练新数据。

`smoke`在默认micro-batch=2下，只取两条最长训练样本、两条验证样本，跑两个epoch、两次更新。若micro-batch=1，只取一条训练样本，仍严格限制为两次更新。它不消耗完整500条训练循环，也不读取测试样本成绩。

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
