# requirements.txt 中文说明

职责是固定本轮训练和测试依赖，不包含基础模型或 CUDA 权重分发包。

```text
Transformers 4.57.3 -> 本地模型、聊天模板、collator、Trainer基础
TRL 0.24.0         -> SFTTrainer / SFTConfig
PEFT 0.18.0        -> LoRA及adapter保存、重载
Accelerate 1.11.0  -> 单卡执行与梯度累积
Datasets 4.4.1     -> 已编码训练/验证数据
Tokenizers 0.22.1  -> 官方tokenizer底层
Safetensors 0.7.0  -> adapter安全文件格式与参数核对
Pytest 8.4.2       -> 自动测试
```

使用仓库外 `/root/autodl-tmp/sft-venv`，继承系统 PyTorch 2.8.0+cu128，不重复下载 PyTorch/CUDA。完整运行版本另外记录在预测试报告；这里只列直接依赖。
