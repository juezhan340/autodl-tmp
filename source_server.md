# 服务器侧仓库外文件登记（source_server）

## 0 这份文件和 source.md 的分工

GitHub 上 `juezhan340/autodl-tmp` 是主仓库，两个工作端各自有仓库外的文件，分别登记：

```text
source.md          本地（Windows）侧：D:\D_program\ 下的模型、构建、源码、论文
source_server.md   本文：autodl 服务器侧：/root/autodl-tmp 下的非 Git 内容
两份文件自身都进仓库；服务器上的新改动记入本文，Windows 侧改动仍记 source.md
```

source.md §3 开头登记的 Qwen2.5-7B GGUF 属于老服务器时期记录，本服务器上没有该文件，留在原处不动。

## 1 服务器现场（2026-10-04）

```text
ssh         ssh -p 18378 root@connect.westd.seetacloud.com（容器 a6a040af…）
仓库        /root/autodl-tmp/10-04
            origin → git@github.com:juezhan340/autodl-tmp.git（SSH，deploy key autodl-18378）
硬件        RTX 5090 32G（Blackwell，sm_120）· 25 核 · 754G 内存
磁盘        /root/autodl-tmp 50G 数据盘（权重与缓存都放这里）；系统盘 30G 只放 conda 与系统件
网络        ModelScope 直连可用（约 17 MB/s，实测为实例出口上限）
            GitHub HTTPS 直连超时；第三方源码走 ghfast.top 代理（见 §3）
```

## 2 目录结构（/root/autodl-tmp，仓库外）

```text
/root/autodl-tmp
├── 10-04/                       Git 仓库（推 GitHub）
├── models/                      模型权重（§4 登记）
│   ├── Qwen3-0.6B/{hf,gguf}/
│   ├── Qwen2.5-1.5B-Instruct/{hf,gguf}/
│   ├── Qwen3.5-2B/{hf,gguf}/
│   └── _logs/                   下载日志、pid 表
├── llama.cpp/                   第三方推理框架源码 + CUDA 构建（§3）
├── llama.cpp-46847e61.tar.gz    源码包原件（保留，可重解压）
├── model-tools-venv/            modelscope CLI 1.40.1 独立 venv（/bin/ms）
├── sft-venv/                    2026-10-05训练预测试环境，继承PyTorch 2.8.0+cu128
├── training_runs/10-5_sft/      数据划分、微型冒烟adapter、检查点、评测轨迹（不入库）
└── .ms_cache/                   modelscope 下载缓存（实际几乎不用，ms 直写目标目录）
```

## 3 第三方源码

| 路径 | 用途 | 来源与版本 | 恢复方式 |
|---|---|---|---|
| `llama.cpp/` | GGUF 推理与评测（llama-server，对齐 Windows 评测口径） | 上游 `https://github.com/ggml-org/llama.cpp.git`；经 `ghfast.top` 代理取指定 commit 源码包，commit `46847e61582097979f539595d893d83d8e1d1af1`；源码包 SHA-256 `262e86c639f478ac8f853da2695929ee659100acfbad1f3d71af84a21064a96b`（保留在 `/root/autodl-tmp/llama.cpp-46847e61.tar.gz`） | 重新下载：`curl -L -o llama.cpp-46847e61.tar.gz https://ghfast.top/https://github.com/ggml-org/llama.cpp/archive/46847e61582097979f539595d893d83d8e1d1af1.tar.gz` 再解压 |

构建命令（2026-10-04，CUDA 后端，对准 5090 的 sm_120）：

```bash
export PATH=/usr/local/cuda-12.8/bin:$PATH
cmake -S /root/autodl-tmp/llama.cpp -B /root/autodl-tmp/llama.cpp/build \
  -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DLLAMA_CURL=OFF
cmake --build /root/autodl-tmp/llama.cpp/build -j 24
```

```text
产物    /root/autodl-tmp/llama.cpp/build/bin/（llama-server、llama-cli、llama-bench、libggml-cuda.so）
日志    /root/autodl-tmp/llama.cpp/build.log
版本    llama-cli --version → 0.5.0-dev (build 0, commit unknown)
        源码目录无 .git，版本串里没有 commit；权威标识用上面登记的 46847e61

冒烟已验证（2026-10-04 22:55，全部通过）
  llama-cli  -ngl 99 单轮生成 Qwen3-0.6B-Q8_0：576 t/s
  llama-server  -m Qwen3-0.6B-Q8_0.gguf --port 18080 -c 32768 --parallel 2 -ngl 99 --jinja
    /health → {"status":"ok"}；带 chat_template_kwargs.enable_thinking=false 请求，回答 "2 + 3 = 5"
    nvidia-smi 实测该进程占 4792 MiB 显存（0.6B 的 32k×2 slot KV 缓存是主力，不是权重）
  Qwen3 默认开思考：max_tokens 小时 content 为空、文本在 reasoning_content
    跑评测算式时要关思考：Windows 侧是 -rea off，这里是请求里带 enable_thinking=false
```

## 4 模型权重（服务器侧，三个尺寸 × 两种格式）

```text
用途一  推理评测：GGUF Q8_0，供 llama-server（与 Windows 旧评测同源同量化）
用途二  SFT / GRPO 训练：HF safetensors 整仓库（含 tokenizer）
下载    scripts/download_models.sh（6 进程并行，全走 ModelScope）
校验    scripts/verify_models.py → scripts/model_manifest.json / .md（全绿）
```

```text
Qwen3-0.6B-Q8_0.gguf                                             0.64 GB
SHA-256  9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031
来源     ModelScope Qwen/Qwen3-0.6B-GGUF（Q8_0）
路径     models/Qwen3-0.6B/gguf/
训练版   models/Qwen3-0.6B/hf/ ← ModelScope Qwen/Qwen3-0.6B（1.52 GB）

qwen2.5-1.5b-instruct-q8_0.gguf                                  1.89 GB
SHA-256  d7efb072e7724d25048a4fda0a3e10b04bdef5d06b1403a1c93bd9f1240a63c8
来源     ModelScope Qwen/Qwen2.5-1.5B-Instruct-GGUF（Q8_0）
路径     models/Qwen2.5-1.5B-Instruct/gguf/
训练版   models/Qwen2.5-1.5B-Instruct/hf/ ← ModelScope Qwen/Qwen2.5-1.5B-Instruct（3.10 GB）

Qwen3.5-2B-Q8_0.gguf                                             2.01 GB
SHA-256  1b04acba824817554f4ce23639bc8495ff70453b8fcb047900c731521021f2c1
来源     ModelScope unsloth/Qwen3.5-2B-GGUF（Q8_0；多模态仓库，评测只跑文本 + --no-mmproj）
路径     models/Qwen3.5-2B/gguf/
训练版   models/Qwen3.5-2B/hf/ ← ModelScope Qwen/Qwen3.5-2B（4.57 GB，多模态）
```

三个 GGUF 的 SHA-256 与 source.md 里 Windows 端登记值完全一致，说明与 newdoc/05、12 的旧评测同源同量化；完整文件清单见 `scripts/model_manifest.md`。

## 5 配置与密钥（仓库外，只记位置）

```text
~/.ssh/id_ed25519(.pub)      部署密钥 autodl-18378，仅对本仓库有写权限
~/.codex/codex-models.json   Codex 模型表（历次改动备份 .bak-20261004-*）
~/.claude/settings.json      Claude Code 接 DeepSeek（9 项 env；ANTHROPIC_AUTH_TOKEN 留空待填，不入库）
```

## 6 新内容怎么归类（服务器侧口径）

```text
服务器上新写的代码 / 文档
    → 进 10-04 仓库（补齐同名中文 md），commit 并推 GitHub

服务器上下载的权重 / 第三方源码 / 构建产物
    → 留在仓库外，登记进本文：URL、commit 或 SHA-256、路径、恢复命令

密钥、缓存、下载日志
    → 留仓库外，只记位置与生成方法，不记内容
```

## 7 2026-10-05 SFT准备与预测试

```text
代码       10-04/training/10-5_sft/，配同名中文md，进入Git
环境       /root/autodl-tmp/sft-venv/，venv采用system-site-packages
依赖       Transformers4.57.3 / TRL0.24.0 / PEFT0.18.0 / Accelerate1.11.0
           Datasets4.4.1 / Tokenizers0.22.1 / Safetensors0.7.0 / Pytest8.4.2
PyTorch    使用系统已有2.8.0+cu128，没有重复下载CUDA/PyTorch分发包
数据       training_runs/10-5_sft/data/：500训练、100验证、200测试、194备用
冒烟       training_runs/10-5_sft/smoke-*/：仅两次更新和两个epoch检查点
方案       newdoc/17_1.5B_SFT详细执行方案_500训练100验证200测试.md
报告       training/10-5_sft/reports/preflight_report.json及.md
状态       用户已批准500条正式SFT，4×2、连续3epoch已启动；不做200条最终模型评测
```

环境恢复采用本实验的`requirements.txt`，基础PyTorch需与本服务器记录一致；模型仍使用§4已有权重。结果以预测试报告为准，短冒烟不代表正式SFT效果。

当前正式配置已按用户要求调整为micro-batch4、梯度累计2，有效batch8；旧2条轨迹冒烟仍作为历史证据。2026-10-05 02:06（Asia/Shanghai）用户批准后直接启动正式训练，没有另跑GPU压力测试。数据划分内容不变，每个epoch保留完整checkpoint。

```text
展示服务   独立后台进程，0.0.0.0:6008，每3秒读取真实训练状态
本机地址   http://127.0.0.1:6008
公网映射   https://uu753393-afb3-4b7a916d.westd.seetacloud.com:8443
进程日志   training_runs/10-5_sft/services/dashboard.log
验证报告   training/10-5_sft/reports/monitor_verification.md
启动入口   training/10-5_sft/launch.py dashboard
训练入口   launch.py train --confirm-full-training（已执行，独立后台运行）
训练日志   training_runs/10-5_sft/services/train.log
启动记录   training/10-5_sft/reports/training_start.json及同名md
```

页面已运行并验证公网访问，现在展示正式训练进度。训练与页面有不同独立会话和日志，不依赖对话或SSH；实例关机仍会停止进程。
