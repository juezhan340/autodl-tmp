# newdoc 08　本机 1.5B LoRA 可行性评估

> 来源：`13_本机1.5B_LoRA可行性评估.md`（独立主题，原样保留，仅标题层级下调一级）。

---

# 一、可行性评估全文

> 来源：newdoc/13_本机1.5B_LoRA可行性评估.md（原文逐字，仅标题层级下调一级）

## 本机 1.5B LoRA 微调可行性评估

> 日期：2026-10-03
> 机器：RTX 5060 Laptop，8151 MiB 显存，驱动 591.74（桌面基线约 0.9 GB）
> 结论：支持，但要降序列长度；推荐复用本机已跑通的手写脚本，不建议先上 TRL。
> 本文件只做评估，没有跑任何训练或标定。

### 0 结论

```text
能不能做        能做：8 GB 上做 1.5B 的 LoRA（bf16 + 梯度检查点）
前提条件        序列长度压到 2048–4096，micro-bs 1 + 梯度累积
                训练前先停掉 llama-server（它现在占约 4.3 GB 显存）
先上什么        复用本机手写 train_lora.py（0.6B 跑通过，带显存守卫与标定模式）
不建议先上 TRL  训练 venv 里没装 trl；现有脚本的自定义 loss 裁剪正是省显存的关键
更高余量方案    装 bitsandbytes 走 4-bit QLoRA（venv 里目前没有 bnb，属于新增依赖）
```

### 1 本机已有的训练证据

```text
训练环境    D:\D_program\venvs\minimind（Python 3.12.13）
            torch 2.9.1+cu128（cuda_available=True）
            transformers 4.57.6 / peft 0.21.1 / accelerate 1.15.0 / datasets 3.6.0
            trl 缺失，bitsandbytes 缺失

已跑通的训练
  Qwen3-0.6B LoRA SFT（train_lora.py，497 条样本，3 epochs）
  Qwen3-0.6B GRPO（52 个优化步，29.3 分钟，峰值显存 2.82 GB）
  训练日志：D:\D_program\logs\grpo_r0_train_master.out 等
```

手写脚本 `train_lora.py` 的现成保护：

```text
bf16 权重 + LoRA r16 / alpha32 / dropout0.05 / all-linear
非重入式梯度检查点（model.train() 模式，避免检查点被静默跳过）
只对 assistant 段算 loss，尾部 hidden 分块算 logits（避免整段 8K logits 占 5 GB）
显存三件套：cache>4 GB 清缓存、reserved>6.5 GB 中止、全卡>7.2 GB 看门狗硬杀
--calibrate：只跑 6 步，实测峰值显存与吞吐，再外推总时长
```

### 2 1.5B 的显存账（推算）

```text
Qwen2.5-1.5B（1.78B 参数）bf16 权重     ≈ 3.5 GB
LoRA 参数 + 梯度 + Adam 状态            < 0.3 GB（只训 adapter）
激活（梯度检查点，seq 8192）             0.6B 实测 2.82 GB 峰值；
                                        1.5B 隐层 1536 vs 1024，激活约 2.25×

粗算 seq 8192：3.5 + 0.3 + 约 3.4 + 上下文 0.6 ≈ 7.8 GB —— 顶到 8 GB 上限，风险高
粗算 seq 4096：约 5.0–5.8 GB —— 留出余量，推荐
粗算 seq 2048：约 4.3–4.8 GB —— 更稳，适合先跑标定
```

所以你的担心是对的：1.5B + 8192 序列在 8 GB 上容易 OOM；把序列压到 2048–4096 后可行。

### 3 TRL 还是手写

```text
维度            手写 train_lora.py（推荐）           TRL SFTTrainer
是否已跑通      本机 0.6B SFT/GRPO 都跑通过           本机没装 trl，需要新装/配环境
省显存手段      自定义 assistant-only loss、         依赖 gradient_checkpointing /
                分块 logits（关键省显存点）           packing，8 GB 上更激进
显存守卫        已有 cache/guard/watchdog 三层        需要自己补
适配 1.5B       改 --model + --max-seq 即可           需要新环境（trl+transformers 版本匹配）
风险            低                                    依赖冲突 + 显存策略不可控
```

建议：第一轮用现有 `train_lora.py` 跑 1.5B（`--max-seq 4096`，先 `--calibrate`）；
如果确认显存仍有富余，再考虑 TRL 或 QLoRA。

### 4 若之后要跑（本轮未执行）

```text
1  先停 llama-server，释放约 4.3 GB
2  用 D:\D_program\venvs\minimind\Scripts\python.exe
3  python train_lora.py --model D:\D_program\models\Qwen2.5-1.5B-Instruct \
       --max-seq 4096 --calibrate
4  看标定输出的 peak_vram_gb：
     < 6.0 GB   → 可以正式训练（epochs/grad-accum 按需）
     触发 guard → 降到 --max-seq 2048，或改装 bitsandbytes 走 QLoRA
```

### 5 文件

```text
手写训练脚本   D:\D_program\models\Qwen3-0.6B-sft-off-lora\run_bundle_20260930\train_lora.py
训练环境       D:\D_program\venvs\minimind（torch 2.9.1+cu128）
底模           D:\D_program\models\Qwen2.5-1.5B-Instruct
训练日志       D:\D_program\logs\grpo_r0_train_master.out、sft_off_train.log.jsonl
```


