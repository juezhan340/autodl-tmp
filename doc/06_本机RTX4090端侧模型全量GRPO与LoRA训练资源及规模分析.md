# 本机 RTX 4090 端侧模型全量 GRPO 与 LoRA 训练资源及规模分析

> 分析日期：2026-09-21  
> 本机：单张 NVIDIA GeForce RTX 4090，24,564 MiB 显存  
> 目标：判断本机能训练哪些模型本体，以及全量 GRPO、LoRA-GRPO、QLoRA-GRPO 能做到多大规模。

## 先看结论

```text
全量 GRPO：
  稳定支持：MiniMind-3，约 68.8M 参数
  改造后可试：1.5B，短序列、小 rollout
  不支持：4B、7B 全量 GRPO
```

```text
LoRA-GRPO：
  稳定支持：1.5B、3B
  可以小规模尝试：4B
  7B：需要 QLoRA、共享 reference 或 CPU offload，属于实验性支持
```

```text
一句话：全量训练按 70M 级别规划；普通 LoRA 按 3B 级别规划；QLoRA 小规模可以摸到 7B。
```

以上判断建立在完成必要代码改造的前提上。当前 `train_grpo.py` 尚未接入 LoRA，仍同时加载 policy、reference、reward，并直接对全量 policy 参数优化。因此直接运行时，只有 MiniMind-3 这类 68.8M 模型较稳妥；LoRA-GRPO 需要先完成训练脚本改造。

## 1. 本机现状

```text
GPU：       NVIDIA GeForce RTX 4090
显存：       24,564 MiB，约 24 GB
CUDA：       13.0
GPU 当前状态：空闲

CPU：       2 路 Intel Xeon Gold 6430
CPU 线程：   128
内存：       约 1 TiB，总可用内存约 863 GiB

磁盘：       /root/autodl-tmp 总容量约 50 GB
剩余：       约 31 GB
```

本机的主要限制是 GPU 显存和磁盘，不是 CPU 或系统内存。CPU 内存足以承担数据预处理、CPU offload 和 rollout 缓存的一部分，但不能把所有 GPU 反向传播激活都“转移”到内存后仍保持合理训练速度。

当前已经存在的模型：

```text
MiniMind-3：
  68.83M 参数
  full_sft_768.pth 约 128 MiB 的半精度权重
  已有 GRPO checkpoint

Qwen2.5-7B-Instruct：
  只有 Q5_K_M GGUF 双分片
  已完成 llama.cpp 推理部署
  这是推理格式，不是当前训练代码可直接加载的 Transformers 训练权重
```

因此，当前机器不能沿用之前按 96GB GPU 得出的资源判断。当前是 24GB 单卡。

## 2. 先区分三种“能不能跑”

```text
模型能推理
  != 模型有可训练的 Transformers 权重

模型有 Transformers 权重
  != 当前 MiniMind 代码能直接加载

模型能放进 GPU
  != policy、reference、reward、optimizer、激活和 rollout 能同时放进 GPU
```

本机判断应采用以下三层：

| 层级 | 判断内容 |
|---|---|
| 模型本体可用 | 本地是否有可训练的权重，格式是否支持反向传播 |
| 训练代码兼容 | 当前代码是否能构造模型、计算 logprob、保存 checkpoint |
| 资源配置可行 | 训练时的 policy、reference、reward、优化器、激活和 rollout 是否能放进 24GB |

## 3. 参数量对应的基础显存

下面只计算模型参数本身，不包括激活、KV cache、logits、临时张量、reference model 和 reward model。

全量训练时，粗略可以按每个可训练参数 `12～16 bytes` 估算：

```text
BF16/FP16 权重：       2 bytes
BF16/FP16 梯度：        2 bytes
AdamW 一阶、二阶状态：  8 bytes
FP32 master weight：    0～4 bytes
```

| 模型规模 | BF16 权重 | 全量 actor 状态下限 | 全量 actor 状态上限 | 当前代码再加 reference 权重后 |
|---:|---:|---:|---:|---:|
| 68.8M | 0.13GB | 0.83GB | 1.10GB | 约 0.96～1.23GB |
| 1.5B | 3GB | 18GB | 24GB | 约 21～27GB |
| 3B | 6GB | 36GB | 48GB | 约 42～54GB |
| 4B | 8GB | 48GB | 64GB | 约 56～72GB |
| 7B | 14GB | 84GB | 112GB | 约 98～126GB |

这里的“reference 权重”只加了一个冻结 BF16 模型，尚未加入 reward model 和序列激活。因此：

```text
1.5B 全量 GRPO：当前代码已经接近或超过 24GB
4B 全量 GRPO：单卡不具备基础可行性
7B 全量 GRPO：单卡完全不具备基础可行性
```

LoRA 的固定参数状态低很多，但当前代码若仍复制一个完整 BF16 reference model，则大致需要：

```text
LoRA actor + reference 权重 ≈ 4 bytes × 参数量
```

| 模型规模 | LoRA policy + reference BF16 权重 | 余下显存是否足够放激活和 rollout |
|---:|---:|---|
| 1.5B | 约 6GB | 通常可以，需小 batch、短上下文 |
| 3B | 约 12GB | 可以做短上下文实验，默认配置偏危险 |
| 4B | 约 16GB | 只有在移除 reward model、压缩 rollout 后才有机会 |
| 7B | 约 28GB | 当前单卡不行，必须 QLoRA、共享 reference 或 offload |

## 4. 当前 `train_grpo.py` 的真实显存结构

当前脚本不是只加载一个 policy。启动时会在同一张 GPU 上加载：

```text
Policy model
    + Reference model
    + Reward model
    + AdamW optimizer states
    + Rollout 结果
    + Policy forward 激活
    + Reference forward 临时张量
```

代码位置：

```text
minimind/trainer/train_grpo.py
  init_model(...)                    # policy
  init_model(...)                    # reference
  LMForRewardModel(...)               # reward model
  optim.AdamW(model.parameters(), ...) # full actor optimizer
```

默认参数还会放大显存：

```text
batch_size       = 2
num_generations  = 6
max_seq_len      = 768
max_gen_len      = 1024
```

这意味着每个训练 step 最多生成：

```text
2 个 prompt × 6 个 generation = 12 条 rollout
每条最长约 768 + 1024 = 1792 tokens
```

如果换成 Qwen 这类约 152K vocabulary 的模型，当前 policy forward 对完整 logits 的粗略张量规模为：

```text
12 × 1792 × 152K × 2 bytes ≈ 6.1 GiB
```

而当前代码的 policy 和 reference 路径都对完整序列计算 logits。这个问题会在模型还没有碰到参数状态上限之前，先造成显存峰值过高。

因此，Qwen 训练前必须做以下结构性调整：

```text
只保留 completion token 的 logits
不要对完整 vocabulary、完整 prompt 重新保存不必要的 logits
reference 与 policy 尽可能共享冻结基座或单独 offload
HomeFlow 使用环境 verifier 后，移除额外 reward model
rollout 采样与反向传播使用不同的 micro-batch
```

## 5. 当前代码对模型本体的支持边界

### 5.1 MiniMind-3：当前唯一可以直接全量训练的模型族

当前 `train_grpo.py` 使用的是：

```python
MiniMindConfig(...)
MiniMindForCausalLM(...)
```

因此它直接兼容的是 MiniMind 自己的 checkpoint，不是任意 Hugging Face CausalLM。

本机已有的 `MiniMind-3` checkpoint 约 68.83M 参数，当前机器完全可以承载：

```text
全量 SFT
全量 GRPO/CISPO
LoRA SFT
改造后的 LoRA-GRPO
HomeEnv 多轮 rollout 原型
```

当前脚本的默认 reward model 路径是 `../../internlm2-1_8b-reward`，本机没有发现该目录。也就是说，MiniMind 全量 GRPO 的模型状态能放下，但按原脚本直接启动仍会因为 reward model 路径缺失而失败。

HomeFlow 复现中更合理的做法是把 `calculate_rewards()` 改成：

```text
HomeEnv 执行动作
  -> 判断目标完成度
  -> 返回状态进展 reward
  -> 非法动作、无效工具调用、超步数产生惩罚
```

这样可以移除额外的 1.8B reward model，减少显存和磁盘占用，并使 reward 与 HomeFlow 的环境真值一致。

### 5.2 Qwen2.5-1.5B：适合移植后做 LoRA-GRPO

Qwen2.5-1.5B 在研究上是本机最合适的外部基座：模型足够小，仍保留真实端侧模型的 tokenizer、工具调用和 instruction 能力。

但当前代码不能直接加载它，原因有三点：

```text
当前初始化函数固定构造 MiniMindForCausalLM
当前 checkpoint 命名和配置固定为 MiniMindConfig
当前 LoRA 只在 train_lora.py 中启用，没有接入 train_grpo.py
```

资源上建议：

```text
LoRA-GRPO：可行，优先级最高
QLoRA-GRPO：可行，但第一版没有必要
全量 GRPO：当前脚本不建议；需要移除 reward model、共享 reference、短序列和 gradient checkpointing
```

### 5.3 Qwen3/Qwen3.5-4B：只适合 LoRA 或 QLoRA 小规模试验

4B 模型的 BF16 权重约 8GB，全量 actor 的 optimizer、梯度和权重状态约 48～64GB。即使不考虑长上下文，当前单卡也无法运行全量 GRPO。

LoRA 版本在理论上可以压到约 16GB 的 policy + reference BF16 权重，但还要为：

```text
HomeEnv rollout
policy backward
completion logits
optimizer adapter states
数据和临时张量
```

预留空间。因此本机 4B 只能采用短上下文、低 generation 数和较小 batch。更稳妥的版本是 QLoRA，但需要引入量化训练支持，当前 MiniMind 的 `model_lora.py` 不是 QLoRA 实现。

论文中的 Qwen3.5-4B agent 实验还显示，LoRA 在各自最佳检查点可以接近全量 GRPO，但达到该检查点可能需要更多更新步数；长上下文下，LoRA 仍无法消除反向传播激活开销。因此本机不应以“4B LoRA 最终能接近全量”为理由使用长轨迹和大 rollout 组。

### 5.4 Qwen2.5-7B：当前机器可以推理，不能直接训练

本机已有 Qwen2.5-7B-Instruct Q5_K_M GGUF，实测可以在 llama.cpp 中运行 8K、16K 和 32K 上下文，并支持低并发推理。

这只能证明：

```text
7B 量化模型推理可部署
```

不能证明：

```text
7B Transformers FP16 权重可以训练
7B 全量 GRPO 可以训练
7B GGUF 可以直接反向传播
```

本机对 7B 的推荐顺序是：

```text
第一选择：Qwen2.5-7B QLoRA-GRPO，短上下文、小 rollout
第二选择：7B LoRA-GRPO，需把 reference 和 rollout 拆开管理
第三选择：7B 只做推理评测，训练在更大 GPU 上完成
不建议：单卡全量 GRPO
```

QeRL 的 7B 结果说明，专门设计的 NVFP4 + LoRA + 自适应量化噪声可以在数学任务上匹配全量微调，但这依赖专门的量化训练和 rollout 实现，不等同于当前代码加一个 `load_in_4bit=True` 就能复现。

## 6. 本机可支持的模型和训练方式

| 模型本体 | 本机已有状态 | 当前代码直接支持 | 全量 GRPO | LoRA-GRPO | QLoRA-GRPO | 推荐用途 |
|---|---|---:|---:|---:|---:|---|
| MiniMind-3 68.8M | 有 checkpoint | 是 | 可以 | 改造后可以 | 没必要 | HomeEnv 闭环、奖励函数、数据管线 |
| Qwen2.5-1.5B | 未安装 HF 训练权重 | 否 | 高风险 | 可以移植 | 可以移植 | 主要端侧模型实验 |
| Qwen2.5/3B | 未安装 HF 训练权重 | 否 | 不建议 | 可行但需短序列 | 可行 | 资源和性能中间档 |
| Qwen3/Qwen3.5-4B | 未安装 | 否 | 不可行 | 小规模可行 | 更推荐 | HomeFlow agent 能力验证 |
| Qwen2.5-7B | 只有 GGUF | 否 | 不可行 | 高风险 | 小规模可尝试 | 推理部署、LoRA 探索 |

## 7. 建议的训练规模

下面的规模是“本机可完成的工程验证规模”，不是 HomeFlow 论文级复现规模，也不是数学 benchmark 的最终效果规模。

### 7.1 MiniMind-3：完整闭环规模

```text
任务数：       100～500 个 HomeEnv 场景
每任务 rollout：4～6 条
prompt 长度：  256～768 tokens
生成长度：     128～256 tokens
训练步数：     50～300 个 optimizer steps
训练方式：     全量 GRPO 与 LoRA-GRPO 都可对比
```

这个规模适合先验证：

```text
HomeEnv reset/step 是否正确
工具调用解析是否稳定
非法动作是否被惩罚
奖励是否有组内方差
SFT 轨迹能否进入 RL rollout
```

### 7.2 1.5B：LoRA 主线，全量做短基线

```text
任务数：       300～1,500 个场景
每任务 rollout：4 条起步，最多 6 条
prompt 长度：  256～512 tokens
生成长度：     128～256 tokens
训练步数：     100～500 steps
LoRA rank：    r=16 或 r=32
```

全量 GRPO 只做以下版本：

```text
batch_size=1
num_generations=2～4
max_seq_len=256～384
max_gen_len=128～256
移除额外 reward model
reference 使用共享或 CPU offload 方案
```

不建议在当前代码不改动的情况下直接运行 1.5B 全量 GRPO。

### 7.3 4B：LoRA/QLoRA 小规模验证

```text
任务数：       100～500 个场景
每任务 rollout：2～4 条
prompt 长度：  128～384 tokens
生成长度：     128～256 tokens
训练步数：     50～250 steps
batch_size：   1
```

4B 训练的重点不是一次性追求大数据量，而是完成四个对照：

```text
同样 steps：       Full/LoRA 的学习速度
同样 rollout token：单位数据量收益
同样 GPU-hours：    实际工程效率
各自最佳 checkpoint：最终性能上限
```

### 7.4 7B：只做 QLoRA 小试验或外部训练

```text
任务数：       50～200 个场景
每任务 rollout：2～4 条
prompt 长度：  128～256 tokens
生成长度：     128～256 tokens
训练步数：     30～150 steps
batch_size：   1
```

7B 本机实验的目标应限定为：

```text
验证 HomeEnv reward 是否有学习信号
验证 LoRA adapter 是否能改变工具调用策略
验证短轨迹下的趋势
```

不应把该规模解释为 7B HomeFlow 能力已经充分训练。

## 8. 当前代码必须修改的地方

### 8.1 当前 LoRA 没有接入 GRPO

`minimind/trainer/train_lora.py` 会调用 `apply_lora(model)`，而 `minimind/trainer/train_grpo.py` 没有调用它，并且优化器直接接收：

```python
optimizer = optim.AdamW(model.parameters(), lr=args.learning_rate)
```

所以当前 GRPO 是全量更新，不是 LoRA-GRPO。

LoRA-GRPO 至少需要：

```text
创建 policy 后插入 adapter
冻结非 adapter 参数
optimizer 只接收 adapter 参数
reference 使用冻结基座或 adapter-disabled policy
checkpoint 分开保存 base 与 adapter
```

### 8.2 当前 LoRA 的目标层过窄

`model_lora.py` 当前只对 `in_features == out_features` 的线性层插入 LoRA。对于 Qwen 和 MiniMind，这通常只能覆盖部分方形 attention projection，不能覆盖完整的 q/k/v/o 和 FFN all-linear 结构。

如果目标是复现论文中的 LoRA-GRPO，应改成显式 target module 选择：

```text
q_proj、k_proj、v_proj、o_proj
gate_proj、up_proj、down_proj
```

第一版 HomeFlow 可以只选：

```text
q_proj、v_proj、o_proj
```

之后再比较 all-linear。这样能先控制显存和 adapter 参数量。

### 8.3 当前 GRPO 的完整 logits 需要裁剪

rollout logprob 计算已经有 `logits_to_keep` 的局部逻辑，但 policy loss 和 reference loss 路径仍然取完整 `res.logits`。对 Qwen 级 vocabulary，这会形成明显的显存峰值。

应改为：

```text
只计算 completion 位置的 logits
或按 micro-batch 分段计算 selected-token logprob
不保留整个 prompt 的 vocabulary logits
```

这项修改对 1.5B、4B、7B 都有价值，优先级高于单纯降低 LoRA rank。

### 8.4 HomeFlow 不应默认依赖通用 reward model

当前脚本的 reward 是“格式规则 + 重复惩罚 + reward model”。HomeFlow 的核心 reward 应由 HomeEnv verifier 产生：

```text
合法动作：      0 或小正奖励
目标完成度增加：按完成度增量奖励
目标完成：      终局奖励
非法动作：      负奖励
越界/副作用：   更强负奖励
超步数：        截断惩罚
```

移除通用 reward model 后，显存、磁盘和训练逻辑都会更适合本机，也更符合 HomeFlow 的环境训练目的。

## 9. 最终资源结论

```text
当前机器最稳妥的主线：
  MiniMind-3 全量 GRPO 做环境闭环
  MiniMind-3 LoRA-GRPO 做参数高效对照
  Qwen2.5-1.5B LoRA-GRPO 做真实端侧模型实验

当前机器可以尝试但需要改造：
  Qwen3/3.5-4B LoRA 或 QLoRA 短序列训练
  Qwen2.5-7B QLoRA 极小规模验证

当前机器不适合：
  1.5B 以上的原始脚本全量 GRPO
  4B/7B 全量 GRPO
  Qwen2.5-7B GGUF 直接反向传播
  HomeFlow 论文级多轮长上下文 rollout 训练
```

推荐的实验顺序是：

```text
第一阶段：MiniMind 68.8M
  修正 HomeEnv reward 和 rollout 契约
  跑通全量 GRPO
  再接 LoRA-GRPO

第二阶段：Qwen2.5-1.5B
  移植 Transformers policy
  先 LoRA-GRPO
  再做短序列全量上限对照

第三阶段：4B
  只做 LoRA/QLoRA
  对比等步数、等 token、等 GPU-hours

第四阶段：7B
  优先部署和评测
  只有在 QLoRA 训练链路稳定后才做小规模 GRPO
```

当前本机的研究价值不在于复现大规模论文训练，而在于用低成本完成下面的验证闭环：

```text
HomeEnv 状态转移
  -> SFT 轨迹质量
  -> GRPO reward 是否有方差
  -> LoRA 是否能改变工具调用策略
  -> 小模型是否能提高任务成功率
```

## 10. 参考论文与本地依据

| 来源 | 用途 |
|---|---|
| *Cooperative Coevolution for Resource-Constrained Agentic LLM Post-Training*，arXiv:2608.02391 | Qwen3.5-4B agent 的全量 GRPO、LoRA-GRPO、长上下文显存和训练预算对照 |
| *Hybrid-LoRA: Bridging Full Fine-Tuning and Low-Rank Adaptation for Post-Training*，arXiv:2605.18822 | 少量模块全量更新与其余模块 LoRA 的折中方案 |
| *Learning to Reason in 13 Parameters*，arXiv:2602.04118 | 极小参数更新在 GRPO 数学任务中的可行性边界 |
| *QeRL: Beyond Efficiency -- Quantization-enhanced Reinforcement Learning for LLMs*，arXiv:2510.11696 | NVFP4、LoRA 和探索噪声结合的资源效率方案 |
| [QWEN7B_DEPLOYMENT_OPTIONS.md](/root/autodl-tmp/QWEN7B_DEPLOYMENT_OPTIONS.md) | 本机 Qwen2.5-7B GGUF 推理显存和上下文实测 |
| [minimind/trainer/train_grpo.py](/root/autodl-tmp/minimind/trainer/train_grpo.py) | 当前 GRPO 的 policy/reference/reward/optimizer 结构 |
| [minimind/trainer/train_lora.py](/root/autodl-tmp/minimind/trainer/train_lora.py) | 当前 LoRA 仅接入 SFT 的事实依据 |
