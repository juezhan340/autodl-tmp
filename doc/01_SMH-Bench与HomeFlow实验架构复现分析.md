# SMH-Bench 与 HomeFlow 实验架构复现分析

> 分析日期：2026-09-20  
> 分析对象：SMH-Bench（arXiv:2606.01912v1）与 HomeFlow（arXiv:2606.01230v1）的本地 PDF/TXT 版本。  
> 目标：判断两篇论文是否实际采用同一套实验架构，并给出可执行的复现拆解。

## 1. 结论摘要

**两篇论文并非使用完全相同的端到端实验架构。** 更准确的说法是：

> 它们高度可能共享同一个 HomeEnv 核心代码谱系、设备能力描述方式和状态条件验证思想，但在环境封装、智能体动作接口、用户交互方式、任务生成器、验证协议、训练闭环和评测数据集上使用了不同的实验栈。

可以把关系理解为五层：

| 层级 | 是否相同 | 判断 |
|---|---:|---|
| 设备、属性、服务、组件等领域模型 | 高度相似 | 很可能来自同一套 HomeEnv 核心实现或同源版本 |
| 状态转移与条件验证 | 高度相似 | 都使用确定性执行和 `device(...).attribute` 式可验证条件 |
| 智能体与环境的接口 | 明显不同 | HomeFlow 明示 `Gym + pyexec/Python`；SMH-Bench 主实验使用结构化工具和 JSON 动作 |
| 数据生成与交互循环 | 明显不同 | HomeFlow 是动态用户、MCTS、多轮在线训练；SMH-Bench 是固定评测实例和两种评测接口 |
| 最终评测器与数据集 | 不同 | SmartHome-Bench 与 SMH-Bench 不是同一个 benchmark，任务范围和评分方式都不同 |

因此，复现时不应实现一个单体程序后同时宣称复现两篇论文。应采用：

1. 一个共享的 `homeenv-core`；
2. 两套可替换的智能体接口；
3. 两套独立的数据生成与评测 harness；
4. HomeFlow 独有的 MCTS、SFT 和 RLVE 训练链路。

## 2. 分析证据与可信度

本分析主要依据两篇论文的正文、附录、提示模板和实验表格。当前工作区没有两篇论文对应的代码或数据，论文均标注“代码即将发布”，所以结论分为三档：

- **高可信事实**：论文明确给出接口、公式、数据规模或提示模板。
- **强推断**：两篇论文在字段、条件语法和任务模板上高度一致，但没有代码证明其为同一提交或同一版本。
- **未知项**：论文没有提供足够细节，不能通过文字唯一还原。

一个重要背景是：两篇论文作者团队高度重叠，arXiv v1 日期仅相差一天；HomeFlow 的五类任务模板又与 SMH-Bench 相应五类的措辞和子类结构高度一致。这强烈支持“同源工程”的判断，但不等于“同一实验架构、同一环境版本、同一数据集”。

## 3. 共享的 HomeEnv 核心谱系

### 3.1 共同的领域模型

两篇论文都把家庭表示为以下概念：

- 房间及其空间层级；
- 设备及其房间归属；
- 动态属性，如电源、温度、亮度、湿度和工作模式；
- 可执行服务及参数约束；
- 多组件设备，如风扇灯的 `light.*` 与 `fan.*` 命名空间；
- 执行动作后产生的确定性状态迁移；
- 基于最终状态谓词的任务验证。

符号虽然不同，但几乎一一对应：

| SMH-Bench | HomeFlow | 含义 |
|---|---|---|
| `R` | `L` | 房间/空间集合 |
| `D` | `D` | 设备集合 |
| `phi(d)` | `psi(d)` | 设备到房间的映射 |
| `X_t(d)` | `X_t(d)` | 动态设备状态 |
| `S(d)` | `F(d)` | 可调用服务/功能 |

条件表达式也共享相同风格，例如：

```text
device("1001").state == "on"
device("1001").brightness > 60
```

这说明两篇工作的“物理真值层”基本一致：任务成功不是匹配参考动作序列，而是判断执行后的状态是否满足谓词。

### 3.2 共同的设备规格思想

HomeFlow 附录把设备定义展示为 YAML；SMH-Bench 附录展示为结构化家庭 JSON。二者字段关系高度一致：

- `attributes`：类型、范围、枚举、当前值；
- `services`：名称、参数、状态更新代码；
- `userdata`：设备 ID、类别、房间等元数据；
- `components`：多功能设备的组件命名空间。

**这不一定表示底层实现不同。** 合理实现是：设备产品规格以 YAML 存储，运行时实例化后序列化成 JSON 家庭状态。复现时应采用这种统一设计，而不是维护两套设备 schema。

### 3.3 共同的验证器基础

两篇论文都需要以下核心能力：

1. 参数类型、范围和枚举检查；
2. 非法调用不改变环境状态；
3. 执行前后状态快照；
4. 目标谓词注册与求值；
5. 多目标部分完成度；
6. 动作审计和错误反馈。

HomeFlow 使用这些能力生成训练奖励；SMH-Bench 使用它们生成评测标签并判断通过。因此，共享一个经过严格测试的验证内核是复现的第一优先级。

## 4. 两篇论文的架构重建

### 4.1 SMH-Bench：评测架构

SMH-Bench 的核心是“固定任务实例 + 两种智能体接口 + 统一结果归一化 + 混合验证器”。

#### 4.1.1 数据构建链路

```text
家庭实例构建
    |
    v
序列化完整 HomeEnv 状态
    |
    v
GPT-5 按任务模板生成用户指令
    |
    v
GPT-5 生成参考助手 JSON
    |
    v
在 HomeEnv 中回放参考动作
    |
    v
提取状态差分、条件、查询答案或澄清目标
    |
    v
自动一致性检查
    |
    v
人工审核
    |
    v
1,100 个固定评测实例
```

这里并没有 HomeFlow 式通用 Blueprint 中间表示。SMH-Bench 附录明确说明，它采用“任务模板 + 用户指令 + 参考助手 JSON + 回放标签”的生成方式。

#### 4.1.2 两种评测接口

##### DR：Direct Reasoning

- 一次性向模型提供完整家庭状态、设备能力、参数范围、对话历史和记忆；
- 模型直接输出结构化 JSON；
- 动作不在生成过程中执行，而是在新的 HomeEnv 副本中统一回放；
- 主要测目标选择、服务定位、组件路径、参数类型和一次性全局规划。

##### EIA：Environment-Interactive Agent

- 模型初始只能看到房间列表和设备索引等部分信息；
- 通过 `query_device` 查询候选设备、规格和状态；
- 通过 `control_device` 立即执行动作；
- 通过 `create_automation` 创建定时或状态触发规则；
- 最终状态由交互前后快照差分得到，而不是从最终自然语言中解析。

这两个接口最终被归一化为同一种预测记录：

```text
predicted_labels
predicted_response
predicted_automation_conditions
trajectory
token_usage
execution_errors
```

#### 4.1.3 SMH-Bench 验证器

SMH-Bench 并不是纯规则评测：

- 设备控制：执行状态谓词验证；
- 无关状态：要求未指定设备保持不变；
- 自动化：验证 Cron、状态条件和动作结果；
- 环境查询：使用 GPT-5 判断回答是否与参考答案事实一致；
- 澄清任务：使用 GPT-5 判断澄清是否必要且合理；
- 最终通过：该任务类型要求的全部检查都成功。

因此，SMH-Bench 的评测结果同时依赖 HomeEnv 和 GPT-5 judge。论文报告在 200 个样本上的人机一致率为 98%，但复现仍需冻结 judge 模型版本、提示、温度和重试策略。

#### 4.1.4 SMH-Bench 的数据结构

- 1,100 个实例；
- 7 个主类、22 个子类；
- 每个子类 50 个实例：简单 25、中等 15、复杂 10；
- 550/330/220 个简单/中等/复杂实例；
- 复杂家庭约为 31 个嵌套房间、135 台设备；
- 复杂样本共享大型密集家庭，简单和中等样本使用更多独立家庭实例。

最后一点会影响泛化解释：复杂组的难度既来自设备数量，也可能包含对同一大型家庭结构的重复适应。

### 4.2 HomeFlow：训练与评测架构

HomeFlow 的核心是“程序化环境生成 + 可验证目标编译 + MCTS 多轮轨迹合成 + SFT + 在线 RLVE”。

#### 4.2.1 总体链路

```text
用户画像池 + 天气/布局/设备先验
                |
                v
           HomeMaker
                |
                v
    多样化初始家庭状态 s0
                |
                v
 GPT-5 生成 Blueprint 与目标条件 Phi
                |
                v
 可执行性/边界/语义一致性三重过滤
                |
                v
 MCTS-Flow：GPT-5 用户 <-> GPT-5 助手 <-> HomeEnv
                |
                v
       提取成功多轮轨迹
                |
                v
              SFT
                |
                v
 DeepSeek-V3.2 动态用户 <-> 策略模型 <-> HomeEnv
                |
                v
        逐步 RLVE 在线优化
                |
                v
       SmartHome-Bench 评测
```

#### 4.2.2 HomeMaker

HomeMaker 负责采样：

- 真实天气上下文；
- 楼层、房间和嵌套空间；
- 基于房间语义的设备组合；
- 初始设备和环境状态；
- 用户画像、健康、习惯和偏好。

这部分在 SMH-Bench 中仅以“家庭实例构建”概括，没有公开相同的生成分布。因此不能默认 SMH-Bench 的家庭采样器就是 HomeMaker 的相同配置。

#### 4.2.3 Blueprint

Blueprint 是 HomeFlow 特有的重要中间表示：

```text
B = <用户画像 U, 初始状态 s0, 生活片段 I, 目标条件 Phi_B>
```

它把开放式生活场景编译为可执行布尔条件，并经过：

1. HomeEnv 可执行性检查；
2. 设备 schema 和参数边界检查；
3. GPT-5 对条件、用户意图和画像的一致性检查。

SMH-Bench 虽然也产生状态条件，但其条件来自参考助手动作回放，不是先构建 Blueprint 再驱动对话搜索。

#### 4.2.4 MCTS-Flow

MCTS-Flow 的节点包含对话历史、环境反馈和当前角色。其关键机制是：

- 用户节点和智能体节点使用不同分支宽度；
- 通常令 `k_agent > k_user`；
- 使用 UCB 做选择；
- 环境验证奖励回传；
- 失败分支可被标记为不可通过；
- 成功和部分成功前缀可以复用，而不是整条轨迹丢弃。

数据合成阶段的用户和助手都由 GPT-5 扮演。论文示例执行 5 次 rollout，但没有说明正式生成时每个 Blueprint 的统一 rollout 数、最大深度和 UCB 系数。

#### 4.2.5 智能体执行接口

HomeFlow 附录明确展示：

```python
env.step({
    "name": "pyexec",
    "code": "device('1001').set_brightness(80)"
})
```

训练奖励又包含“代码检查”和“代码长度”项，禁止 `getattr`、`setattr`、`eval`、`exec` 和 `compile` 等关键词。这证明 HomeFlow 的主要执行层至少包含代码生成/代码执行接口，而不是只使用 SMH-Bench 的 `control_device` 结构化调用。

论文同时说动作也可以是 API 调用，智能体提示中又要求查询设备手册和状态。因此合理判断是：HomeFlow 使用了一个更通用的沙箱执行层，工具/API 可能最终转换成 `pyexec`；但论文没有给出完整工具 schema 和转换器。

#### 4.2.6 两阶段训练

##### SFT

论文构建三套各 15,000 条的对照数据：

- 纯文本角色扮演；
- Blueprint 锚定的线性生成；
- Blueprint + MCTS-Flow。

主实验要求“相同样本数”，因此完整 HomeFlow-SFT 应使用 15,000 条 MCTS-Flow 数据，而不是简单合并为 45,000 条。论文的“由三个子集构成”表述容易产生歧义，复现前需要代码确认。

##### RLVE

- 10,000 个独立基础配置；
- DeepSeek-V3.2 作为动态用户模拟器；
- 最多 3 个交互回合；
- 奖励包括目标进度、最终成功、动作审计惩罚；
- Full 版本使用相对 SFT 参考模型的 KL 约束；
- 论文给出学习率、采样温度、GPU 数量等部分参数，但没有完整给出训练算法实现细节。

逐步奖励可写为：

```text
r_t = lambda_prog * (m_t - m_{t-1})
    + lambda_succ * 1[终局完全成功]
    - c_audit * 1[动作被拦截]
```

#### 4.2.7 HomeFlow 内部存在三种奖励语义

HomeFlow 的不同阶段没有使用完全相同的成功函数：

1. 任务形式化将终端奖励写为已满足条件数量 `sum(phi_k)`，允许部分奖励；
2. MCTS-Flow 的终端回传公式要求轨迹有效且所有条件均满足，使用二值成功；
3. RLVE 使用条件完成比例的逐步增量、终局完全成功奖励和审计惩罚。

这三种定义可以服务不同阶段，但复现时必须分别实现，不能用一个统一的布尔验证器替代全部逻辑。还应明确条件是否允许在中途满足后又被后续动作破坏，以及负进度是否产生负奖励。

#### 4.2.8 SmartHome-Bench

HomeFlow 使用自己的 SmartHome-Bench：

- 1,678 个实例；
- 5 个主类、论文声称 18 个子类；
- 原子控制、组合控制、模糊意图、多轮交互和个性化记忆；
- 从少于 10 台设备到超过 100 台设备；
- 使用 HomeEnv 状态验证；
- 记录成功率、平均工具调用和输出 token。

它没有纳入 SMH-Bench 的自动化调度和环境查询两个主类，也没有描述与 SMH-Bench 相同的 GPT-5 judge 协议。

## 5. 核心架构差异

| 维度 | SMH-Bench | HomeFlow | 对结果的影响 |
|---|---|---|---|
| 主要目标 | 评测通用 LLM 智能体 | 生成训练数据并优化小模型 | 评测 harness 与训练 harness 不是一回事 |
| 环境输入 | 固定 benchmark 家庭状态 | HomeMaker 持续采样环境 | HomeFlow 更依赖环境分布设计 |
| 任务中间表示 | 模板、参考 JSON、回放标签 | 显式 Blueprint 与目标条件集合 | 数据生成逻辑不同 |
| 用户侧 | 固定请求、历史和记忆 | GPT-5/DeepSeek 动态用户模拟器 | 是否能恢复错误、澄清后继续执行不同 |
| 动作接口 | JSON 动作或结构化工具调用 | `pyexec`/Python 或 API 沙箱 | 语法错误、安全面和策略难度不同 |
| 可观测性 | DR 完全可观测；EIA 部分可观测 | POMDP 式部分观察 | 观察内容和查询成本未必一致 |
| 交互形态 | 工具循环，通常没有动态用户继续回应 | 用户与智能体轮流推进多轮轨迹 | “多轮”含义不同 |
| 目标验证 | 任务类型专用验证器 | 通用条件集合完成度 | HomeFlow 更适合奖励塑形 |
| 自然语言评分 | 查询和澄清使用 GPT-5 judge | 主实验强调客观状态验证 | 指标的主观依赖不同 |
| 无关状态约束 | 明确要求保持未指定状态不变 | 动作审计提到无关动作，但终局公式主要检查目标条件 | 过度操作是否必然判错不明确 |
| 自动化 | 专门的 Cron/状态触发类别 | 框架可涉及习惯和自动化，但主 benchmark 不测 | 两套任务覆盖不同 |
| 纯查询 | 专门类别并使用语义 judge | 主 benchmark 不单列 | HomeFlow 分数不能代表查询能力 |
| 训练 | 无 | MCTS-SFT + 在线 RLVE | HomeFlow 独有 |
| Benchmark | SMH-Bench，1,100 | SmartHome-Bench，1,678 | 分数不可直接横向比较 |

## 6. 最关键的非等价点

### 6.1 `pyexec` 与结构化工具不是等价接口

代码动作空间允许模型一次生成多个语句、变量、循环和条件判断；结构化工具则把每一步限制在固定 schema 中。二者会改变：

- 动作表达能力；
- 语法与运行时错误率；
- 工具调用次数；
- token 消耗；
- 安全审计难度；
- 强化学习的探索空间。

它还会改变“工具调用次数”的统计口径。一次 `pyexec` 可以包含多个设备查询和控制，而 SMH-Bench 的 `query_device`、`control_device` 通常把查询和单个服务执行拆成多次调用。HomeFlow 表中的平均约 2 次工具调用，不能直接与 SMH-Bench EIA 的调用步数比较，也不能单独证明其规划更高效。

如果用 SMH-Bench 的结构化工具替代 HomeFlow 的代码沙箱，RLVE 会变成另一个问题；反之，用 `pyexec` 评测 SMH-Bench 也会改变错误分布。因此复现必须保留两个 adapter，并增加接口消融实验。

### 6.2 “多轮交互”的定义不同

SMH-Bench 的多轮样本主要把既有对话历史作为输入，或判断当前是否应澄清。模型提出澄清后，评测器通常判断这句话是否合理，并不等同于真实用户随后回答、智能体继续完成任务。

HomeFlow 的 MCTS 和 RLVE 则明确让用户模拟器与智能体交替生成下一轮，并让环境状态随动作变化。这种在线轨迹更适合训练错误恢复，但也更依赖用户模拟器质量。

### 6.3 两套 benchmark 不是训练集与测试集的简单对应

SmartHome-Bench 的五类任务与 SMH-Bench 中五个类别几乎同构，但：

- 样本数不同；
- 子类总数不同；
- 难度分层说明不同；
- 人工审核流程不同；
- 自动化和查询覆盖不同；
- 评测器不同；
- 是否使用同一家庭池、设备产品池和模板实例没有说明。

一个合理但尚未证实的假设是：SmartHome-Bench 与 SMH-Bench 来自同一任务模板代码家族，SMH-Bench 是经过扩展和人工审核的独立评测产品，而不是 HomeFlow benchmark 的简单改名。

### 6.4 HomeFlow 的 headline 结果不是在 SMH-Bench 上得到的

HomeFlow-RL-8B 的 87.03% 以及超过 GPT-5.5 的结论，只能解释为在 HomeFlow 自建 SmartHome-Bench 和其统一智能体框架下成立。没有证据表明该模型：

- 在 SMH-Bench 的 DR 或 EIA 设置下也有相同优势；
- 能处理 SMH-Bench 的自动化和环境查询；
- 在 GPT-5 judge 与无关状态保持约束下仍保持同等成绩。

复现项目最有价值的新增实验，是把 HomeFlow 模型放到 SMH-Bench EIA 上做真正的跨论文验证。

## 7. 论文中影响精确复现的缺失与不一致

### 7.1 HomeEnv 与 HomeMaker

以下信息没有完整公开：

- 全部设备 YAML 规格和产品数量；
- 房间类型、楼层和嵌套结构的采样分布；
- 设备按房间语义的条件分布；
- 初始属性联合分布和设备状态依赖；
- 天气数据来源、地点、日期和采样方式；
- SMH-Bench 与 HomeFlow 是否使用同一 HomeEnv commit；
- 条件解释器和服务代码的安全执行方式；
- 状态快照、回滚和 MCTS 分支环境复制的实现。

缺少这些信息时可以复现机制，但不能保证复现论文的绝对分数。

### 7.2 SMH-Bench 评测配置

未充分说明：

- 所有模型的温度、top-p、最大输出长度和重试策略；
- EIA 最大工具步数的统一规则；
- API 失败、超时、无效 JSON 的重试和计分方式；
- 复杂家庭是否在所有任务类别间共享完全相同的状态；
- GPT-5 judge 的具体模型快照和解码参数。

特别需要注意：错误分析出现“10 次调用预算”，但附录中的成功 EIA 示例包含约 13 次查询/控制调用。因此，10 次可能是特定任务预算、不同实验配置，或论文描述不一致，不能直接设为全局常量。

### 7.3 HomeFlow 数据合成

未充分说明：

- 正式 MCTS 每个 Blueprint 的 rollout 数；
- 最大树深度、终止条件和总搜索预算；
- UCB 常数 `c_ucb`；
- 节点去重和环境状态哈希；
- 用户与助手模型的温度、采样参数和失败重试；
- Blueprint 数量与每个 Blueprint 的保留轨迹数；
- 训练、RL 和 SmartHome-Bench 在用户、家庭、模板及设备规格层面的去重规则。

论文报告纯角色扮演生成成功率 86.33%、Blueprint 线性生成 92.43%，但附录又给出 20,000 条中分别保留 16,700 和 17,500 条。若分母相同，对应比例是 83.5% 和 87.5%。这可能是“执行成功率”和“过滤后保留量”两个不同阶段的指标，但论文没有明确解释。

### 7.4 HomeFlow 训练

RLVE 只给出了部分超参数，仍缺少：

- 具体 RL 优化算法和实现框架；
- 全参数训练还是参数高效训练；
- 优化器、批量大小、梯度累积和裁剪；
- 最大上下文长度和代码/观察截断规则；
- SFT 的 epoch、学习率、batch size 和模板；
- rollout 与更新的比例；
- 优势估计、归一化和失败轨迹处理；
- 4B 模型的训练资源和独立超参数。

论文给出的 Full RLVE 资源为 96 张 H20、95 小时以上，即至少约 9,120 H20 GPU-hours；这不适合作为第一阶段复现目标。

### 7.5 数字与分类不一致

- HomeFlow 摘要和主表中 4B 成绩为 84.60%，结论写成 84.20%，应按主表和摘要采用 84.60%。
- SmartHome-Bench 声称 18 个子类，但本地文本抽取中的模板表不能完整恢复全部 18 个名称；需要原 PDF 表格或代码确认。
- HomeFlow 的任务编号在正文使用 QT1-QT5，附录表格又使用 TC1-TC5，复现数据 schema 应自行固定命名。

## 8. 推荐的复现软件架构

建议仓库结构如下：

```text
reproduction/
  homeenv_core/
    schema/                 # Home, Room, Device, Component, Attribute, Service
    specs/                  # YAML 产品规格
    engine.py               # 确定性状态转移
    validation.py           # 类型、范围、枚举、前置条件
    predicates.py           # 安全条件 AST，不直接 eval 字符串
    snapshots.py            # diff、copy、rollback、state hash
    audit.py                # 非法/危险/无关动作审计

  adapters/
    pyexec_adapter.py       # HomeFlow 代码动作接口
    structured_tools.py     # query/control/create_automation
    direct_json.py          # SMH-Bench DR 动作回放

  homemaker/
    room_sampler.py
    device_sampler.py
    state_sampler.py
    profile_sampler.py
    weather_provider.py

  smh_bench/
    generation/
    datasets/
    prompts/
    runners/dr.py
    runners/eia.py
    evaluators/

  homeflow/
    blueprint/
    mcts/
    synthesis/
    sft/
    rlve/
    user_simulator/

  smart_home_bench/
    datasets/
    runner.py
    evaluator.py

  experiments/
    configs/
    manifests/
    reports/

  tests/
    unit/
    golden/
    integration/
```

设计原则是：核心状态和服务只有一份；论文差异通过 adapter、runner 和 evaluator 表达。

## 9. 复现实施顺序

### Phase 0：规格冻结

先产出以下机器可读协议：

- `home.schema.json`；
- `device-spec.schema.json`；
- `action.schema.json`；
- `automation.schema.json`；
- `task-condition.schema.json`；
- `trajectory.schema.json`；
- `benchmark-record.schema.json`。

同时定义中英文名称与 canonical 英文字段的映射，避免直接使用翻译版 PDF 中不稳定的服务名称。

### Phase 1：最小 HomeEnv

先支持 6 类设备：灯、空调、风扇、风扇灯、窗帘、传感器。必须通过以下 golden tests：

1. 正确动作产生预期状态变化；
2. 错误参数被拒绝且状态不变；
3. 多组件定位器正确；
4. 快照差分只包含真实变化；
5. 条件验证器不依赖 Python `eval`；
6. 环境复制与回滚确定性一致；
7. 未指定设备状态保持检查可用。

### Phase 2：先复现 SMH-Bench harness

SMH-Bench 不需要训练，适合验证环境正确性：

- 手工构造每个主类 5-10 个任务；
- 实现 DR 和 EIA 两个 runner；
- 实现状态、自动化、查询和澄清评测；
- 对同一动作在 DR 回放与 EIA 在线执行后比较最终状态；
- 先用固定规则 agent 做端到端测试，再接 LLM。

阶段目标不是立刻重建 1,100 条数据，而是证明两种接口能够被同一个验证内核一致评分。

### Phase 3：复现 HomeMaker 与 Blueprint

- 固定随机种子生成可重放家庭；
- 所有采样分布写入版本化配置；
- Blueprint 条件必须解析成安全 AST；
- 明确区分物理可执行性过滤和 LLM 语义过滤；
- 记录每个过滤阶段的通过率，解决论文成功率口径不清问题。

### Phase 4：复现 MCTS-Flow

先用小规模模型和少量 Blueprint 验证机制：

- `k_user=1, k_agent=3`；
- 明确最大深度、rollout 数和 token 预算；
- 每个节点保存环境快照哈希；
- 失败节点保留原因；
- 成功路径去重；
- 报告每条成功轨迹的生成成本。

必须与两条基线比较：纯文本角色扮演、Blueprint 线性生成。

### Phase 5：SFT 机制复现

先训练 1,000-5,000 条数据的小规模版本，验证三个数据源的相对排序，而不是追求论文绝对成绩。三个训练集必须：

- 样本数相同；
- 用户/家庭池相同；
- 只改变数据生成方法；
- 测试集按家庭、画像和 Blueprint 分组隔离。

### Phase 6：RLVE 缩比复现

完整 96×H20 实验之前，先做：

- 1B-4B 模型；
- 100-1,000 个 RL 环境；
- 终局奖励、逐步奖励和审计奖励三组消融；
- 静态用户与动态用户两组消融；
- 结构化工具与 `pyexec` 两种动作接口消融。

只有在策略熵、任务成功率和非法动作率呈现与论文一致的趋势后，才扩大训练规模。

## 10. 必须增加的跨论文实验

为了验证两篇论文是否真正共享架构，以及 HomeFlow 是否泛化，建议形成如下矩阵：

| 模型 | SmartHome-Bench | SMH-EIA | SMH-DR | 自动化/查询扩展集 |
|---|---:|---:|---:|---:|
| Qwen3 Base | 必测 | 必测 | 必测 | 必测 |
| Role-play SFT | 必测 | 必测 | 可选 | 必测 |
| Blueprint Linear SFT | 必测 | 必测 | 可选 | 必测 |
| MCTS-Flow SFT | 必测 | 必测 | 必测 | 必测 |
| RLVE-ST | 必测 | 必测 | 可选 | 必测 |
| RLVE-Full | 必测 | 必测 | 必测 | 必测 |

再增加接口消融：

| 训练接口 | 测试接口 | 目的 |
|---|---|---|
| `pyexec` | `pyexec` | 论文内分布 |
| `pyexec` | 结构化工具 | 检查策略是否只学会代码模板 |
| 结构化工具 | 结构化工具 | 降低动作空间后的上限 |
| 结构化工具 | `pyexec` | 检查迁移不对称性 |

这组实验能分离三种收益：

1. HomeEnv 领域知识收益；
2. MCTS 数据多样性收益；
3. 对特定动作接口和 benchmark 模板的拟合收益。

## 11. 数据隔离方案

论文没有充分说明训练测试去重。复现时至少执行五级隔离：

1. `profile_id` 隔离；
2. `home_layout_id` 隔离；
3. `device_spec_id/spid` 组合隔离；
4. Blueprint 语义签名隔离；
5. 用户指令近重复隔离。

推荐生成如下签名：

```text
semantic_signature = hash(
  task_family,
  selected_device_types,
  normalized_predicate_graph,
  dialogue_dependency_type,
  memory_dependency_type
)
```

测试集不仅要去掉文本重复，还要去掉同一条件图的表面改写，否则会高估数据飞轮的泛化。

## 12. 指标与日志

除论文指标外，建议统一记录：

- 严格任务成功率；
- 目标条件完成率；
- 无关状态修改率；
- 非法动作率；
- 过度澄清率与欠澄清率；
- 工具/代码执行失败率；
- 平均工具调用数；
- 平均环境步数；
- 输入、输出和 judge token；
- 端到端延迟；
- 每条成功训练轨迹的生成成本；
- 按家庭规模和设备密度分层的结果；
- 按 seen/unseen device spec 的结果。

所有实验必须保存：模型快照、提示版本、数据 manifest、随机种子、环境 commit、生成模型版本和 API 返回原文。

## 13. 复现目标分级

### L1：机制复现

- 实现共享 HomeEnv；
- 实现 SMH 的 DR/EIA；
- 实现 Blueprint、MCTS 和逐步奖励；
- 证明主要消融趋势方向一致。

### L2：协议复现

- 重建相同任务类别、样本规模和模型接口；
- 严格冻结提示与解码参数；
- 结果接近论文，但允许因闭源模型版本变化产生偏差。

### L3：数值复现

- 获得原始代码、设备规格、数据和模型快照；
- 使用相同硬件与训练框架；
- 复现主要表格到预先约定的误差范围。

在代码和数据尚未公开的情况下，当前现实目标应是 L1，并为后续 L2/L3 保留兼容接口。

## 14. 最终判断

两篇论文的关系不是“两套互不相关的系统”，也不是“完全相同实验架构下的一篇评测论文和一篇训练论文”。更准确的工程判断是：

> **同一个 HomeEnv 核心家族之上，构建了两个不同的实验产品。SMH-Bench 是固定数据、双接口、混合评分的评测系统；HomeFlow 是动态环境、Blueprint/MCTS 数据生成、代码沙箱和在线 RLVE 的训练系统，并使用另一套 SmartHome-Bench 做内部评测。**

复现时最危险的做法，是把 HomeFlow 的 SmartHome-Bench 当成 SMH-Bench，或用 SMH-Bench 的结构化工具替换 HomeFlow 的 `pyexec` 后仍声称复现了原论文。正确方案是共享核心、保留接口差异，并通过跨 benchmark、跨动作接口实验检验 HomeFlow 的真实泛化能力。

## 15. 本地材料

- [SMH-Bench PDF](../论文/4个bench/03_2026_arXiv_SMH-Bench-Environment-Grounded_智能家居环境推理基准_英.no_watermark.zh-CN.mono.pdf)
- [SMH-Bench 文本](../论文/4个bench/03_2026_arXiv_SMH-Bench-Environment-Grounded_智能家居环境推理基准_英.no_watermark.zh-CN.mono.txt)
- [HomeFlow PDF](../论文/方法相关的论文/19_2026_arXiv_HomeFlow-Data-Flywheel-Smart-Home_数据飞轮智能家居训练_中.pdf)
- [HomeFlow 文本](../论文/方法相关的论文/19_2026_arXiv_HomeFlow-Data-Flywheel-Smart-Home_数据飞轮智能家居训练_中.txt)
