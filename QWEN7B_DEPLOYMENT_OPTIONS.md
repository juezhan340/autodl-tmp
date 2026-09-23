# Qwen 7B 本地推理后端综合分析

更新时间：2026-09-19

> 本机落地状态：llama.cpp 已通过源码压缩包解压并构建 CUDA 后端，Qwen2.5-7B-Instruct Q5_K_M 双分片已完成 SHA256 校验。命令行、OpenAI 兼容 API、8K/16K/32K 上下文和 1/2/4 路并发均已通过实测；`llama-bench` 的单流生成基线为 `151.18 +/- 15.92 token/s`。初始损坏分片已隔离到 `models/qwen2.5-7b-instruct-gguf/corrupt-20260919/`，不参与任何有效测试。

## 1. 结论先行

本文默认讨论 `Qwen/Qwen2.5-7B-Instruct`。如果实际使用的是 Qwen1.5、Qwen2、Qwen2.5-Coder、Qwen3 或其他量化版本，启动参数和模型目录需要相应调整。

这里的目标是单机本地部署，用模型执行科研任务，例如批量生成、分类、信息抽取、摘要和评测。当前首要指标是生成速度，尤其是单请求的 decode tokens/s；并发、输出质量和上下文长度作为第二层约束分析。本文不讨论训练。

以下排序是针对当前机器的 **RTX 4090 24 GB、Qwen 7B、低并发或单流生成**，不是所有 GPU 和所有任务的绝对排名：

1. **单流速度上限：`ExLlamaV3 + EXL3 4.0/5.0 bpw`**
   - 面向 NVIDIA 消费级 GPU 的量化推理，通常是本机单请求 decode 速度最值得测试的路线。
   - 代价是模型格式、量化文件和 Python/CUDA 版本匹配更复杂。
   - 适合只关心生成速度和最终文本的任务。

2. **速度、稳定性和部署成本的平衡：`llama.cpp + GGUF Q4/Q5_K_M`**
   - CUDA 后端成熟，模型占用低，单流速度通常很好。
   - 适合本地离线任务，不需要 Python 推理栈。
   - `Q5_K_M` 更偏质量，`Q4_K_M` 更偏速度和显存余量。

3. **愿意构建专用 engine：`TensorRT-LLM`**
   - 调优后可能有很高的单流和批量性能。
   - 需要构建 engine、匹配 CUDA/TensorRT-LLM 版本，维护成本最高。
   - 对单个 7B 模型和一张 4090，除非追求极限 benchmark，否则不一定划算。

4. **需要并发或批量调度：`vLLM` / `SGLang`**
   - 重点优势是 continuous batching、KV cache 管理和调度，不是单请求峰值速度。
   - 并发请求或大量独立样本时，总 tokens/s 可能明显高于单纯串行推理。
   - 如果只处理一个请求，未必比 ExLlamaV3 或 llama.cpp 更快。

5. **质量和可控性基线：`Transformers + PyTorch`**
   - 最适合核对 FP16 输出、做自定义处理和建立质量基线。
   - 纯 decode 速度通常不是最高，不应作为当前“最大 token/s”目标的第一选择。

6. **最简单但不适合测速调优：`Ollama`**
   - 使用方便，本质上更像封装层。
   - 适合验证模型，不适合作为速度优化的主测试对象。

### 1.1 单卡是否很难支持并发

7B 模型在单张 RTX 4090 上并不是不能并发。只要显存中能同时放下模型权重、KV cache 和运行时 workspace，就可以同时维护多个生成序列。真正的限制是：

- 并发越高，每个请求分到的计算资源越少，单请求 tokens/s 通常下降。
- 在 GPU 尚未饱和时，并发可能改善批量任务的整体完成时间；达到饱和后，继续加并发只会增加排队和延迟。
- 上下文越长，KV cache 占用越大，可支持的并发数越少。
- 长 prompt 的 prefill 和生成阶段会相互影响，不能只看 decode tokens/s。

因此，“不需要并发”时应优先优化单流速度；只有在同时运行多个独立任务，或总任务完成时间比单条延迟更重要时，才值得启用批处理或并发调度。

### 1.2 本文中的速度口径

- **Prefill speed**：处理输入 prompt 的速度，输入很长时重要。
- **Decode speed**：已经开始生成后，每秒生成多少 token，是本文的主要指标。
- **TTFT**：从提交请求到第一个输出 token 的时间。
- 本文当前落地报告以**单请求速度和延迟**为主；多请求合计吞吐只在明确讨论批量任务时单独说明。

## 2. 当前机器条件

本机已检查到的关键环境：

| 项目 | 当前值 |
|---|---|
| GPU | NVIDIA GeForce RTX 4090，24,564 MiB 显存 |
| NVIDIA Driver | 580.105.08 |
| 驱动支持的 CUDA | 13.0 |
| CUDA Toolkit / nvcc | 12.8.93，路径为 `/usr/local/cuda/bin/nvcc` |
| Python | 3.12.3 |
| PyTorch | 2.8.0+cu128 |
| `torch.version.cuda` | 12.8 |
| cuDNN | 9.10.2 |
| GPU 可用性 | `torch.cuda.is_available() == True` |
| Conda 环境 | 当前只有 `base` |
| 工作目录 | `/root/autodl-tmp` |
| llama.cpp 源码 | `/root/autodl-tmp/llama.cpp` |
| llama.cpp 构建产物 | `/root/autodl-tmp/llama.cpp/build/bin` |
| 模型目录 | `/root/autodl-tmp/models/qwen2.5-7b-instruct-gguf` |

当前 `base` 环境中已经有 PyTorch，但还没有安装 `transformers`、`vllm`、`sglang`、`bitsandbytes` 或 Python 版 `llama-cpp`。不建议为了安装 vLLM 或 SGLang 直接改造 `base` 环境。

当前 `/root/autodl-tmp` 约有 38 GiB 可用空间；Q5_K_M 双分片合计约 5.07 GiB（5.44 GB），损坏下载备份约 6.7 GiB。失败文件当前仍保留；确认不再需要排查下载问题后，可以删除 `corrupt-20260919` 回收空间。

## 3. 模型与显存估算

Qwen2.5-7B-Instruct 官方模型约 7.61B 参数，FP16 权重文件约 15.2 GB，采用 28 层结构和 GQA。不同后端还需要为 CUDA workspace、临时激活和 KV cache 留空间。

下面是实际选型时可用的粗略范围，具体数值取决于量化格式、上下文长度、批大小和后端实现：

| 权重格式 | 权重占用粗略范围 | RTX 4090 上的建议 |
|---|---:|---|
| FP16/BF16 | 14-16 GB | 适合 Transformers/vLLM；上下文先从 8K 开始 |
| Q8 | 8-10 GB | 质量接近 FP16，适合 llama.cpp |
| Q6 | 6-8 GB | 质量和显存的折中 |
| Q5_K_M | 5-7 GB | 本机 llama.cpp 的默认推荐 |
| Q4_K_M / AWQ 4-bit | 4-6 GB | 显存余量大，适合更长上下文或更高并发 |

### 3.1 理论上下文长度与实际可用长度

Qwen2.5-7B-Instruct 的模型规格支持扩展到约 `131072` token，但这不是 RTX 4090 上的默认实用配置。对于超过模型默认上下文的长度，还需要模型配置、RoPE/YaRN 设置和后端实现共同支持；只把 `context length` 参数调大，并不能保证结果质量或显存可用。

对当前 24 GB 显存，建议把下面的数字当作起始测试区间，而不是硬性保证：

| 方案 | 建议起始上下文 | 进一步测试范围 | 说明 |
|---|---:|---:|---|
| Transformers FP16 | 8K | 16K，谨慎测试 32K | 权重占用大，长上下文和并发的余量较小 |
| vLLM FP16 | 8K | 16K-32K | `max_model_len` 是上限，不代表一定能稳定运行 |
| ExLlamaV3 EXL3 4-5 bpw | 8K-16K | 32K 及以上需实测 | 量化权重节省显存，但 KV cache 仍会增长 |
| llama.cpp GGUF Q4/Q5 | 8K-16K | 32K，长上下文谨慎 | 可通过量化留出更多显存，速度会受 prompt 长度影响 |
| TensorRT-LLM | 8K | 按 engine 配置测试 | 最大序列长度通常需要在 engine 配置/构建时规划 |
| Ollama | 8K | 由 `num_ctx` 和显存决定 | 本质仍受底层 llama.cpp 和 KV cache 限制 |

### 3.2 KV cache 为什么会限制并发

按 Qwen2.5-7B 的 28 层、4 个 KV heads、128 的 head dimension 和 FP16 KV cache 粗略估算，单个序列的 KV cache 约为：

| 单个序列上下文 | KV cache 粗略占用 |
|---:|---:|
| 8K | 约 448 MiB |
| 16K | 约 896 MiB |
| 32K | 约 1.75 GiB |
| 131K | 约 7.0 GiB |

这只是 KV cache，不包括模型权重、临时激活、CUDA workspace、分页/对齐开销和输出增长。实际后端会因 KV cache 精度、内存布局和调度方式产生差异。

本机 llama.cpp 实测与上述估算一致：8K、16K、32K 的 CUDA KV buffer 分别为 448、896、1792 MiB。Q5_K_M 权重加载到 GPU 后约占 4829 MiB，因此在 24 GB 显存上运行单路 32K 仍有较大余量。并发时需要按所有活动序列的上下文总量规划 KV cache，而不是只看单个请求的上限。

因此，量化权重主要解决“模型能否装下”和“能否为 KV cache 留空间”，并不会让长上下文的计算成本消失。对于本机，建议先以 `8192` 上下文建立速度基线，再分别测试 `16384` 和 `32768`。

## 4. 方案一：llama.cpp + GGUF

### 4.1 适用场景

- 离线批量推理和结果文件生成。
- 想要较低的显存占用。
- 希望同时支持 CUDA、CPU+GPU 混合或后续切换到其他机器。
- 不需要访问模型内部张量，只需要最终文本结果。

### 4.2 优点与限制

优点：

- C/C++ 后端，运行时依赖少。
- GGUF 量化生态成熟，Q4/Q5/Q6/Q8 都容易切换。
- 支持完整 GPU offload，也支持 CPU+GPU 混合推理。
- `llama-server` 可直接提供 HTTP API。

限制：

- 需要使用 GGUF 权重，不能直接拿 Hugging Face Safetensors 目录启动。
- 如果要访问模型内部结果、改模型结构或深度定制生成逻辑，不如 Transformers 灵活。
- 版本更新较快，部分参数名称可能随构建版本变化。

### 4.3 编译 CUDA 版本

本机采用发布源码压缩包下载后解压的方式，避免为安装 llama.cpp 拉取 git 仓库：

```bash
cd /root/autodl-tmp
mkdir -p llama.cpp
tar -xzf llama.cpp-master.tar.gz -C llama.cpp --strip-components=1
cd llama.cpp

cmake -S . -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF

cmake --build build --config Release -j 16 \
  --target llama-cli llama-server llama-bench
```

本机 CUDA Toolkit 位于 `/usr/local/cuda`，构建产物已经确认链接 `libggml-cuda`、CUDA runtime 和 cuBLAS。若当前 shell 找不到 `nvcc`，使用绝对路径即可：

```bash
export PATH=/usr/local/cuda/bin:$PATH
```

### 4.4 获取官方 GGUF

Q5_K_M 在官方仓库中是两个 GGUF 分片，启动时只需要把第一个分片路径传给 llama.cpp，它会根据 GGUF 元数据读取第二个分片。不要把两个分片拼接成一个文件，也不要把 `*.aria2` 控制文件当作模型。

本机使用 ModelScope 镜像和 `aria2c` 下载，按官方 SHA256 校验：

```bash
mkdir -p /root/autodl-tmp/models/qwen2.5-7b-instruct-gguf

aria2c --dir=/root/autodl-tmp/models/qwen2.5-7b-instruct-gguf \
  --out=qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf \
  --file-allocation=none --check-integrity=true \
  --checksum=sha-256=42f6693004793ee6cf1b2b723f0273b10f86a3bb2a949bd9128d4cda5fb866cd \
  --max-connection-per-server=8 --split=8 --min-split-size=20M \
  'https://modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/master/qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf'

aria2c --dir=/root/autodl-tmp/models/qwen2.5-7b-instruct-gguf \
  --out=qwen2.5-7b-instruct-q5_k_m-00002-of-00002.gguf \
  --file-allocation=none --check-integrity=true \
  --checksum=sha-256=beba9d4f2f5a1fe7d144dcae332e68b52c26705c5310dece2e5d1997e091e134 \
  --max-connection-per-server=8 --split=8 --min-split-size=20M \
  'https://modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/master/qwen2.5-7b-instruct-q5_k_m-00002-of-00002.gguf'

sha256sum /root/autodl-tmp/models/qwen2.5-7b-instruct-gguf/*.gguf
```

期望文件大小分别为 `3989841792` 和 `1454989568` 字节，哈希必须分别为上面的两个值。若目录中存在 `*.aria2`，说明下载器尚未完成最终校验。若更重视质量，可以换成 `Q6_K` 或 `Q8_0`；如果更重视显存和长上下文，可以选择 `Q4_K_M`。

### 4.5 启动命令行推理

```bash
cd /root/autodl-tmp/llama.cpp

./build/bin/llama-cli \
  -m /root/autodl-tmp/models/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf \
  -ngl all \
  -fa on \
  -c 8192 \
  -n 512 \
  --single-turn \
  --simple-io
```

参数说明：

- `-ngl all`：把所有可 offload 的层放到 GPU；当前版本也支持具体层数。
- `-fa on`：启用 Flash Attention 路径；当前构建已包含 CUDA Flash Attention 实现。
- `-c 8192`：上下文长度先设置为 8K。
- `--single-turn`：处理一个预设请求后退出，适合脚本任务。
- `--simple-io`：适合重定向到文件或由任务脚本调用。

### 4.6 启动 HTTP 服务

```bash
cd /root/autodl-tmp/llama.cpp

./build/bin/llama-server \
  -m /root/autodl-tmp/models/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf \
  -a qwen2.5-7b-instruct \
  -ngl all \
  -fa on \
  -c 8192 \
  -b 2048 \
  -ub 512 \
  -np 1 \
  --host 127.0.0.1 \
  --port 8080 \
  --no-ui
```

测试 OpenAI 兼容接口：

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-7b-instruct",
    "messages": [{"role": "user", "content": "用一句话介绍你自己"}],
    "temperature": 0.7,
    "max_tokens": 128
  }'
```

### 4.7 对当前机器的评价

这是本机最稳妥的实用方案。它未必在所有负载下达到绝对最高速度，但部署成本明显低于 ExLlamaV3/TensorRT-LLM，适合作为第一条速度基线。推荐组合为：

```text
Qwen2.5-7B-Instruct-GGUF / Q5_K_M / llama-server / context 8192
```

当前构建版本为 `llama.cpp 0.4.1-dev`，可执行文件位于 `/root/autodl-tmp/llama.cpp/build/bin`，CUDA 设备枚举为 `CUDA0: NVIDIA GeForce RTX 4090`。两个有效分片已经通过 SHA256 校验；命令行和 HTTP API 都能按 ChatML 模板输出正常中文。损坏分片曾产生重复 token，已经隔离且不能用于判断后端性能。

如果目标是单请求生成速度，先比较 `Q5_K_M` 和 `Q4_K_M`。如果 llama.cpp 的速度仍不满足要求，再测试 ExLlamaV3；如果需要查看 logits 或 hidden states，再使用 Transformers。

### 4.8 本机实测结果

测试日期为 2026-09-19。统一使用 Qwen2.5-7B-Instruct Q5_K_M、全部层 GPU offload、Flash Attention、CUDA `sm_89` 构建。下面的结果只代表当前机器和当前构建，不应直接外推到其他 llama.cpp 版本或量化文件。

`llama-bench` 使用 512-token prompt、生成 128 token、重复 3 次：

| 测试项 | 结果 |
|---|---:|
| Prefill `pp512` | `9761.76 +/- 1092.59 token/s` |
| Decode `tg128` | `151.18 +/- 15.92 token/s` |

OpenAI 兼容接口 `/v1/chat/completions` 已通过真实请求验证。测试问题得到正确输出“4，因为这是基本的加法运算，两个2相加得到4。”；该次请求处理 53 个 prompt token 时为 1297.78 token/s，生成 18 token 时为 141.57 token/s。因为输出过短，API 单次结果只作为功能验证，稳定速度以 `llama-bench` 为准。

不同上下文上限下的 CUDA 显存分解如下。`self` 为 llama.cpp 报告的模型、KV cache 和 compute buffer 之和；运行时另有约 448 MiB 未归类开销。

| 上下文 | 模型 | KV cache | Compute | `self` 合计 | 报告空闲显存 |
|---:|---:|---:|---:|---:|---:|
| 8K | 4829 MiB | 448 MiB | 140 MiB | 5417 MiB | 18214 MiB |
| 16K | 4829 MiB | 896 MiB | 148 MiB | 5873 MiB | 17758 MiB |
| 32K | 4829 MiB | 1792 MiB | 164 MiB | 6785 MiB | 16846 MiB |

并发测试固定为 4 个 server slots、每槽 8K 上下文，每个请求强制生成 256 token，每组重复 3 次并取中位数。下面只保留单请求速度：

| 同时请求数 | 单请求平均 decode | 相对单路变化 |
|---:|---:|---:|
| 1 | 149.54 token/s | 基线 |
| 2 | 132.95 token/s | -11.1% |
| 4 | 116.30 token/s | -22.2% |

结论是这张 4090 可以支持 Qwen 7B 并发，但并发会降低单请求速度：4 路时每个请求约慢 23%。当前科研任务如果一次只处理一条生成，应保持 `-np 1`；如果确实需要同时处理多个独立样本，可使用 `-np 2` 或 `-np 4`，同时按“每槽上下文 x 槽位数”扩大 `-c`。

单并发真实请求的延迟结果另见 [llama.cpp + Qwen 7B 部署与性能实测报告](LLAMA_CPP_QWEN7B_DEPLOYMENT_BENCHMARK.md)：32K 输入时 TTFT 约 4.04 秒，完整请求约 5.19 秒，固定生成 128 token 的输出 decode 约 111.72 token/s。

## 5. 方案二：Transformers + PyTorch

### 5.1 适用场景

- 需要直接修改 Python 推理代码。
- 需要控制 tokenizer、chat template、采样、停止词或 logits processor。
- 需要做实验、调试模型输入输出或自定义推理逻辑。
- 批量处理数据集，并把中间结果、概率或评测指标写入文件。
- 需要调试模型输入输出和自定义推理逻辑。

### 5.2 建议单独建环境

```bash
conda create -n qwen-transformers python=3.12 -y
conda activate qwen-transformers

pip install -U torch transformers accelerate safetensors
```

如果需要 4-bit 量化，再安装：

```bash
pip install -U bitsandbytes
```

### 5.3 FP16 推理示例

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen2.5-7B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto",
)

messages = [{"role": "user", "content": "用三点说明本机适合哪种推理后端。"}]
inputs = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_dict=True,
    return_tensors="pt",
).to(model.device)

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=256,
        do_sample=True,
        temperature=0.7,
        top_p=0.8,
    )

answer = outputs[0][inputs["input_ids"].shape[-1]:]
print(tokenizer.decode(answer, skip_special_tokens=True))
```

### 5.4 4-bit 方案

当上下文较长或需要为多个请求预留显存时，可以使用 `bitsandbytes` 4-bit：

```python
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    quantization_config=quant_config,
    device_map="auto",
)
```

4-bit 适合节省显存，但不应默认认为它在所有任务上与 FP16 完全等价。建议先用 FP16 建立基线，再比较回答质量和速度。

### 5.5 对当前机器的评价

这是当前需求的质量和功能基线，不是最大 decode tokens/s 的主推荐。当前机器的 24 GB 显存可以直接尝试 FP16，建议把上下文限制在 8K 或 16K。用它确认量化模型是否在目标任务上产生可接受的质量变化。

## 6. 方案三：vLLM

### 6.1 适用场景

- 大规模离线批量推理。
- 想让框架自动管理 batch、KV cache 和 GPU 调度。
- 后续可能把同一套模型改造成 API 服务。
- 只有在确实需要时，才使用它的 OpenAI 兼容服务模式。

vLLM 官方提供 `vllm serve` 和 OpenAI 兼容接口。Qwen2.5-7B-Instruct 模型卡也直接给出了 vLLM 启动方式，并推荐 vLLM 用于部署。

### 6.2 安装建议

不要直接在当前 `base` 环境中安装，建议使用独立环境：

```bash
conda create -n qwen-vllm python=3.12 -y
conda activate qwen-vllm
pip install -U vllm
```

安装前后应检查：

```bash
python -c 'import torch, vllm; print(torch.__version__, torch.version.cuda, vllm.__version__)'
```

如果 pip 为满足依赖而替换了 Torch，优先以该环境实际测试结果为准，不要把它和当前 `base` 环境混用。

### 6.3 FP16 启动

```bash
conda activate qwen-vllm

vllm serve Qwen/Qwen2.5-7B-Instruct \
  --dtype half \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --served-model-name qwen2.5-7b \
  --host 127.0.0.1 \
  --port 8000
```

### 6.4 离线批处理示例

如果不需要 HTTP 服务，可以直接在脚本中使用 vLLM：

```python
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

messages_list = [
    [{"role": "user", "content": "请从下面的摘要中提取研究问题：..."}],
    [{"role": "user", "content": "请把下面的实验结果归纳成三点：..."}],
]

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
prompts = [
    tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    for messages in messages_list
]

llm = LLM(
    model="Qwen/Qwen2.5-7B-Instruct",
    dtype="half",
    max_model_len=8192,
    gpu_memory_utilization=0.90,
)

sampling = SamplingParams(
    temperature=0.0,
    max_tokens=256,
)

outputs = llm.generate(prompts, sampling)
for prompt, output in zip(prompts, outputs):
    print({"prompt": prompt, "answer": output.outputs[0].text})
```

对于真正的科研批处理，应自行把输入、模型版本、采样参数、时间戳和输出保存到 JSONL/Parquet，而不是只打印到终端。

请求示例：

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-7b",
    "messages": [{"role": "user", "content": "你好"}],
    "temperature": 0.7,
    "max_tokens": 128
  }'
```

### 6.5 AWQ 4-bit 启动

如果 FP16 在目标上下文或并发下显存不足，可以尝试官方 AWQ 变体：

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ \
  --quantization awq \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --served-model-name qwen2.5-7b-awq \
  --host 127.0.0.1 \
  --port 8000
```

是否显式指定 `--quantization awq` 取决于当前 vLLM 是否能从模型配置自动识别；如果自动识别成功，可以去掉该参数。

### 6.6 对当前机器的评价

如果一次要处理大量独立样本，或未来确实要并发，vLLM 是本机的重要对照方案。建议先把 `max_model_len` 设置为 8192，分别测并发 1、2、4；如果要提高上下文或并发，再评估 AWQ。只跑单请求时，不要预设它一定快过 ExLlamaV3 或 llama.cpp。

需要注意，vLLM 的 `--api-key` 不是完整的网络安全边界。仅在本机使用时绑定 `127.0.0.1`；对外暴露时，应放在认证和反向代理之后。

## 7. 方案四：ExLlamaV3 + EXL3

### 7.1 适用场景

- 只追求 NVIDIA 消费级 GPU 上的单流生成速度。
- 接受使用专用量化格式，而不是原始 Safetensors 或 GGUF。
- 主要关心最终文本，不依赖复杂的模型内部张量接口。

### 7.2 输出质量与速度

ExLlamaV3 的优势来自专门的 CUDA 推理路径和 EXL3 weight-only 量化。建议优先比较 `4.0 bpw` 和 `5.0 bpw`：

- `5.0 bpw`：更接近 FP16 的质量，通常是质量/速度的平衡点。
- `4.0 bpw`：显存更省，速度和可支持上下文通常更有优势，但更应该用目标任务评测质量。

和其他后端一样，最终质量主要由量化权重决定；同一个量化模型换后端，质量差异通常小于从 FP16 换到 4-bit 产生的差异。

### 7.3 并发与上下文

ExLlamaV3 适合把单流速度作为第一指标。它可以支持一定程度的并行推理，但若目标是很多请求的自动排队、连续批处理和服务调度，vLLM/SGLang 通常更方便。

EXL3 权重更省显存，可以给 KV cache 留出更多空间；但上下文长度仍受模型的 RoPE/YaRN 配置和 GPU 显存限制。建议从 8K 或 16K 开始，不要把模型理论最大上下文直接作为配置值。

### 7.4 对当前机器的评价

这是本机最值得测试的“单流速度上限”方案，但不是最省事的方案。当前 Python 3.12 环境不应直接假设与所有 ExLlamaV3 wheel 兼容，建议建立独立环境，按目标版本官方安装说明匹配 Python、PyTorch、CUDA 和量化模型。

## 8. 方案五：TensorRT-LLM

### 8.1 适用场景

- 愿意为固定模型、固定精度和固定上下文构建专用 engine。
- 追求较高的单流速度或批量调度性能，并愿意投入调优成本。
- 能接受 engine 构建时间、版本绑定和部署复杂度。

### 8.2 输出质量与速度

TensorRT-LLM 可以使用 FP16、FP8 或其他量化路径，实际质量由 engine 使用的精度和量化校准决定。FP16 更适合作为质量基线；低精度路径需要用目标科研任务做回归测试。

它的速度上限可能很高，但不能仅凭“使用 TensorRT”就推断一定快过 ExLlamaV3 或 llama.cpp。对于 7B 单卡任务，engine 构建和参数调优成本可能超过节省的运行时间。

### 8.3 并发与上下文

TensorRT-LLM 的优势更容易在 in-flight batching、分页 KV cache 和稳定的服务负载下体现。单流时应和 ExLlamaV3、llama.cpp 做实测；并发时需要同时观察单请求速度、TTFT 和完整请求耗时。

上下文长度通常需要在 engine 配置或构建阶段规划。增大最大序列长度会增加内存需求；为 131K 上下文构建 engine 不等于实际能在 24 GB RTX 4090 上高效运行。

### 8.4 对当前机器的评价

它是“愿意做性能工程”时的进阶选项，不是当前最推荐的第一步。建议先用 llama.cpp 或 ExLlamaV3 建立基线，只有基线不能满足速度目标时再投入 TensorRT-LLM。

## 9. 方案六：SGLang

### 9.1 适用场景

- 想测试 vLLM 之外的高性能服务后端。
- 需要较强的批处理、结构化输出或复杂服务编排能力。
- 可以接受使用官方容器或独立环境解决依赖问题。

### 9.2 启动思路

Qwen2.5-7B-Instruct 模型卡给出了 SGLang 的服务示例。典型方式是使用官方容器：

```bash
docker run --gpus all \
  --shm-size 32g \
  --ipc=host \
  -p 30000:30000 \
  -v /root/autodl-tmp/huggingface:/root/.cache/huggingface \
  lmsysorg/sglang:latest \
  python3 -m sglang.launch_server \
    --model-path Qwen/Qwen2.5-7B-Instruct \
    --host 0.0.0.0 \
    --port 30000
```

如果当前容器没有 Docker，建议先不要为了 7B 模型专门改造系统环境，优先使用 llama.cpp 或 vLLM。SGLang 的 pip 安装方式和 CUDA/Torch 兼容关系变化较快，应以目标版本的官方安装说明为准。

### 9.3 对当前机器的评价

SGLang 可以作为性能对比对象，但不是本机的第一落点。除非已经有明确的并发、结构化生成或服务编排需求，否则 vLLM 的维护成本通常更低。

## 10. 方案七：Ollama

### 10.1 适用场景

- 想最快启动一个本地模型。
- 主要是交互式聊天、命令行调用或简单 API。
- 不希望手动管理 GGUF、CUDA 编译和 Python 依赖。

典型用法：

```bash
ollama run qwen2.5:7b
```

Ollama 也提供本地 HTTP 接口，默认监听 `11434`。具体模型标签、量化版本和后端行为以本机 Ollama 版本和模型库为准。

### 10.2 优点与限制

优点：安装和调用简单，模型管理方便。

限制：

- 对底层 GPU offload、批处理和 KV cache 的控制不如直接使用 llama.cpp/vLLM。
- 服务参数和模型打包由 Ollama 抽象，排查性能问题时透明度较低。
- 如果最终要做正式 API 服务，通常仍会回到 vLLM、SGLang 或直接 llama.cpp。

### 10.3 对当前机器的评价

适合快速演示，不建议作为后续性能优化和服务化的唯一后端。若只是临时验证 Qwen 是否能用，Ollama 是最省事的路径之一。

## 11. 方案对比

以下是基于各方案定位的预期，不代替本机实测。速度等级只用于决定先测试谁，不能当作承诺的 tokens/s。

| 方案 | 常用权重 | 单流 decode 潜力 | 并发调度能力 | 质量上限 | 上下文控制 | 安装维护 | 本机定位 |
|---|---|---:|---:|---:|---:|---:|---|
| ExLlamaV3 | EXL3 4-5 bpw | 很高 | 中到高 | 中到高 | 高 | 高 | **单流速度优先测试** |
| llama.cpp | GGUF Q4/Q5/Q6/Q8 | 高 | 中 | 中到高 | 很高 | 低到中 | **综合首选** |
| TensorRT-LLM | FP16/FP8/量化 engine | 很高，需调优 | 很高 | 很高 | 中 | 很高 | 极限性能工程 |
| vLLM | FP16/BF16/AWQ | 中到高 | 很高 | 很高 | 高 | 中到高 | 并发和批量调度 |
| SGLang | FP16/BF16/量化权重 | 中到高 | 很高 | 很高 | 高 | 高 | 服务和复杂调度 |
| Transformers | FP16/BF16/bitsandbytes | 中 | 低到中 | 很高 | 很高 | 中 | 质量与功能基线 |
| Ollama | 封装后的 GGUF | 中到高 | 中 | 取决于量化 | 中 | 很低 | 快速验证 |

### 11.1 输出质量与速度

后端本身通常不是输出质量差异的主要来源。影响更大的因素依次是：

1. 模型版本和 chat template 是否一致。
2. 权重精度与量化方法。
3. 上下文扩展方式是否正确，例如 RoPE/YaRN 配置。
4. temperature、top-p、top-k、重复惩罚、随机种子和停止条件。
5. 后端数值实现造成的小幅差异。

如果使用随机采样，即使底层 logits 只有很小差异，也可能在后续 token 中逐步放大。做后端质量比较时，应先使用 `temperature=0` 或等价的确定性解码，再比较随机采样结果。

| 精度/量化 | 输出质量预期 | 显存 | 单流速度预期 | 建议用途 |
|---|---|---:|---:|---|
| FP16/BF16 | 质量基线 | 最高 | 中到高，依赖后端 | 建立科研任务基线 |
| Q8 / 8-bit | 通常很接近 FP16 | 高 | 高 | 重视质量且想节省显存 |
| Q6 / EXL3 5-6 bpw | 通常接近 FP16 | 中 | 高到很高 | 推荐质量/速度平衡 |
| Q5_K_M / EXL3 5 bpw | 较好的平衡 | 中低 | 很高 | 当前 4090 的推荐候选 |
| Q4_K_M / EXL3 4 bpw / AWQ 4-bit | 任务相关的轻微到明显损失 | 低 | 较强，需实测 | 速度、上下文和并发优先 |

不能简单认为位数越低就一定越快。某些量化 kernel、batch size 和 GPU 架构组合可能让 Q5 快于 Q4，或让 FP16 在特定 prefill 阶段表现很好，必须在本机测试。

### 11.2 并发的影响

单卡并发的核心关系如下：

```text
并发增加
  -> GPU 利用率提高
  -> 总 tokens/s 上升
  -> 每请求 tokens/s 通常下降
  -> TTFT 和尾延迟通常上升
  -> KV cache 显存线性增长
```

对于当前 RTX 4090 和 Qwen 7B，短到中等上下文下支持 `2-4` 个并发序列通常是合理的测试起点；这不是容量保证。能否继续增加到 `8` 或更多，取决于权重格式、上下文长度、输出长度和后端的 KV cache 管理。

| 目标 | 合适配置 | 后端倾向 |
|---|---|---|
| 单条任务最快完成 | 并发 1 | ExLlamaV3、llama.cpp、调优后的 TensorRT-LLM |
| 两到四个独立任务同时跑 | 并发 2/4，观察每请求速度 | vLLM、SGLang、llama.cpp server |
| 大量样本尽快全部完成 | 动态 batching，另行评估批量完成时间 | vLLM、SGLang、TensorRT-LLM |
| 需要自定义 logits/内部状态 | 手工 micro-batch | Transformers |

如果科研任务本身是一个长序列生成，不要为了“并发支持”更换后端，直接用并发 1 获取最高单任务速度。如果有几千条独立样本，再单独评估 vLLM/SGLang 的整批完成时间。

### 11.3 上下文长度的影响

上下文越长，会同时带来三种成本：

- KV cache 显存近似线性增长。
- prefill 计算量显著增加，TTFT 变长。
- 可同时运行的序列数减少。

后端能够设置 32K 或 131K，不代表该长度在当前 24 GB 显存上高效，也不代表扩展后的输出质量与模型默认上下文相同。对本机的建议是：

1. `8K`：默认速度测试和大多数普通任务。
2. `16K`：需要较长论文、报告或多段材料时测试。
3. `32K`：使用量化权重并单独验证显存、TTFT 和输出质量。
4. `131K`：只作为专项长上下文实验，不作为常规配置。

### 11.4 当前目标下的明确排序

只看单请求 decode tokens/s：

```text
优先测试 ExLlamaV3 EXL3 4/5 bpw
  -> 再测试 llama.cpp Q4_K_M/Q5_K_M
  -> 有性能工程预算时测试 TensorRT-LLM
  -> vLLM/SGLang 用于并发和批量调度对照
  -> Transformers FP16 作为质量基线
```

如果不想承担 ExLlamaV3 的环境和模型格式成本，直接选择 `llama.cpp + Q5_K_M`；需要更高速度和更多上下文余量时，再比较 `Q4_K_M`。

## 12. 推荐落地路线

### 路线 A：单流速度优先

```text
Qwen2.5-7B-Instruct EXL3 4/5 bpw
  -> 独立 ExLlamaV3 环境
  -> 并发 1
  -> 测 decode tokens/s、TTFT、显存
```

这是追求单条任务最快完成时间时的第一条测试路线。

### 路线 B：实用平衡

```text
Qwen2.5-7B-Instruct-GGUF Q5_K_M
  -> llama.cpp CUDA
  -> 并发 1
  -> 与 Q4_K_M 做速度/质量对比
```

如果不想维护 ExLlamaV3 的量化格式和环境，直接使用这条路线。它是当前最推荐的工程折中。

### 路线 C：并发或批量调度优先

```text
Qwen2.5-7B-Instruct FP16/AWQ
  -> vLLM 或 SGLang
  -> 并发 1/2/4/8 压测
  -> 比较单请求速度、TTFT、完整请求耗时和整批完成时间
```

这条路线不保证单请求最快，但可能让一批独立任务更快完成。

### 路线 D：质量基线

```text
Qwen2.5-7B-Instruct Safetensors FP16
  -> Transformers
  -> 固定模板、采样和随机种子
  -> 与量化后端比较输出质量
```

如果需要访问 logits、hidden states 或其他内部结果，应使用这条路线。

## 13. 建议的验证顺序

1. 用 Transformers FP16 建立质量基线，固定模型、chat template、采样参数和随机种子。
2. 用完全相同的输入和输出长度测试 ExLlamaV3 EXL3 5 bpw、llama.cpp Q5_K_M 和 Q4_K_M。
3. 预热后分别测 `8K`、`16K` 上下文下的 prefill、decode、TTFT 和显存峰值。
4. 对需要并发的场景，依次测试并发 `1/2/4/8`，重点记录单请求 tokens/s、TTFT、完整请求耗时和 P50/P95 延迟。
5. 只有当单流和并发基线都不能满足目标时，再投入 TensorRT-LLM。

建议同时记录：

```bash
nvidia-smi
nvidia-smi dmon -s pucm
```

重点关注显存峰值、GPU 利用率、TTFT、decode tokens/s、完整请求耗时和输出质量，不要只看平均响应时间。

### 13.1 建议的测速控制条件

- 预热至少 1-2 次，不把模型加载时间计入 decode 速度。
- 固定 prompt token 数，例如 512、2K、8K 三组。
- 固定 `max_new_tokens`，建议先测 256 或 512。
- 温度设为 `0`，避免随机采样影响后端对比。
- 每组至少重复 3-5 次，报告中位数和显存峰值。
- 并发测试使用相同或相近长度的请求，避免长度差异干扰调度。
- 并发场景优先记录每请求速度和请求延迟；只有批处理目标明确时，才额外记录整批完成时间。

单流重点看：

```text
decode tokens/s
TTFT
峰值显存
输出质量
```

并发重点看：

```text
每请求 tokens/s
TTFT
完整请求耗时
P50/P95 延迟
可稳定运行的最大并发
```

## 14. 风险和注意事项

- 不要把 128K 上下文直接作为 RTX 4090 的默认配置；先从 8K 或 16K 开始。
- 不要在当前 `base` 环境中反复安装 vLLM、SGLang、bitsandbytes 并让它们互相覆盖 Torch 依赖。
- 本次模型和构建文件放在已验证可写的 `/root/autodl-tmp`；切换到其他挂载点前先检查可写性和剩余空间。
- 服务若只供本机访问，绑定 `127.0.0.1`；绑定 `0.0.0.0` 前先配置认证、反向代理和访问控制。
- 量化模型的速度和质量不能只按位数判断，应使用同一提示集做对比。
- 使用第三方 GGUF 或量化模型前，应确认来源、模型许可和是否修改了 chat template。

## 15. 最终建议

如果现在就要开始：

1. 直接使用当前已验证的 `llama.cpp + Q5_K_M`，默认 `-np 1 -c 8192`，单流 decode 基线约 151 token/s。
2. 如果需要质量对照，再用 Transformers FP16 建立同一提示集的输出基线。
3. 如果还要提高单流速度，先比较 `Q4_K_M`，再测试 `ExLlamaV3 + EXL3 4/5 bpw`。
4. 如果多个独立任务同时跑或整批完成时间优先，先尝试 llama.cpp 的 `-np 2`/`-np 4`，再决定是否引入 vLLM/SGLang。
5. 只有在愿意构建和维护专用 engine 时，才把 TensorRT-LLM 纳入主方案。

对当前单卡而言，最合理的默认配置是 **并发 1、上下文 8K、最大 32K、先用量化模型测 decode tokens/s、TTFT 和完整请求耗时**。单卡可以支持并发，但并发会降低单请求速度；是否提高并发应由实际任务调度需求决定。

## 16. 参考资料

- Qwen2.5-7B-Instruct 官方模型卡：模型结构、Transformers/vLLM/SGLang 示例。
- Qwen 官方 Qwen2.5 llama.cpp 指南：GGUF 获取、量化选择和 llama.cpp 参数示例。
- ggml-org/llama.cpp 官方 README 与 CUDA 构建文档：`GGML_CUDA=ON`、`llama-server` 和 CUDA 编译器路径。
- ExLlamaV3 官方文档：EXL3 量化、CUDA 推理和 Qwen 模型支持。
- NVIDIA TensorRT-LLM 官方文档：engine 构建、in-flight batching 和 KV cache 相关能力。
- vLLM 官方在线服务文档：`vllm serve` 和 OpenAI 兼容 API。
- SGLang 官方文档与 Qwen 模型卡中的部署示例。
