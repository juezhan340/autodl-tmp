# 仓库边界与外部来源

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
│   ├── simuprocject/*源码*/      第三方模拟器与 Matter 源码
│   ├── 论文/                     论文 PDF 与提取文本
│   └── models/                   模型权重
└── 本地状态
    ├── .autodl/                  平台状态
    ├── new_demo/.env.deepseek    新包私密 API 配置（当前填写处）
    ├── homeflow_demo/.env.deepseek 旧 demo 私密 API 配置，不再作为主入口
    ├── **/data_raw/              API 原始响应
    └── **/checkpoints/、**/out/  训练产物
```

## 2. 第三方源码

| 本地路径 | 用途 | 来源与版本状态 | 恢复方式 |
|---|---|---|---|
| `llama.cpp/` | Qwen GGUF 本机推理与吞吐测试 | 上游为 `https://github.com/ggml-org/llama.cpp.git`。本地目录没有 `.git`，二进制报告 `0.4.1-dev, commit unknown`；现存压缩包 SHA-256 为 `36ac6eef0bba8c3cfa37fe3006dfbcd58a44020ec4e09813fcfe4124c092c6d4` | 优先用现存 `llama.cpp-master.tar.gz` 解压；需要升级时重新克隆并单独记录 commit |
| `minimind/` | 早期 SFT/GRPO 学习实验 | `https://github.com/jingyaogong/minimind.git`。本地快照没有 `.git`，无法证明精确 commit；2026-09-23 查询到上游 HEAD 为 `f659b55761b754d306bd140573493a6543cafd7f` | 按下面命令恢复一个干净、固定版本；数据集和权重另行下载 |
| `simuprocject/Simuhome_experiment/` | SimuHome 对照实验 | 本地 remote 为 `https://github.com/Mr-luo-q/Simuhome_experiment.git`，本地 HEAD 为 `f8a813f237fca394edd36260dccef78aa3214335`；远端当前 `main` 为 `b828846f6a1b28e15460808026d1abb51e28641f` | 当前工作树含大量修改/删除且 packfile 已损坏，不把它视为干净基线；重建时克隆远端当前固定版本 |
| `simuprocject/external_repos/connectedhomeip/` | Matter 数据模型对照 | `https://github.com/project-chip/connectedhomeip.git`，本地 HEAD 为 `ace3cccec2cd7580eaa77f8fc8ce2a38e55e45ca` | 本地 index 已损坏；重新克隆后检出该 commit |

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

当前推理模型来自 ModelScope 的 `Qwen/Qwen2.5-7B-Instruct-GGUF`，本地放在 `models/qwen2.5-7b-instruct-gguf/`。

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
