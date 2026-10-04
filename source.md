# 仓库边界与外部来源

> 本文件登记**本地（Windows）侧**的仓库外文件（`D:\homeflow\autodl-tmp`、`D:\D_program\` 等）。
> 服务器侧（`/root/autodl-tmp/`）的仓库外文件登记在 `source_server.md`。
> 主仓库在 GitHub，两个工作端各自维护自己那侧的仓库外文件，两份登记文件都随仓库同步。

## 1. 管理原则

本仓库保存能够体现研究设计和实现增量的内容。可重新下载的第三方源码、论文原件、模型权重、私密配置和运行产物继续放在当前工作区，但不进入 Git 历史。

```text
/root/autodl-tmp
├── Git 核心
│   ├── new_demo/                 新代码根（17/18 的 D0–D6，尚未写完）
│   ├── homeflow_demo/            旧 V1.2/V2 只读参考，不再打补丁
│   ├── tests/                    自动测试
│   ├── doc/                      设计与实施文档
│   ├── UbiComp三支柱讨论/         自主研究讨论
│   ├── simuprocject/analysis_docs/ SimuHome 自主分析
│   ├── simuprocject/structure/   自主结构记录
│   └── benchmarks/               本机基准脚本与小型结果
├── 仓库外来源
│   ├── llama.cpp/、minimind/     第三方训练或推理框架
│   ├── simuprocject/Simuhome_experiment/  第三方模拟器源码
│   │                              （connectedhomeip / Matter 副本已于 2026-10-03 删除）
│   ├── 论文/                     论文 PDF 与提取文本
│   └── models/                   模型权重
└── 本地状态
    ├── .autodl/                  平台状态
    ├── new_demo/.env.deepseek    新包私密 API 配置（当前填写处）
    ├── homeflow_demo/.env.deepseek 旧 demo 私密 API 配置，不再作为主入口
    ├── **/data_raw/              API 原始响应
    └── **/checkpoints/、**/out/  训练产物
```

同一套仓库另有一份本机（Windows）部署，外部程序与权重同样放在仓库外：

```text
D:\homeflow\autodl-tmp            仓库根（与服务器 /root/autodl-tmp 同一套内容）
D:\D_program\                     仓库外程序与权重
├── llama.cpp\vulkan-b10991\      Windows 构建 10991（Vulkan 后端），提供 llama-server.exe
├── models\                       本机评测与训练用 GGUF 权重
└── venvs\minimind\               LoRA 可行性验证用的 Python 环境
```

## 2. 第三方源码

| 本地路径 | 用途 | 来源与版本状态 | 恢复方式 |
|---|---|---|---|
| `llama.cpp/` | Qwen GGUF 本机推理与吞吐测试 | 上游为 `https://github.com/ggml-org/llama.cpp.git`。本地目录没有 `.git`，二进制报告 `0.4.1-dev, commit unknown`；现存压缩包 SHA-256 为 `36ac6eef0bba8c3cfa37fe3006dfbcd58a44020ec4e09813fcfe4124c092c6d4`；本机另有 Windows 构建 `D:\D_program\llama.cpp\vulkan-b10991`（`0.4.1-dev`，build 10991，commit `930e2fa59`，Vulkan 后端） | 优先用现存 `llama.cpp-master.tar.gz` 解压；需要升级时重新克隆并单独记录 commit；Windows 构建按同一 commit 重新编译 |
| `minimind/` | 早期 SFT/GRPO 学习实验 | `https://github.com/jingyaogong/minimind.git`。本地快照没有 `.git`，无法证明精确 commit；2026-09-23 查询到上游 HEAD 为 `f659b55761b754d306bd140573493a6543cafd7f`；本机验证环境为 `D:\D_program\venvs\minimind`（Python 3.12.13、torch 2.9.1+cu128） | 按下面命令恢复一个干净、固定版本；数据集和权重另行下载 |
| `simuprocject/Simuhome_experiment/` | SimuHome 对照实验 | 本地 remote 为 `https://github.com/Mr-luo-q/Simuhome_experiment.git`，本地 HEAD 为 `f8a813f237fca394edd36260dccef78aa3214335`；远端当前 `main` 为 `b828846f6a1b28e15460808026d1abb51e28641f` | 当前工作树含大量修改/删除且 packfile 已损坏，不把它视为干净基线；重建时克隆远端当前固定版本 |
| `simuprocject/external_repos/connectedhomeip/` | Matter 数据模型对照 | `https://github.com/project-chip/connectedhomeip.git`，本地 HEAD 为 `ace3cccec2cd7580eaa77f8fc8ce2a38e55e45ca`。本地副本已于 2026-10-03 按作者要求删除（10,027 个文件、约 70 MB；运行时代码零引用） | 需要时重新克隆后检出该 commit；删除前已把目录里的自主分析《SimuHome对照_Matter官方仓库实现梳理.md》移到 `simuprocject/analysis_docs/` |

推荐恢复到独立的外部目录，再建立软链接或按本表路径放置：

```bash
git clone https://github.com/jingyaogong/minimind.git minimind
git -C minimind checkout f659b55761b754d306bd140573493a6543cafd7f

git clone https://github.com/Mr-luo-q/Simuhome_experiment.git simuprocject/Simuhome_experiment
git -C simuprocject/Simuhome_experiment checkout b828846f6a1b28e15460808026d1abb51e28641f

git clone https://github.com/project-chip/connectedhomeip.git simuprocject/external_repos/connectedhomeip
git -C simuprocject/external_repos/connectedhomeip checkout ace3cccec2cd7580eaa77f8fc8ce2a38e55e45ca
```

这里固定的是可重新获取的基线。`Simuhome_experiment` 当前本地 HEAD 和未提交改动不能仅凭远端恢复，删除该目录前应先单独归档确有价值的改动。

## 3. 模型权重

服务器侧推理模型来自 ModelScope 的 `Qwen/Qwen2.5-7B-Instruct-GGUF`，本地放在 `models/qwen2.5-7b-instruct-gguf/`（相对 `/root/autodl-tmp`）。

```text
qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf
SHA-256  42f6693004793ee6cf1b2b723f0273b10f86a3bb2a949bd9128d4cda5fb866cd

qwen2.5-7b-instruct-q5_k_m-00002-of-00002.gguf
SHA-256  beba9d4f2f5a1fe7d144dcae332e68b52c26705c5310dece2e5d1997e091e134
```

下载地址：

```text
https://modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/master/qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf
https://modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/master/qwen2.5-7b-instruct-q5_k_m-00002-of-00002.gguf
```

### 本机（Windows）评测与训练权重

```text
Qwen2.5-1.5B-Instruct-GGUF\qwen2.5-1.5b-instruct-q8_0.gguf       1.76 GB
SHA-256  d7efb072e7724d25048a4fda0a3e10b04bdef5d06b1403a1c93bd9f1240a63c8
用途     new_demo 250 条评测与 few-shot 对照（newdoc/01、04、05、07）
来源     ModelScope Qwen/Qwen2.5-1.5B-Instruct-GGUF（Q8_0 量化）
路径     D:\D_program\models\Qwen2.5-1.5B-Instruct-GGUF\

Qwen3-0.6B-GGUF\Qwen3-0.6B-Q8_0.gguf                             0.60 GB
SHA-256  9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031
用途     早期 SFT/GRPO 实验基座
路径     D:\D_program\models\Qwen3-0.6B-GGUF\

Qwen3-1.7B-GGUF\Qwen3-1.7B-Q8_0.gguf                            2.02 GB
SHA-256  9860780f3a1fab1f8f909a1b549ea3e62c22d19ab1a492b3a1026b38c5bd3ec3
用途     200 条评测对照（newdoc/12），llama-server 用 -rea off 关思考
来源     hf-mirror ggml-org/Qwen3-1.7B-GGUF（Q8_0）
路径     D:\D_program\models\Qwen3-1.7B-GGUF\

Qwen3.5-2B-GGUF\Qwen3.5-2B-Q8_0.gguf                            1.87 GB
SHA-256  1b04acba824817554f4ce23639bc8495ff70453b8fcb047900c731521021f2c1
用途     200 条评测对照（newdoc/12，112/200，目前最好）；多模态仓库，只跑文本 + --no-mmproj
来源     hf-mirror unsloth/Qwen3.5-2B-GGUF（Q8_0）
路径     D:\D_program\models\Qwen3.5-2B-GGUF\
```

评测服务由本机 `llama-server.exe`（build 10991，Vulkan）提供：端口 18080、上下文 32768、2 slot；评测侧入口为 `new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py`，默认 `--server http://127.0.0.1:18080`，2 路并发、12 轮上限。

本机训练产物没有外部来源，只登记路径，不登记校验值（重新生成方式见 git 历史中的 LoRA 可行性评估：`git show 347e2c3:newdoc/08_LoRA可行性评估.md`）：

```text
D:\D_program\models\Qwen3-0.6B-sft-off-gguf\
D:\D_program\models\Qwen3-0.6B-grpo-r0-gguf\、grpo-T1/、grpo-T2/、grpo-T3/
D:\D_program\models\batch_checkpoints\batch_r1_b*_gguf\ … batch_r3_b*_gguf\
D:\D_program\models\Qwen3-4B-GGUF\Qwen3-4B-Q4_K_M.gguf（2.33 GB，未用于当前评测）
```

`minimind/checkpoints/`、`minimind/out/` 和 `minimind/minimind-3/` 中的训练权重也属于仓库外文件。它们是早期学习实验产物，不是 HomeFlow Demo V1/V1.1 的运行依赖。

## 4. 论文与参考材料

完整论文库保留在本机 `论文/`，Git 只保存基于论文形成的分析。当前 HomeFlow Demo 的两份直接依据为：

| 论文 | 官方入口 | 本地原件校验 |
|---|---|---|
| SMH-Bench | `https://arxiv.org/abs/2606.01912` | PDF SHA-256：`592299d1bd0e5123ded13b7beaf558c2d1563bfc5a84717518166b405c8aa93b` |
| HomeFlow | `https://arxiv.org/abs/2606.01230` | PDF SHA-256：`51ae28dd74b13623955971ae4e626f5e0a013be718192ed22f2ff45c336aba91` |
| SimuHome | `https://arxiv.org/abs/2509.24282` | PDF SHA-256：`7d5a54015475a1c896c21cbc3f8e807660e1461934742cf6cf38401c86ced595` |

PDF 的中文翻译版和提取文本可能来自本地阅读工具，不能由 arXiv 原件逐字恢复。它们继续留在仓库外；设计结论以 `doc/` 和 `simuprocject/analysis_docs/` 内的自主文档为准。

## 5. 私密配置与生成数据

新包 DeepSeek 配置固定放在 `new_demo/.env.deepseek`，该文件不会被 Git 跟踪。字段、默认值和安全约束见 `new_demo/.env.deepseek.md`。真实密钥只在本机填写，不写入本文件、日志、JSONL 或提交记录。旧 demo 的 `homeflow_demo/.env.deepseek` 只服务历史 V2 smoke，不再作为新管线入口。

```text
输入配置：new_demo/.env.deepseek
    ↓
原始响应：new_demo/data_raw/api/             Git 忽略
    ↓ 解析与 HomeEnv 重放验证
交付数据：new_demo/data_processed/           小型、可审计版本可进入 Git
    ↓
评测结果：new_demo/runs/qwen15b_eval_*/       Git 忽略（轨迹与标签）
    ↓
训练产物：checkpoints/、out/、runs/、wandb/   Git 忽略
```

## 6. 纳入新内容的判断

```text
自主源码、测试、设计文档、小型确定性数据
    └── 纳入 Git，并补齐同名中文说明文档

可下载第三方源码、论文、模型、数据集
    └── 留在仓库外，在 source.md 记录 URL、版本和校验值

密钥、原始 API 响应、缓存、checkpoint、运行日志
    └── 留在仓库外，只记录生成方法，不记录内容
```

当外部依赖升级时，应先更新本文件中的 commit 或 SHA-256，再运行相关测试。不要只覆盖本地目录而不记录版本。
