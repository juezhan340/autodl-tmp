# ≤4B 小模型 RL 后训练 / GRPO 及变体调研笔记

检索日：2026-10-05（Asia/Shanghai）。口径约定：引用数=Semantic Scholar 单篇端点（`/graph/v1/paper/arXiv:<id>`，实测返回）；star 数=GitHub REST API 实测（直连，非代理）；硬件/超参=官方 README、官方文档或论文页原文。查不到的标注"未查证"，不凭记忆填数。

一句话结论：

```text
GRPO 已经从"一个算法"变成"一套配方"：
  算法默认值：beta=0（不挂 KL）、G=8~16、token-level loss、clip-higher、动态采样剔零方差组
  工程路线：1.5B 级 → 单卡 LoRA 或单卡全参可跑通；3~4B → 2 卡起（verl/TinyZero）或单卡 24GB QLoRA（TRL/ms-swift/Unsloth）
  小模型的坑不在"跑不跑得动"，而在零方差组、熵坍缩、长度/难度偏置、格式奖励被刷
```

## 1. GRPO 现在一般怎么用（算法口径）

| 机制 | 主流做法（2025–2026） | 证据来源 |
| --- | --- | --- |
| 组大小 G | 原始 DeepSeekMath 用 64；显存受限的小模型常用 8~16，配合动态采样补足有效组 | DeepSeekMath 论文；DAPO verl 配方；AReaL 示例 |
| KL 系数 | 新配方普遍默认 beta=0（不挂 KL/参考模型）。TRL GRPOTrainer 默认 `beta=0.0`，并明确引用 DAPO、Dr.GRPO、Open-Reasoner-Zero 作为"KL 非必需"依据 | TRL 官方文档（grpo_trainer.md，检索日快照） |
| clip | DAPO 引入 decoupled clip + clip-higher：`clip_ratio_low/high`（0.2/0.28 风格）；GRPO 老式对称 0.2 已不是默认最优 | verl `docs/algo/dapo.md`；TRL 文档 `epsilon` / `epsilon_high` |
| loss 归一化 | sample-level（原始 GRPO）→ token-level（DAPO，长 CoT 不再少罚长回答）→ 除常数 L（Dr.GRPO，彻底消长度偏置）。TRL 可一键切：`loss_type="dapo"` / `"dr_grpo"` | TRL 文档；Dr.GRPO 论文（2503.20783） |
| 奖励缩放 | 原始 GRPO 用组内 std 归一，被 Dr.GRPO 证明带来题目难度偏置；TRL 提供 `scale_rewards=False`（Dr.GRPO 风格）与 `scale_rewards="batch"`（Lite PPO 风格） | TRL 文档明确说明 |
| 动态采样 | DAPO 用 `filter_groups`：采样到"全对/全错"的组直接丢弃；verl 配方参数 `gen_batch_size=1536 → train_batch_size=512`，`max_num_gen_batches=10` 封顶 | verl DAPO 配方原文 |
| GSPO | 序列级重要性比率 + 序列级 clip（对长 CoT 更稳）；AReaL 内置 `gsm8k_gspo.yaml`，TRL/verl 2026 版也提供对应 loss 类型 | AReaL README；GSPO 论文 2507.18071 |
| RLOO / ReMax | 无 critic 的 REINFORCE 系基线，AReaL 有 `gsm8k_rloo.yaml` 现成示例；作为 GRPO 对照实验的首选 | AReaL README |
| 新变体（2026） | TRL/AReaL 已内置 SAPO、LitePPO、IcePop、CISPO、VESPO 等；AReaL 把"GRPO 家族"当算法菜单，同一份数据可切不同 loss | TRL 文档；AReaL README 表格 |

论文引用数（Semantic Scholar 单篇端点，检索日 2026-10-05；`429` 表示当日限流未取到）：

| 论文 | arXiv | 年份 | 引用数 | 关键做法（对我们的可借鉴点） |
| --- | --- | --- | --- | --- |
| DeepSeekMath（GRPO 原始） | 2402.03300 | 2024 | 9472 | G=64、KL β=0.04、sample-level loss；GRPO 去掉 value model |
| DAPO | 2503.14476 | 2025 | 2787 | clip-higher、token-level loss、动态采样；Qwen2.5-32B AIME24 52%（16×8×H800），去动态采样 50%、去 token-level 44% |
| DeepSeek-R1 | 2501.12948 | 2025 | 未查证（S2 429） | R1-Zero 纯 RL 无 SFT；规则奖励+格式奖励范式 |
| InstructGPT（奠基） | 2203.02155 | 2022 | 未查证（S2 429） | PPO-RLHF 奠基，小模型 RL 的历史起点 |
| Dr.GRPO（Understanding R1-Zero-Like Training） | 2503.20783 | 2025 | 未查证（S2 429） | 去 std 归一 + 除常数 L；指出难度偏置与长度偏置来源 |
| RLOO（Back to Basics） | 2402.14740 | 2024 | 未查证（S2 429） | 多样本 REINFORCE 基线（k=2..8），免 critic |
| ReMax | 2310.10505 | 2023 | 未查证（S2 429） | 免 critic 的方差缩减方法 |
| GSPO | 2507.18071 | 2025 | 未查证（S2 429） | 序列级 ratio/clip（Qwen 系长 CoT 稳定训练） |
| SimpleRL-Zoo | 2504.09566 | 2025 | 未查证（S2 429） | 0.5B~32B 基座零 RL 系统研究（含失败模式梳理） |
| RL for reasoning in small LLMs | 2503.16219 | 2025 | 未查证（S2 429） | 1.5B 级 RL 配方与超参对照 |
| Tulu 3 | 2411.15124 | 2024 | 未查证（S2 429） | 多任务 RLVR + LLM-judge 奖励混合配方 |
| ProRL | 2505.24864 | 2025 | 未查证（S2 429） | 长程 RL 扩展推理边界（1.5B 也有实验） |
| Spurious Rewards | 2506.10947 | 2025 | 未查证（S2 429） | RLVR 收益可能来自格式/已有能力而非新能力 |
| Does RL Really Incentivize… | 2504.13837 | 2025 | 未查证（S2 429） | RL 后 pass@k 覆盖分析（能力边界争论） |
| VAPO | 2504.05118 | 2025 | 未查证（S2 429） | value-based PPO 变体，Qwen-32B AIME 60.4（verl README 引用） |
| The Art of Scaling RL Compute | 2510.13786 | 2025 | 未查证（S2 429） | RL 计算扩展律（小模型算力预算参考） |
| Open-Reasoner-Zero | 2503.24290 | 2025 | 未查证（S2 429） | 极简 KL-free 配方；0.5B/1.5B 脚本与权重全开源 |
| The Entropy Mechanism of RL | 2505.22617 | 2025 | 未查证（S2 429） | 熵坍缩机制（小模型 RL 头号风险的理论依据） |

## 2. 开源框架/项目（高 star 线，star 数=GitHub API 实测 2026-10-05）

| 项目 | stars | 定位 | 1.5B~4B 可跑性证据 | 复现性判断 |
| --- | --- | --- | --- | --- |
| unslothai/unsloth | 77198 | 单卡省显存微调/RL | 官方文档：1.5B 及以下最低 5GB VRAM；≤17B 模型 15GB VRAM 可 GRPO；notebook 含 Qwen3(4B)-GRPO、Llama3.2(3B)-GRPO-LoRA、Gemma3(4B) GSPO | 极高：Colab 可直接跑，LoRA 为主 |
| hiyouga/LlamaFactory | 75306 | 全家桶微调（SFT/DPO/GRPO…） | 支持 GRPO 训练与多数据集 interleave 配比；社区复现量大 | 高：配置化，适合快速对照实验 |
| huggingface/open-r1 | 26477 | R1 全流程复现 | 官方 recipe：Qwen2.5-1.5B-Instruct GRPO 用 `--num_processes=7`（8×H100 节点）；demo 配置 1+1 节点；已停止维护，训练代码迁至 TRL | 高（代码冻结），但 1.5B 仍是多卡配置 |
| verl-project/verl | 23747 | 工业级 RL 训练后端 | DAPO 32B 配方 16×8×H800；README 提供 LoRA RL（含多卡 LoRA 省内存）与 Qwen3 系支持 | 高：生产级，但小模型也建议 ≥1 卡 80G 舒适 |
| huggingface/trl | 19450 | 训练库（GRPOTrainer 事实标准） | vLLM colocate/单卡连续批处理；loss_type 全家桶；小显存可关 vLLM 走连续批处理 | 极高：小模型最省心的入口 |
| modelscope/ms-swift | 15781 | 国产全家桶（含 GRPO） | 文档：vLLM 共卡/分离两种模式；`vllm_enable_lora` 只同步 LoRA 权重省显存 | 高：中文文档+LoRA 路线清晰 |
| Jiayi-Pan/TinyZero | 13250 | R1-Zero 最小复现 | README：单卡可跑 ≤1.5B；3B 用 2 卡；0.5B 明确"学不会推理"；成本 <$30 说法 | 高（已停止维护，建议迁 verl） |
| OpenPipe/ART | 10784 | Agent 场景 GRPO（LoRA） | 默认 LoRA+vLLM；支持本地 GPU 起 server；notebook 覆盖 Qwen2.5 3B/7B/14B | 高：agent/工具任务首选 |
| OpenRLHF/OpenRLHF | 10067 | PPO/GRPO/vLLM 训练框架 | simpleRL-reason 基于它；7B 配方要求 6×A100-80G（官方注明未实测） | 中高：偏大卡 |
| areal-project/AReaL | 5810 | GRPO 家族算法菜单 | 官方 1.5B（Qwen2-1.5B-Instruct）可复现结果；单节点 `scheduler.type=local`；LoRA 示例 | 高：1.5B 单节点有现成脚本 |
| hkust-nlp/simpleRL-reason | 3874 | 极简规则奖励 RL | 7B：8K MATH、8 samples、120 步收敛；4 节点×8×A100-80G≈1.5 天；官方说 6×A100-80G 可训（未测） | 中：7B 起步的硬件门槛 |
| NovaSky-AI/SkyRL | 2376 | 长程/多轮 agent RL | skyrl-gym（math/coding/search/SQL 环境）+ Tinker API；支持 Multi-LoRA | 中高：环境生态好 |
| Open-Reasoner-Zero | 2098 | 极简 KL-free RLVR | 0.5B/1.5B/7B/32B 全谱系；0.5B 脚本可单张 A800/H800 跑；1.5B 有独立脚本与权重 | 高：0.5B~1.5B 单卡证据最硬 |

## 3. 1.5B~4B 的复现项目清单（数据/奖励/超参/硬件）

| 项目 | 模型 | 数据 | 奖励设计 | 关键超参 | 效果 | 硬件 | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TinyZero | Qwen2.5-0.5B/3B (base) | Countdown、乘法任务 | 规则奖励（答案对错） | 直接套 verl GRPO 脚本；单卡 ≤1.5B、3B 双卡 `ROLLOUT_TP_SIZE=2` | 3B 出现 self-verification/"aha"；0.5B 学不出推理 | 1~2 卡（官方建议起点） | TinyZero README |
| SimpleRL-reason | Qwen2.5-Math-7B | 8K MATH（query, answer） | 规则奖励，无 RM 无 SFT | 8 samples/query，120 步；PPO+Ray+vLLM | AIME 33.3 / AMC 62.5 / MATH 77.2（pass@1）＞同基座 50× 数据基线 | 4 节点×8×A100-80G≈1.5 天；6×A100 可能够（未测） | 官方 README |
| Open-R1 | Qwen2.5-1.5B-Instruct | 自建 code/math 验证集（IOI/CodeForces/Mixture-of-Thoughts） | 规则验证（代码执行/答案比对） | GRPO 配置 `--num_processes=7`、zero2、vLLM 占 1 节点；`dataset_mixture` 支持按 weight 混数据 | 1.5B 配方可复现；正式模型训练按 8×H100 节点写死 | 1+1 节点（vLLM+训练） | open-r1 README |
| Unsloth GRPO | Qwen3(4B)、Llama3.2(3B)、Gemma3(4B) 等 | 自备任务数据 | 规则/裁判混合（教程强调 rubric 拆分） | LoRA 为主；1.5B ≤5GB VRAM、≤17B 15GB VRAM 的说法 | 教程级可跑，Colab 免费档可玩 1.5B~4B QLoRA | 单卡 16GB 起 | Unsloth 官方文档 |
| ART | Qwen2.5-3B/7B/14B | agent 任务（工具调用/游戏） | 任务级规则奖励 + RULER 自动 rubric | LoRA + vLLM server；GRPO | 邮件检索 agent 14B 超 o3（官方博客口径） | 本地单卡 GPU 可起 server | ART README |
| AReaL 1.5B | Qwen2-1.5B-Instruct | GSM8K | 规则奖励 | `scheduler.type=local` 单节点；GRPO/PPO/DAPO/RLOO/GSPO/Dr.GRPO 一键切 | 官方称 1.5B 可复现 | 单节点（8 卡档；LoRA 示例另给） | AReaL README |
| ORZ | Qwen2.5-0.5B/1.5B/7B/32B | 自建 math（KL-free 配方） | 规则奖励（答案验证） | 极简 GRPO，无 KL；32B 仅需 R1-Zero 1/10 步数 | 奖励与长度随规模可扩展；0.5B 单卡可跑 | 0.5B=1×A800/H800；1.5B 多卡脚本 | ORZ README |
| ms-swift GRPO | Qwen 系小模型（含 LoRA） | 自备 | 插件式奖励函数 | vLLM 共卡 + `vllm_enable_lora true` 只同步 LoRA | 工程可用，社区量大 | 单卡 24GB 级可 LoRA | ms-swift 官方文档 |
| DAPO（对照规模） | Qwen2.5-32B | DAPO-Math-17k | 规则奖励 | G=16、clip 0.2/0.28、token-level、动态采样 | AIME24 52% | 16×8×H800 | verl DAPO 配方 |

## 4. 小模型 RL 特有坑与处置（按风险排序）

```text
零方差组（全对/全错）
  表现：G 个回答奖励全同 → 优势全 0 → 那一步白跑
  处置：DAPO 动态采样（filter_groups / max_num_gen_batches）、G 提到 8~16、
        任务难度筛选（选中等难度题，别一上来全是难题）

熵坍缩 / 重复退化
  表现：输出越来越短、越来越模板化，entropy 掉到接近 0
  处置：clip-higher（0.2/0.28）、监控 entropy、降 lr、混入略难任务
  依据：DAPO、Entropy Mechanism（2505.22617）

长度偏置 / 难度偏置
  表现：样本级 loss 少罚长回答；std 归一让简单题优势被放大
  处置：token-level loss（DAPO）或除常数 L（Dr.GRPO）；scale_rewards=False

格式奖励被刷 / reward hacking
  表现：只学会输出 `\boxed{}` 格式，答案正确率不涨
  处置：格式奖励权重压低、终态答案权重拉高、verifier 要防作弊
  依据：SpuriousRewards 警示 RLVR 收益可能只是激活已有能力（2506.10947）

too-hard 任务 / 泛化
  表现：难题组全错、简单题组全对，梯度都浪费
  处置：SimpleRL 的经验是用中等难度 MATH 训练、AIME 泛化 +20 分；难度分层采样

train-inference mismatch（vLLM 生成 ≠ 训练重算 logp）
  表现：ratio 漂移、训练后期不稳
  处置：TRL 的 TIS/MIS 重要性采样修正（默认开启 TIS）；或换连续批处理生成
```

## 5. 三套可复现方案（超参起点 + 硬件估计）

方案 A：单卡 24GB 保守起步（LoRA，先跑通再谈效果）

```text
模型：Qwen3-1.7B / Qwen3.5-2B（4bit QLoRA 或 bf16 LoRA）
框架：TRL GRPOTrainer（或 Unsloth/ms-swift，同思路）
关键参数起点：
  num_generations(G) = 8
  max_completion_length = 2048（先短跑通，再 4096）
  beta = 0.0（不挂 KL）
  loss_type = "dapo"（长链）或 "dr_grpo"（防长度偏置）
  scale_rewards = False
  lr = 1e-6~2e-6（LoRA；全参取 5e-7~1e-6）
  per_device_train_batch_size = 4~8 prompts（grad accum 8~16）
  use_vllm = True（colocate + sleep mode 省显存；显存不够就关掉走连续批处理）
数据：先单任务（数学/工具调用）2k~8k 条，中等难度为主
硬件：1×24GB（4090/L40S/A5000）；1.5B LoRA 24GB 有余量，4B 建议 QLoRA
证据：Unsloth 文档（1.5B≤5GB、≤17B 15GB，LoRA）、TRL 文档（loss_type/scale_rewards/vLLM 模式）、ART 默认 LoRA
```

方案 B：1.5B 全参 / 3B LoRA，双卡 4090 或单卡 80G（追求真实效果）

```text
模型：Qwen3-1.7B 全参（单卡 80G 或 2×40G）；Qwen3.5-3B/4B 用 LoRA（2×24G）
框架：verl（TinyZero 配方思路）或 AReaL（算法可切换）
关键参数起点：
  G = 8（显存换质量再上 16）
  train_batch_size = 64~128 prompts
  mini_batch_size = 16~32
  lr = 1e-6（全参）
  clip_ratio_low/high = 0.2 / 0.28（动态采样开 filter_groups）
  KL = 0（beta=0）
  rollout temperature = 1.0（探索期），评测 0.6
数据：8k~20k 条 verifiable 任务（答案可程序验证）；难度分层
硬件：2×24GB（LoRA）~2×A100-40G（全参 1.5B）；TinyZero 单卡≤1.5B 已验证可行
证据：TinyZero README（单卡≤1.5B、3B 2 卡）、AReaL 1.5B 单节点、ORZ 单卡 0.5B/1.5B 脚本
```

方案 C：4B + 多任务混合 RL（对着我们 5~7 类家居任务）

```text
模型：Qwen3.5-4B（LoRA）
框架：ms-swift 或 AReaL（vLLM 共卡 + LoRA 权重同步）
混合方式（推荐两层混合，先分后总）：
  阶段1：每个任务类型单独跑通（各自 reward，确认无全对/全错退化）
  阶段2：按权重混合数据流：math/code : 工具调用 : 家居任务 : 格式约束 = 3 : 3 : 3 : 1
  奖励 = 每任务独立 verifier + 全局格式奖励 + 终态奖励（格式权重压到 0.1 以下）
关键参数起点：
  G = 8；lr = 5e-7（LoRA 1e-6）
  动态采样开；loss_type = dapo；beta = 0
硬件：2×A100-80G（4B LoRA + vLLM 共卡）或 4×3090-24G（LoRA，慢但可行）
证据：Open-R1 `dataset_mixture.weight`、Tulu3 多任务 RLVR+judge 混合、AReaL 多任务示例、ms-swift vllm_enable_lora
```

## 6. 来源与口径

```text
引用数：api.semanticscholar.org/graph/v1/paper/arXiv:<id>（2026-10-05 实测；429 即标"未查证"）
star 数：api.github.com/repos/<owner>/<repo>（2026-10-05 00:49~01:10 实测，直连配额口径）
框架能力：各仓库 README / 官方文档 原文（检索日快照），不是二手转述
硬件数字：官方 README/文档/论文页原文；"估计"字样处为按参数量的推算，非实测
```
