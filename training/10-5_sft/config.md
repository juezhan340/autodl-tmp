# config.json 中文说明

本配置只指定本轮 1.5B 实验参数，不会因读取配置自动启动训练。

```text
模型：已有 Qwen2.5-1.5B-Instruct HF 原始权重
数据：千条 quota200_20261004_v2 的 D_dataset.jsonl
产物：/root/autodl-tmp/training_runs/10-5_sft，仓库外
种子：20261005

每类训练100 / 验证20 / 测试40
  -> 总计500 / 100 / 200，备用194

完整训练：最多3个epoch
micro-batch 2 × 累积4 = 单卡有效batch 8
序列容量3072；超长直接报错，不截断
learning_rate=0.0001
LoRA：r=16，alpha=32，dropout=0.05
单轮生成上限192个新token
```

所有 epoch 均保存。验证 loss 选择 adapter，不访问最终测试集。修改配置会改变数据版本指纹，须明确重新准备产物；完整训练仍需命令行确认。
