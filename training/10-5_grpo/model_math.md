# model_math.py 中文说明

2026-10-06：policy支持从`policy_adapter`独立加载，默认仍兼容原SFT起点；`sft_reference`始终从`sft_adapter`加载。分别核对两份源张量的FP32键、精度和数值，不要求GRPO起点与SFT参考相等。基座共享，参考与基座冻结，优化器只含policy。

正式第二次更新OOM定位于TRL BF16 `log_softmax`：micro16不同轨迹的生成位置取并集后，词表输出及softmax中间量同时常驻。`logprob_token_chunk=128`启用Qwen2专用等价概率路径：完整16轨迹decoder照常前向，提取每条真实policy位置，按128个token投影整个词表，FP32归一化；梯度路径使用PyTorch非重入checkpoint重算LM head，减少大矩阵常驻。old/current/reference均走同一路径。没有截断上下文、改变温度、奖励、KL或32轨迹的token分母；FP32概率数值精度相较原BF16提升，不宣称逐bit相同。未配置该项时保留历史TRL路径。

职责：加载共享基座与两个SFT adapter，构造完整上下文训练批次，计算实际采样token的概率和GRPO裁剪/KL损失。

```text
输入：模型配置、packed轨迹、old/ref概率、组内优势
读取：本地HF权重、epoch3 selected_adapter、TRL selective_log_softmax
输出：模型/tokenizer、token logprob、可反向loss、KL/裁剪统计
写入：无；检查点由smoke.py保存
不负责：环境采样、奖励判定、完整GRPO Trainer及多轮训练调度
```

`load_model`读取一份BF16冻结基座；policy和sft_reference分别从保存的SFT FP32 LoRA逐张量精确复制。载入时检查键集合、dtype和torch.equal，避免先降精度再升回FP32。LoRA dropout设0，使用SDPA、非重入activation checkpointing。`activate`切换adapter并重新锁定requires_grad，只有policy参数进入优化器。参考仍需跑前向；共享基座省的是第二份基座权重，不省参考计算。

`make_batch`右padding训练批次，全部真实上下文attention=1。`positions`取实际采样预测位置的批内并集；`token_logps`借Qwen2的`logits_to_keep`只在这些位置执行词表输出层，再用TRL的selective_log_softmax取实际token概率。词表位置减少，Transformer仍读取整段上下文。CPU小模型测试验证该概率与完整logits取同位置相等。

```text
ρ = exp(current_logp − old_logp)
k = exp(reference_logp − current_logp) − (reference_logp − current_logp) − 1
每token损失 = −min(ρA, clip(ρ,0.8,1.2)A) + 0.02k
整次更新分母Z = 全部16条轨迹真正采样的token总数
每个micro把自己的token损失除Z，8次backward后只step一次
```

这是token归一化的DAPO式分母，长度较长轨迹包含更多token；并非每条轨迹等权平均。步骤奖励先累成轨迹R，组内得到轨迹A，再共享给本条采样token；本版没有实现每个动作独立优势或精确逐步信用分配。

`surrogate_loss`先清零非策略位置，再计算指数，避免无意义位置的inf×0造成NaN。默认β=0.02，参考固定在epoch3，old只保存CPU token概率，不常驻第二份old模型。这里复用TRL工具并按其公式实现限定冒烟循环，没有调用完整GRPOTrainer。
