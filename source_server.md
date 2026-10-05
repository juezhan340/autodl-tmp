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
硬件        RTX 5090 32G（Blackwell，sm_120）；实例CPU配额25逻辑核、内存限额92GiB
            宿主Xeon Platinum 8470Q、208逻辑CPU、约754GiB内存，不代表实例独占
磁盘        /root/autodl-tmp 50G 数据盘（权重与缓存都放这里）；系统盘 30G 只放 conda 与系统件
网络        ModelScope 直连可用（约 17 MB/s，实测为实例出口上限）
            GitHub HTTPS 直连超时；第三方源码走 ghfast.top 代理（见 §3）
```

2026-10-05直接读取cgroup v2：`cpu.max=2500000 100000`、`memory.max=98784247808`，确认上述实例限额。5090的软件兼容组合、SFT显存峰值、已验证负载与换机检查项见`newdoc/5090算力支持能力.md`；最新项目进度见`context/context4.md`。

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
    nvidia-smi 实测该进程占 4792 MiB 显存（启动参数为总 ctx 32768、parallel 2；
    额外占用包含 KV 缓存和计算缓冲，不把该参数直接记成每 slot 32k×2）
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

## 7 2026-10-05 SFT训练与评测

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
状态       500条SFT、3epoch、189次更新已完成；四模型各200条测试及D6已完成
效果       基线0%，epoch1 72.5%，epoch2 84.5%，epoch3 88%（C+D6完整成功）
总结       newdoc/18_1.5B_SFT四模型效果_固定200条测试.md
           newdoc/19_1.5B_SFT训练复盘_数据方法日志与调整.md
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

页面已运行并验证公网访问，训练自然结束后显示completed。训练与页面有不同独立会话和日志，不依赖对话或SSH；实例关机仍会停止进程。

```text
本地评测   training_runs/10-5_sft/comparison_test_20261005/{baseline,epoch1,epoch2,epoch3}
语义补审   同目录semantic_review/：310条、930票、100并发上限，9.567秒，无系统失败
完整统计   同目录final_comparison_statistics.json及.md
API配置    10-04根目录.env.deepseek，已由Git忽略；报告与提交不含key
补审入口   training/10-5_sft/review.py（只审已有轨迹，不加载本地模型或重训）
```

## 8 2026-10-05 GRPO落地与4×4冒烟

```text
代码       10-04/training/10-5_grpo/；复用sft-venv，无新增框架下载
文档       newdoc/1004推进文档/12_GRPO落地设计_轨迹预处理奖励判定与4x4冒烟.md
当前GPU    RTX5090，32607MiB；驱动580.76.05，与旧硬件快照不同
输入模型   models/Qwen2.5-1.5B-Instruct/hf/，冻结BF16
输入SFT    training_runs/10-5_sft/sft-main/selected_adapter/，复制双adapter
CPU证据    training_runs/10-5_grpo/check-20261005T145457955818Z/
           800条旧轨迹重放，原文件指纹不变，不加载模型、不调用API
GPU证据    training_runs/10-5_grpo/smoke-20261005T145556954487Z/
           4任务组×4新轨迹，实际4路生成，micro2累计8，一次参数更新
保存       同目录smoke_adapter/policy/、optimizer.pt；不覆盖SFT模型
API评审    同目录finish_review/，16个输入、48票/48次HTTP尝试，无pending
显存       allocated峰值4780.01MiB，reserved峰值6990MiB；两者不能相加
耗时       56.035秒，最长2762token；不代表完整训练耗时与极限显存
状态       冒烟已结束，原SFT与固定参考不变，完整500任务GRPO未启动
```

运行产物均放在仓库外，JSON/JSONL配同名中文说明。冒烟完成当时，GPU入口为`smoke.py --mode smoke --confirm-smoke --confirm-api-review`，仅一次更新，尚无连续训练/监控；后续用户批准的100任务入口及页面见8.1。历史冒烟生成线程已关闭。

### 8.1 后续批准：100任务第一阶段，16×1正式训练

```text
正式配置   10-04/training/10-5_grpo/stage1_config.json及同名md
范围       原500训练池选五类各20，共100；每任务4轨迹，共400；25更新批次
Batch      micro16、累计1；rollout仍4路；未另做GPU冒烟，不自动降批
启动UTC    2026-10-05T16:02:27.907962+00:00（元数据原始时间）
训练       PID7783；独立新会话，日志不绑定SSH或对话
运行目录   training_runs/10-5_grpo/stage1-100-20261005T160227906618Z/
日志       同目录train.log、metrics.jsonl、training_status.json及说明
检查点     阶段末checkpoint-stage1；每个更新只存日志和证据
异常       已有更新时一次checkpoint-interrupted；OOM停止留档，不降micro
评测       训练成功后原固定200，greedy、现行A内嵌示例、原D6三票
对照       使用已有SFT epoch3固定200结果，起点权重SHA与本次一致
页面       PID7001，0.0.0.0:6008，独立只读进程
本机       http://127.0.0.1:6008
新公网     https://uu753393-981f-3f635753.westd.seetacloud.com:8443
启动身份   training_runs/10-5_grpo/services/{train,dashboard}.json及说明
当前运行   training_runs/10-5_grpo/active_run.json及说明
页面验证   training_runs/10-5_grpo/monitor_checks/stage1-100/
```

平台环境变量`AutoDLService6008URL`提供了新公网地址，旧`uu753393-afb3-4b7a916d`域名返回平台404，当前新域名页面及healthz均200。无需修改平台代理配置；记录URL时只读取公开域名，不输出平台token。阶段启动后的首批32.604秒，micro16分配峰值17270.72MiB、预留19124MiB；之后较长批次已到24392.45/27128MiB，不能把首批当整个阶段最终峰值，最终结果以training_report为准。

本轮完整CPU回归149项通过，页面桌面/手机/窄屏/宽屏、canvas曲线像素和轮询检查通过；检查没有发起GPU训练或收费API。正式训练由上面的显式双确认入口启动，后台继续执行。

第一阶段训练现已完成：100任务、400轨迹、25次实际optimizer更新，无OOM；25个更新批次合计803.484秒，均值32.139秒，最长完整采样序列2721 token。最终分配峰值25480.26MiB、预留27800MiB（24.88/27.15GiB），固定参考与SFT源文件保持不变。`checkpoint-stage1/policy/`及`training_report.json/md`已落盘，原固定200评测已自动开始。最终评测状态与结果看实时状态和`evaluation/comparison.json`，不要把这里的启动记录当作评测完成证明。

后续200评测已完成：C+D6完整成功179/200（89.5%），已有epoch3为176/200（88%）；6题改善、3题退步，无待审或D6系统失败。原D6审查108条、324张合法票，原始评测轨迹指纹未变。结果位于同目录`evaluation/comparison.json/md、grpo_summary.json/md、reviewed_trajectories.jsonl/md`。训练进程自然结束，6008页面仍运行并显示completed；不自动启动第二阶段。

### 8.2 用户批准直接启动：全500任务池反馈采样，16×2

```text
方案先写   第12文档第11节；随后实现并直接启动，无新增测试或冒烟
配置入口   training/10-5_grpo/{full_config.json,train_full.py,sampler.py}，均配中文md
启动UTC    2026-10-05T18:04:54.545052+00:00；北京时间2026-10-06 02:04:54
运行目录   training_runs/10-5_grpo/full500-20261005T180454543706Z/
训练进程   PID22635，独立会话；stdout/stderr写同目录train.log
页面进程   PID22658，独立6008只读；启动身份仍由services元数据核对
起点       第一阶段最终GRPO policy与AdamW状态；KL参考仍SFT epoch3
数据       全train500，剩余400先覆盖、旧100重新生成；不使用val/test训练
更新       8完整组×G4=32条；micro16累计2；四路rollout
预算       最多1500候选组、64次实际更新；全同分窗跳过，全500覆盖后才正常结束
日志       metrics.jsonl/md、training_status.json/md、sampler_state.json/md
证据       candidates/和windows/；每组真实采样/重放/复核/奖励/优势、每批loss/KL/显存
保存       checkpoint-update032、checkpoint-coverage500、checkpoint-full500均保留
异常       failure.json/md；已有更新时checkpoint-interrupted，不自动降micro
评测       训练成功后原200任务greedy、现行A内嵌few-shot、原D6三票
访问       http://127.0.0.1:6008
公网       https://uu753393-981f-3f635753.westd.seetacloud.com:8443
```

这是已启动记录，最终成功率/耗时以本次运行产物为准，不提前声称收敛或效果提升。旧第一阶段目录与固定SFT文件不覆盖。

后续实际：第二次更新在大词表softmax前向OOM，原正式目录保留首步及`checkpoint-interrupted`、`failure.json`，训练PID22635已退出。已明确修复LM head分块/重算并续跑，micro16累计2不变，不新增测试。

```text
当前配置   training/10-5_grpo/full_resume_config.json/md
当前运行   training_runs/10-5_grpo/full500-resume-20261005T181501989146Z/
当前训练   PID24357；UTC2026-10-05 18:15:01，北京时间2026-10-06 02:15:01
恢复内容   首步policy/AdamW、52项覆盖/采样反馈/累计预算；未提交旧轨迹丢弃
显存修复   完整micro16 decoder；真实生成token的LM head按128分块并checkpoint重算
当前页面   PID22658、6008地址不变；自动跟随active_run
日志位置   新目录train.log、metrics.jsonl/md、training_status.json/md和resume_manifest.json/md
```

续跑policy指纹与原中断checkpoint一致，固定参考仍SFT epoch3。首个运行的OOM如实记录，后续峰值和训练状态以新运行日志为准。

续跑首个实际更新已完成，累计step2、覆盖80/500、生成320条；采用6个有差异任务组，micro16反向两次后一次step。该续跑批峰值allocated13842.15MiB、reserved15398MiB（13.52/15.04GiB），无OOM。训练继续，200评测尚未启动；这些是首批证据而非最终峰值/效果。

### 8.3 2026-10-06：覆盖500的冻结checkpoint完整评测与复盘

500首遍全部生成评分于UTC2026-10-05 19:03:25保存checkpoint-coverage500，step21、2000候选轨迹，168唯一任务组/672轨迹实际进入梯度。后续反馈复访继续，update032也已保存，不能把任务覆盖500当成整个训练结束。

```text
独立评测入口   training/10-5_grpo/evaluate_checkpoint.py及同名md
阶段分析入口   training/10-5_grpo/analyze_run.py及同名md
阶段权重       当前续跑/checkpoint-coverage500/policy/，21更新，不是最终权重
评测目录       当前续跑/checkpoint_evaluations/checkpoint-coverage500-20261005T191100770011Z/
启动/结束      北京时间2026-10-06 03:11:00 → 03:28:21，1040.522秒
生成           原固定200，greedy，相同A内嵌few-shot，1129次generate，无生成错误
原D6           107条、321合法票/321 completion日志，无待确认，原轨迹/权重不变
完整成功       SFT epoch3 176 → 100任务GRPO179 → 覆盖500阶段182/200（91%）
严格安全成功   175 → 178 → 182；检出严重过程违规轨迹2 → 2 → 0
配对变化       相对SFT9改善/3退步；相对100阶段5改善/2退步
分析证据       当前续跑/analysis/coverage500-step21/analysis.json及同名md
综合报告       newdoc/1004推进文档/13_GRPO500任务阶段评测_训练复盘与下一步改进.md
上下文更新     context/context4.md，已在综合报告写完后更新
```

复访现场快照截至北京时间03:46:32：PID24357仍running，39/64实际更新、872候选组、1248采用轨迹；fixed_reference_unchanged=true。最终checkpoint与自动最终200评测尚未完成，未来以active_run/status为准。6008继续显示主训练，独立阶段评测进程已自然退出，其状态在自身目录，不覆写主训练状态。

第13文档补齐真实失败案例、T5 E/F停用、当前mean-only与归一化候选的边界。没有实施新奖励、新归一化或下一轮训练；原200已经用于诊断，不能称新的盲测。也纠正了AMP描述：原CUDA log_softmax亦可自动提升FP32，显存改善来自真实token位置筛选、LM head分块和重算，不归因于单纯换精度。
