# OPD 小模型任务适配调研（2026-10）

> 检索日期：2026-10-06，arXiv API。
> 检索口径：`abs:"on-policy distillation"` 全量倒序 + 相关性排序 + 领域定向检索（medical / translation / SQL / tool-use / domain-specific 等）。
> OPD = On-Policy Distillation：学生在自己生成的轨迹上接受教师的逐 token 分布监督。与 SFT 的区别是训练状态由学生自己产生，与 GRPO 的区别是监督信号是稠密的教师分布，而不是稀疏的结果奖励。

## 0 一屏

```text
① 有，而且 2026 年是爆发年。
   仅摘要含 "on-policy distillation" 的论文，按提交时间拉 60 条，全部落在 2025-12 之后。
   概念本身不新（GKD, 2306.13649, 2023），但作为"后训练主菜"进入小模型任务适配是 2026 年的事。

② 直接命中"SFT + OPD 做小模型任务适配"的最强例子：
   HY-MT1.5（翻译，1.8B，SFT→OPD→RL，超 72B 开源模型）
   SSTD（金融/医疗/法律领域适配，Qwen3 多尺寸，OPD 解决通用能力遗忘）
   Med-OPD（医疗 VQA，比 SFT 高 5.24 个点）
   RWOPD（硬件验证 NL→SVA，7B 学生，验证器加权的 OPD）

③ 主流管线收敛成四种：SFT→OPD、SFT→OPD→RL、OPD+RL 退火、无 SFT 的 OPD+RL。

④ OPD 和 GRPO 是互补关系：OPD 给稠密 token 级监督解决冷启动，
   RL 用稀疏结果奖励突破教师天花板。混合方案普遍比单用任何一种高。

⑤ 反例也要知道：多语翻译那篇发现 OPD 能追平但没超过 RL+检查点插值；
   小规模机理研究发现 OPD 只迁移"会解题"，不迁移"知道何时停"。
```

## 1 直接命中表

```text
论文          领域任务              学生模型         管线                          关键数字
2512.24092 HY-MT1.5   翻译(中英外)      1.8B / 7B      预训练→SFT→OPD→RL             1.8B 超 Tower-Plus-72B、Qwen3-32B；达 Gemini-3.0-Pro 约90%
2608.28647 SSTD       金融/医疗/法律     Qwen3多尺寸+Gemma 领域教师训练→OPD          通用均分 +4.8~5.0，领域增益大部分保留
2607.16303 Med-OPD    医疗VQA           医疗VLM        OPD+证据感知重加权            比SFT +5.24pp，比标准OPD +2.83pp
2605.13501 RWOPD      硬件验证NL→SVA    Qwen2.5-Coder-7B 验证器加权OPD(14B教师)      NL2SVA 双榜SOTA，超671B通用基线
2606.27814 ATOD       长程agent          0.6B/1.7B/4B   OPD→RL退火+回合重加权          比OPD +4.16，比GRPO +23.62，超教师 +2.16
2608.24310 OPDSearch+ 搜索增强推理       3B            OPD(冻结教师)→RL              HotpotQA +13.1%，2Wiki +8.5%
2605.07725 SOD        工具集成推理       0.6B          逐步OPD(按步分歧重加权)        AIME2025 26.13%，超次优 +20.86%
2609.01947 Reranker   指令跟随重排序     1B(教师4B)    教师GRPO→学生reward-OPD        MAIR-11 nDCG@6 0.7670，超离线KD +4.6
2605.07505 LiteGUI    GUI agent          2B/3B         Guided OPD + 双层GRPO          轻量模型 SOTA（无 SFT）
2608.07068 MemOPD     长程记忆agent      3B            状态对齐OPD + PPO             F1 比 PPO 最高 +416.2%
2609.37522 GC-OPD     多轮agent          4B            图条件OPD                     ScienceWorld 24.70→48.78；ALFWorld-unseen 53.36→85.26
2609.36608 ActFirst   多轮agent          0.6B/1.7B/4B  act-first异步OPD              训练加速 2.3x/1.8x/4.9x，9设置中8个不输
2610.02781 RP-OPD     健康/科学rubric    开源模型       rubric特权OPD→RL              两阶段最优；SFT→RL 出现 reward hacking
2603.11137 REOPOLD    数学/视觉/工具     7B(教师32B)   放松约束OPD                   比RL样本效率 6.7~12x；7B追平32B
2609.36860 IronLLM    端侧通用           0.65B         多领域OPD整合领域教师          对标 Qwen3.5-0.8B / MiniCPM5-1B
2608.10812 MiLMMT     多语翻译           46语言         SFT→GRPO→插值（OPD做对照）    OPD 追平但未超过 RL 前沿（反例）
2609.37326 SmallScale 机理研究           Qwen3 0.6B~4B 从8B蒸馏                     迁移解题、不迁移"停止"（诊断）
2604.13016 OPD Recipe 机理与配方         1.5B/7B       失败修复：off-policy冷启动     教师与学生思维模式需兼容
```

只核到标题、还没深读的（备查）：2607.19850 SOPD-SocialNav（社会导航）、2607.18835 ABOPD（抗体设计）、2609.33838 ChemOPD（化学推理）、2604.24005 TCOD（多轮agent时间课程）、2609.34036 UOPD、2607.14777 SEED。

## 2 重点论文在做什么

### 2.1 HY-MT1.5：SFT→OPD→RL 的完整工业管线（2512.24092）

腾讯混元的翻译模型家族，1.8B 和 7B 两个规模。训练管线四段：翻译向预训练 → SFT → 强到弱 OPD（用训好的 7B 当教师，教 1.8B）→ RL。论文明确写了顺序："we adopt this approach after SFT"，教师是 fully trained 的 HY-MT1.5-7B，学生是 1.8B。

结果：1.8B 全面超过 Tower-Plus-72B、Qwen3-32B 和主流商业翻译 API，大约达到 Gemini-3.0-Pro 的 90%；7B 在 Flores-200 上达到 Gemini-3.0-Pro 的 95%，在 WMT25 和少数民族语言上反超。这是"小模型 + SFT + OPD 做单任务适配"目前最硬的工业证据。

### 2.2 SSTD：用 OPD 做领域适配同时防遗忘（2608.28647）

金融数值推理、医疗问答、法律 holding 识别三个领域。痛点：只在目标域上做 SFT 会把基座的通用能力打坏，而 replay 语料往往拿不到。做法两阶段：先把基座自己复制一份，用目标域监督加"基座感知的关键 token 加权"训练成领域教师；再让学生在**自己生成的 prefix** 上接受这个教师的分布监督（OPD）。

结果：领域增益保留了直接微调的大部分，同时通用评测均分提升 4.8~5.0 个点；结论在 Qwen3 多个尺寸和 Gemma 上都能复现。不需要外部教师、不需要通用 replay 数据。

### 2.3 Med-OPD：医疗 VQA 的证据感知 OPD（2607.16303）

标准 OPD 把 token 一视同仁地蒸馏，医疗场景里诊断关键证据只占少数 token，会被大量临床叙述 token 稀释。Med-OPD 用"答案感知提示"做反事实对比，测每个 token 对医学视觉证据的依赖程度（Medical Evidence Advantage），再在 token 级和轨迹级重新分配蒸馏信号。

结果：OmniMedVQA 上跨模态、跨任务平均比 SFT 高 5.24 个百分点，比标准 OPD 高 2.83 个百分点。

### 2.4 RWOPD：验证器加权的 OPD 做硬件验证（2605.13501）

任务是把自然语言规格翻成 SystemVerilog Assertion（NL→SVA）。论文先指出 SFT 的老问题：token 模仿不等于性质等价，模型会在有界延迟和 liveness 规格上塌缩到几个模板。做法：学生 rollout 用 SymbiYosys+Z3 开的性质等价检查器打分，只在通过验证的轨迹上，用验证器奖励加权的 forward-KL 从冻结的 14B 教师蒸馏到 Qwen2.5-Coder-7B。

结果：NL2SVA-Human 和 NL2SVA-Machine 双榜 pass@1/5/10 全面 SOTA，超过专用模型和 671B 通用基线。

### 2.5 ATOD：OPD 与 RL 的退火混合（2606.27814）

ALFWorld、WebShop、Search-QA 三个长程交互任务。观察：OPD 早期涨得快，学生接近教师后饱和；RL 天花板更高，但稀疏奖励冷启动慢。ATOD 让 OPD 前期主导、RL 权重逐渐加码，并加回合级 disagree-uncertainty 重加权，把蒸馏信号集中在分歧大、不确定性高的回合。

结果：三个学生尺寸上平均成功率比 OPD 高 4.16 个点、比 GRPO 高 23.62 个点，平均超过对应教师 2.16 个点。0.6B 学生一组具体数字：vanilla 6.66 → GRPO 33.17 → OPD 67.73 → ATOD 更高（教师 Qwen3-4B 是 68.93）。

### 2.6 OPDSearch+ 与 SOD：两个小模型智能体的 OPD 变体（2608.24310 / 2605.07725）

OPDSearch+ 用冻结的通用 instruct 模型当教师（不需要任务专用教师），先 OPD 把推理分解和证据整合能力灌给 3B 学生，再用 RL 精炼，HotpotQA 涨 13.1%、2WikiMultihopQA 涨 8.5%，全面超过同尺寸 RL 基线。

SOD 指出工具调用场景里 OPD 的级联失败：一步工具调错，后面分歧放大、教师监督失真。它按步级分歧自适应重加权蒸馏强度，0.6B 学生在 AIME 2025 拿到 26.13%，比次优基线高 20.86%。

### 2.7 机理与配方（2604.13016 / 2609.37326 / 2609.38666）

2604.13016 给出 OPD 成功的两个条件：学生和教师思维模式兼容；教师要有学生没见过的新能力。失败时可以用 off-policy cold start（先跑一段离线数据）和教师对齐的 prompt 选择救回来。2609.37326 把 Qwen3-8B 蒸到 0.6B/1.7B/4B，发现解题能力能迁移，但在 thinking 模式下"知道何时停"不能迁移——学生只保留原本就存在的正确停止点。2609.38666 从目标函数角度解释 forward KL 与 reverse KL 在蒸馏里各自的行为差异。

## 3 四种管线范式

```text
范式一：SFT → OPD（任务适配最直接）
   HY-MT1.5：预训练→SFT→OPD→RL
   SSTD：领域教师(监督) → OPD
   Med-OPD / RWOPD：以 OPD 为主，与 SFT 做对照

范式二：OPD → RL（先灌能力和轨迹，再冲上限）
   ATOD：OPD 退火到 RL
   OPDSearch+：OPD 一阶段 → RL 二阶段
   RP-OPD（2610.02781）：rubric 特权 OPD → rubric RL
   MemOPD：OPD 状态对齐 + PPO 保底

范式三：无 SFT，OPD + RL 混合
   LiteGUI：Guided OPD + 多解双层 GRPO

范式四：纯 OPD 压到端侧
   IronLLM-0.6B：多领域 OPD 把多个领域教师合成进一个 0.65B 学生
```

## 4 OPD 与 GRPO 的数字对照

```text
ATOD（2606.27814）：同任务同学生，GRPO 33.17 vs OPD 67.73（0.6B 学生平均SR）
                    ATOD 又比 OPD 高 4.16、比 GRPO 高 23.62
REOPOLD（2603.11137）：比 RL 方法样本效率高 6.7~12 倍；7B 学生追平 32B 教师
Reranker（2609.01947）：reward-based OPD 学生 1B 超过已发布的 7B RL 重排序模型；
                       且优于 on-policy GKD、离线 listwise KD
翻译对照（2608.10812）：OPD 追平但未超过"RL + 检查点插值"的前沿
小尺度诊断（2609.37326）：OPD 迁移解题，不迁移停止判断
```

## 5 对 HomeFlow 的直接参考

```text
1 HY-MT1.5 证明"1.8B + SFT + OPD 单任务"可以打 72B 通用模型，
  这是你们 1.5B 家居任务最有力的同类证据。

2 SSTD 的动机和你们完全一致：领域适配时别把通用行为打坏，
  而且它不需要 replay 数据，只需要学生自己的 prefix。

3 ATOD 的"OPD 冷启动 + RL 冲上限"比单用 GRPO 高 23 个点，
  对你们一期 GRPO 只涨 1.5 个点的情况，是最直接的改进路径。

4 如果二期要用 OPD，教师从哪来是主要工程问题：
   可以先用强模型（或更大的同族模型）在当前 250/500 任务上跑出成功轨迹，
   再按 RWOPD/Med-OPD 的方式做验证器加权或证据加权，避免均匀蒸馏稀释关键 token。
```

## 6 检索式（可复现）

```text
abs:"on-policy distillation"                                    （倒序 60 条 + 相关性排序）
abs:"on-policy distillation" AND abs:"small language model"
abs:"on-policy distillation" AND abs:"supervised fine-tuning"
abs:"on-policy distillation" AND (abs:"domain-specific" OR abs:"medical" OR abs:"translation"
     OR abs:"SQL" OR abs:"tool-use" OR abs:"function calling" OR abs:"smart home")
id_list 定向拉取：候选论文的完整摘要

排除：纯算法理论（如梯度估计、几何分析）、纯多教师能力合并、纯压缩/加速类。
```
