# HomeFlow Demo 分版本详细交付计划

> 计划日期：2026-09-21  
> 适用项目：`/root/autodl-tmp/homeflow_demo`  
> 目标：把 HomeFlow Demo 拆成可单独验收的版本，最终完成 HomeEnv、DeepSeek 数据合成、LoRA-SFT、HomeEnv 在线 rollout、LoRA-GRPO 和独立测评闭环。  
> 当前状态：`V1.1` 已完成，尚未调用 DeepSeek API，尚未下载 Qwen2.5-1.5B Transformers 权重。当前日期：2026-09-22。

## 先看版本路线

```text
V0  HomeEnv 核心骨架                         已完成
    |
V1  HomeEnv 规格固化 + 场景生成 + 程序规划器
                                          已完成
    |
V1.1  模型 turn-level 契约修订
                                          已完成
    |
V2  DeepSeek 教师数据流水线
    |
V3  SFT 数据集和训练环境
    |
V4  LoRA-SFT + Base/SFT 基线测评
    |
V5  HomeEnv 在线 rollout 接口
    |
V6  LoRA-GRPO 最小闭环
    |
V7  完整对照实验、消融和复现报告
```

每个版本必须同时交付：

```text
代码
  -> 同名中文说明文档
测试
  -> 可重复运行的命令
数据或模型产物
  -> 固定路径、格式和统计信息
验收报告
  -> 已验证事实、未完成事项、残余风险
```

项目的主要原则：

```text
先完成可验证的环境，再调用 API
先完成 SFT，再做 RL
先用原生 Transformers rollout，再考虑 vLLM
先做 group=2 的 GRPO，再增加 group=4
先跑通最小闭环，再扩大数据和任务类型
```

## 1. 当前版本状态

### V0 已完成内容

当前已经存在：

```text
homeflow_demo/env/models.py
homeflow_demo/env/tool_schema.py
homeflow_demo/env/state_engine.py
homeflow_demo/env/predicates.py
homeflow_demo/env/home_env.py
homeflow_demo/env/demo_scenario.py
tests/test_home_env.py
```

当前已经验证：

```text
合法控制动作可以改变设备状态
非法动作不会修改设备状态
目标谓词可以计算完成度
finish 可以判定成功或失败
snapshot/restore 可以恢复环境
fork 生成的 rollout 相互隔离
max_steps 可以触发 truncated
```

当前测试结果：

```text
V1 原有测试和 V1.1 新增测试共 33 个 unittest 全部通过
Python compileall 通过
未调用 DeepSeek API
```

V0 的定位是“环境内核可用”，还不能承担数据生成、SFT 或 RL。

# 2. V1：HomeEnv 规格固化与程序基线

## 2.1 版本目标

把当前能运行的 HomeEnv 变成可长期依赖的环境接口，并且加入场景生成器和规则规划器。V1 完成后，不依赖任何外部大模型，也能批量生成可行任务、成功轨迹和测评场景。

```text
V1 结束时应能回答：
  一个场景是否合法？
  一个动作是否合法？
  一个任务是否可完成？
  一条规则轨迹是否成功？
  同一个场景是否能稳定复现？
```

## 2.2 代码交付

```text
homeflow_demo/env/schema.py
  完整校验 Scenario、Device、GoalPredicate、Action 的输入结构。

homeflow_demo/env/gym_adapter.py
  提供 reset/step 的 Gymnasium 风格适配器，不让训练主链依赖它。

homeflow_demo/data/scenario_generator.py
  按设备模板、任务模板和随机 seed 生成场景。

homeflow_demo/data/planner.py
  为有限设备和有限谓词生成最短或近似最短成功动作序列。

homeflow_demo/data/trajectory_format.py
  统一保存 action、observation、state_diff、reward 和 final_result。
```

每个新增 `.py` 文件必须配套：

```text
homeflow_demo/env/schema.md
homeflow_demo/env/gym_adapter.md
homeflow_demo/data/scenario_generator.md
homeflow_demo/data/planner.md
homeflow_demo/data/trajectory_format.md
```

## 2.3 数据交付

```text
homeflow_demo/data_processed/v1/
├── scenarios_train.jsonl
├── scenarios_val.jsonl
├── scenarios_eval.jsonl
├── oracle_trajectories.jsonl
└── manifest.json
```

第一版规模：

```text
训练场景：  80
验证场景：  20
测评场景：  40
```

场景覆盖：

```text
单设备控制
双设备控制
查询后控制
条件控制
至少一种不可完成或需要澄清的任务
```

## 2.4 测试交付

```text
场景 schema 非法输入测试
重复 device_id 测试
所有设备类型控制命令测试
所有边界值测试
规则规划器成功率测试
同 seed 可复现测试
Gym adapter 返回字段测试
```

目标测试数量：至少 20 个明确断言，不以覆盖率数字替代关键行为测试。

## 2.5 V1 验收标准

```text
100% 生成场景可以通过 schema 校验
100% feasible 场景存在至少一条规则成功轨迹
规则成功轨迹经过 HomeEnv 执行后 success=True
同一场景和动作序列重复运行，结果完全一致
eval 场景不混入训练场景 ID
```

## 2.6 V1 不做的内容

```text
不调用 DeepSeek
不训练语言模型
不做复杂自然语言改写
不做 MCTS
不实现真实用户对话
```

## 2.7 进入 V2 的条件

规则场景、Oracle 轨迹和 V1.1 turn-level 契约已经稳定，可以进入 V2 的 DeepSeek 候选轨迹生成。API 生成失败时仍需通过解析错误、HomeEnv 验证结果和请求审计区分环境、轨迹格式与教师输出问题。

# 3. V1.1：模型 turn-level 契约修订

## 3.1 版本目标

V1 的 `HomeEpisodeEnv.step(Action)` 是原子工具动作级接口，已经足以验证状态转移、参数边界、规则规划器和环境裁判。它不能直接作为 LLM 在线 RL 的最终 step，因为一次模型 completion 可能包含多个工具调用，后续工具调用没有新的模型输出、token 和 logprob。

V1.1 已完成“模型输出如何进入环境”的边界修订，没有重写 V1 的状态引擎：

```text
AssistantTurn
  -> 一个模型策略决策步
  -> 内部执行一个或多个 tool_call
  -> 记录多个 ToolEvent
  -> 汇总一个 TurnResult
  -> 写入一条 RL transition
```

## 3.2 代码交付

```text
homeflow_demo/env/models.py
  新增 AssistantTurn、ToolEvent、TurnResult。

homeflow_demo/env/home_env.py
  抽取 _apply_action 原子执行原语，step 接收 assistant turn 并汇总结果。

homeflow_demo/env/gym_adapter.py
  Gym 风格 step 的 reward 和终止信号对应整个 assistant turn。

homeflow_demo/data/trajectory_format.py
  增加 turns、tool_events、assistant_output 字段；token_alignment 留给 V5 的真实模型 rollout。

tests/test_home_env.py
  覆盖一个 turn 包含多个工具调用时只产生一条 transition。
```

`Action` 保留为单个工具调用的数据结构，不能删除。它属于环境内部执行层；`AssistantTurn` 才是模型 rollout 的输入层。

## 3.3 数据契约

```text
max_turns                一个 episode 最多允许多少次 assistant 输出
max_tool_calls_per_turn  一次 assistant 输出最多包含多少个工具调用
turn_index               模型决策步编号
tool_event_index         turn 内部工具事件编号
```

过渡期间继续读取旧场景字段 `max_steps`，加载时转换为 `max_turns`。新数据统一写 `max_turns`，不再把工具调用数作为模型 episode 长度。

一个 turn 的记录至少包括：

```text
assistant_output
tool_calls
tool_events
observation_before
observation_after
reward
reward_components
terminated
truncated
```

## 3.4 V1.1 验收结果

```text
一个 assistant turn 含两个合法工具调用时，trajectory 只有一条 turn transition
tool_events 数量可以大于 turn 数量
每条 RL transition 都能找到对应的 assistant output
max_turns 按 assistant 输出次数计数
非法工具调用不会修改设备状态，但会写入对应 tool_event
V1 既有动作级状态机测试全部继续通过
旧 V1 JSONL 可以读取，新生成数据统一写 v1.1-turn 和 turns 主字段
```

实际结果：

```text
33 个 unittest 全部通过
compileall 通过
多工具 turn 产生 1 条 transition 和 2 个 tool_events
旧 max_steps 场景继续报告 MAX_STEPS，新 max_turns 场景报告 MAX_TURNS
V1 数据集重生成后可由验证器全量重放
```

## 3.5 V1.1 不做的内容

```text
不接 DeepSeek API
不训练 Qwen
不实现 GRPO optimizer
不把单个 completion 的 token 再拆成工具级策略步
不删除 V1 动作级接口
```

# 4. V2：DeepSeek 教师数据流水线

## 4.1 版本目标

让 DeepSeek 根据 V1 的结构化场景生成候选自然语言和工具轨迹，再由 HomeEnv 执行筛选。V2 的核心原则是：

```text
DeepSeek 生成候选
HomeEnv 负责裁判
程序规划器负责兜底
```

## 4.2 代码交付

```text
homeflow_demo/data/deepseek_teacher.py
  读取 .env.deepseek，调用 OpenAI 兼容接口，保存原始响应。

homeflow_demo/data/teacher_prompt.py
  生成结构化 prompt 和 JSON 输出约束。

homeflow_demo/data/trajectory_parser.py
  解析 DeepSeek 返回的 JSON，拒绝格式不合法的响应。

homeflow_demo/data/trajectory_verifier.py
  按 assistant turn 将候选轨迹送入 HomeEnv，生成验证结果。

homeflow_demo/data/deduplicator.py
  按场景、turn 序列、tool call 序列和最终状态去重。

homeflow_demo/data/build_teacher_dataset.py
  组织批量生成、重试、筛选和 manifest 写入。
```

## 4.3 配置和安全交付

继续使用：

```text
homeflow_demo/.env.deepseek
homeflow_demo/.env.deepseek.md
homeflow_demo/.gitignore
```

要求：

```text
API key 只从环境变量或 .env.deepseek 读取
日志不打印 Authorization header
API 原始响应写入 data_raw，不覆盖处理后数据
请求失败保留 request_id、错误类型和重试次数
测评集不能拿去生成可回收的标准教师轨迹
```

## 4.4 数据交付

```text
homeflow_demo/data_raw/v2/deepseek/
  每次 API 请求一条原始记录

homeflow_demo/data_processed/v2/
├── teacher_candidates.jsonl
├── verified_success.jsonl
├── verified_failure.jsonl
├── parse_errors.jsonl
├── oracle_fallback.jsonl
└── manifest.json
```

每条候选记录必须带：

```text
scenario_id
request_id
model_name
prompt_version
raw_response 或 raw_response_path
parsed_trajectory
verification_result
timestamp
```

## 4.5 批量规模

第一轮：

```text
训练场景：       80
每场景候选数：   3
预计 API 请求：   240 次
成功轨迹目标：   至少 80 条
```

如果 DeepSeek 成功率不足，不能直接修改评测结果。应记录失败原因，并使用 Oracle 轨迹补齐训练数据。

## 4.6 V2 验收标准

```text
候选 JSON 的解析失败不会中断整批任务
HomeEnv 能按 turn 验证所有候选工具调用
成功轨迹 success=True 且完成度为 1.0
失败轨迹不会进入 verified_success.jsonl
同一场景成功轨迹去重结果稳定
原始响应可以追溯到 scenario_id 和 request_id
API key 不出现在任何输出文件和日志中
```

## 4.7 V2 不做的内容

```text
不把 DeepSeek 评分当 reward
不让 DeepSeek 判断 HomeEnv 成功
不把失败轨迹直接混入主 SFT 数据
不调用测评模型给最终结果打分
```

# 5. V3：SFT 数据集与训练环境

## 5.1 版本目标

把 V1 Oracle 轨迹和 V2 HomeEnv 验证成功的 DeepSeek 轨迹统一转换成 Qwen2.5-1.5B-Instruct 可消费的 SFT 数据，并建立独立训练环境。

## 5.2 前置条件

```text
V1 场景和 Oracle 轨迹通过验收
V2 至少产出一批 verified_success
准备 Qwen2.5-1.5B-Instruct Transformers 权重
确认磁盘剩余空间足够保存模型和 adapter
```

当前本机只有 Qwen2.5-7B GGUF，不能直接用于这个版本的 SFT。V3 必须准备 Hugging Face/Transformers 格式的 1.5B 权重。

## 5.3 环境交付

单独创建训练环境，不修改 MiniMind 学习环境：

```text
/root/autodl-tmp/envs/homeflow-trl/
```

安装并锁定：

```text
torch
transformers
trl
peft
accelerate
datasets
python-dotenv
```

只有做 QLoRA 时才加入：

```text
bitsandbytes
```

交付文件：

```text
homeflow_demo/requirements-trl.txt
homeflow_demo/requirements-trl.lock
homeflow_demo/environment_setup.md
```

## 5.4 代码交付

```text
homeflow_demo/data/dataset_builder.py
  将 verified_success 转为 SFT JSONL。

homeflow_demo/data/validate_dataset.py
  检查消息角色、tool_calls、tool response 和环境结果。

homeflow_demo/train/config.py
  读取模型、LoRA、长度、batch 和保存路径配置。

homeflow_demo/train/model_loader.py
  加载 Qwen tokenizer、model 和 PEFT adapter。
```

## 5.5 数据交付

```text
homeflow_demo/data_processed/v3/
├── sft_train.jsonl
├── sft_val.jsonl
├── sft_rejected.jsonl
└── manifest.json
```

第一版数据建议：

```text
成功 SFT 样本： 120～180 条
训练/验证：     8:2
失败轨迹：      单独保存，不进入主训练集
```

每条 SFT 样本必须能回答：

```text
来自哪个 scenario_id？
是否经过 HomeEnv 验证？
最终是否 success=True？
包含几次工具调用？
```

## 5.6 V3 验收标准

```text
SFT JSONL 可以被 tokenizer 正确加载
所有 assistant tool_calls 都能重新解析
所有 tool response 都是合法 JSON
训练集和验证集没有 scenario_id 重叠
环境结果字段不进入模型输入文本
可以完成一次不更新参数的 forward smoke test
```

## 5.7 V3 不做的内容

```text
不训练完整 epoch
不做 GRPO
不启用 vLLM
不启用 QLoRA
不比较多个 LoRA rank
```

# 6. V4：LoRA-SFT 与 Base/SFT 基线测评

## 6.1 版本目标

让 Qwen2.5-1.5B 学会 HomeEnv 工具协议，并证明 SFT 阶段确实提高了基本工具调用能力。V4 结束后，模型还没有经过 RL，但已经可以进行可解释的 Base/SFT 对比。

## 6.2 代码交付

```text
homeflow_demo/train/sft.py
  使用 TRL SFTTrainer + PEFT LoRA 训练。

homeflow_demo/eval/run_eval.py
  让 Base 或 SFT 模型和 HomeEnv 交互。

homeflow_demo/eval/metrics.py
  计算成功率、合法动作率、非法动作率和步数。

homeflow_demo/eval/report.py
  将评测 JSON 转换成 Markdown 报告。
```

## 6.3 SFT 初始配置

```text
模型：                   Qwen2.5-1.5B-Instruct
精度：                   BF16
LoRA rank：              16
LoRA alpha：             32
target_modules：         q_proj、k_proj、v_proj、o_proj
per_device_batch_size：  1
gradient_accumulation：  4～8
max_seq_length：         768～1024
gradient_checkpointing： 开启
use_cache：              关闭
```

## 6.4 测评交付

对同一批冻结场景分别运行：

```text
Base checkpoint
SFT adapter checkpoint
Oracle planner
```

输出：

```text
homeflow_demo/results/v4/
├── base_metrics.json
├── sft_metrics.json
├── oracle_metrics.json
├── episode_records.jsonl
└── report.md
```

## 6.5 V4 验收标准

```text
SFT adapter 可以保存和重新加载
Base/SFT/Oracle 使用同一 eval 场景
SFT 的合法工具调用率高于 Base
SFT 能完成至少一种单设备控制任务
评测记录包含每个 episode 的动作和 HomeEnv final_result
重新运行同一 seed，规则环境结果一致
```

如果 SFT 没有提升，先检查数据格式、chat template、工具 token 和评测解析，不进入 V5。

# 7. V5：HomeEnv 在线 Rollout 接口

## 7.1 版本目标

在不更新模型参数的情况下，让 SFT 模型针对同一任务生成多条独立 HomeEnv 轨迹，并保存 GRPO 所需的 token 和环境信息。

V5 是 RL 的关键接口版本。它不负责优化参数，只负责回答：

```text
一条语言模型 completion 如何变成多轮工具轨迹？
工具结果如何重新拼入上下文？
每条轨迹的 completion token 和 logprob 如何保存？
同一 group 的环境是否相互隔离？
```

## 7.2 代码交付

```text
homeflow_demo/train/rollout_types.py
  定义 Rollout、Turn、TokenAlignment 和 RolloutBatch。

homeflow_demo/train/rollout_parser.py
  将 Qwen 输出解析为 tool call 或 finish。

homeflow_demo/train/home_rollout.py
  驱动 HomeEnv 多轮交互，生成独立 episode。

homeflow_demo/train/logprob_utils.py
  计算 completion token 的 old logprob，并生成 mask。

homeflow_demo/train/rollout_smoke.py
  用固定模型或 mock policy 验证 rollout 数据结构。
```

## 7.3 rollout 数据交付

```text
homeflow_demo/data_processed/v5/
├── rollout_samples.jsonl
├── rollout_failures.jsonl
└── manifest.json
```

每条 rollout 至少保存：

```text
scenario_id
group_id
rollout_id
messages
tool_calls
tool_results
prompt_ids
completion_ids
completion_mask
old_per_token_logps
episode_reward
reward_components
terminated
truncated
final_result
```

## 7.4 V5 初始配置

```text
每个 scenario 的 group： 2
max_prompt_length：       256～512
max_completion_length：   128～256
最大 assistant turn：     6
每 turn 最大工具调用：    1（接口预留多个）
rollout 引擎：            Transformers 原生生成
vLLM：                    关闭
```

## 7.5 V5 验收标准

```text
同一 scenario 的 2 条 rollout 从相同初始状态开始
一条 rollout 的状态变化不会影响另一条
每条 rollout 都能得到 final_result
非法工具调用能被环境记录并给出负 reward
completion_mask 只覆盖模型生成部分
同一 prompt 能生成 2 条结构不同或 reward 不同的样本
```

如果所有 group reward 完全相同，先调整任务难度和采样配置，不进入 V6。

# 8. V6：LoRA-GRPO 最小闭环

## 8.1 版本目标

把 V5 的在线 rollout 接入 TRL/自定义 GRPO 更新，在单张 RTX 4090 上完成 30～80 步的最小实验。

V6 只证明训练闭环成立，不追求最终论文结果。

```text
SFT adapter
    -> 在线采样 group=2
    -> HomeEnv reward
    -> 组内 advantage
    -> LoRA policy 更新
    -> 保存 adapter
    -> eval 对比
```

## 8.2 代码交付

```text
homeflow_demo/train/grpo.py
  组织 rollout、reward、advantage、policy loss 和 optimizer step。

homeflow_demo/train/grpo_config.py
  固化 batch、group、KL、学习率、长度和显存配置。

homeflow_demo/train/checkpoint.py
  保存和恢复 LoRA adapter、optimizer、scheduler 和训练状态。

homeflow_demo/eval/compare_runs.py
  比较 Base、SFT 和 RL checkpoint。
```

## 8.3 GRPO 初始配置

```text
模型：                   SFT LoRA checkpoint
更新对象：               LoRA adapter
per_device_batch_size：  1
num_generations：        2
gradient_accumulation：  4～8
max_prompt_length：      256～512
max_completion_length：  128～256
learning_rate：          1e-5～5e-5
beta：                   0.02～0.1
gradient_checkpointing： 开启
use_cache：              关闭
reward model：            不加载
rollout：                Transformers 原生生成
```

## 8.4 训练规模

```text
RL prompts：       40～80
训练步数：         30～80 optimizer steps
group size：       2
checkpoint：       每 10 steps 保存一次
评测：             每个 checkpoint 都跑固定小 eval
```

## 8.5 V6 监控指标

```text
平均 episode reward
reward 标准差
degenerate group 比例
平均 completion 长度
合法工具调用率
非法动作率
KL reference
policy loss
GPU peak memory
```

## 8.6 V6 验收标准

```text
训练可以完成至少 30 个 optimizer steps
LoRA adapter 和 optimizer 可以恢复
训练日志中 reward、advantage 和 KL 可读取
至少部分 group 存在非零 reward 方差
训练后 checkpoint 可以独立运行 eval
SFT 与 RL 的评测结果可比较
```

如果训练 loss 下降但 HomeEnv 成功率下降，判定为 reward 或轨迹对齐问题，不把 loss 下降解释成训练成功。

# 9. V7：完整对照实验与复现报告

## 9.1 版本目标

把最小 Demo 扩大到可报告规模，并完成 Base、SFT、RL、LoRA rank、reward 和数据来源的对照。

## 9.2 数据规模

```text
训练场景：             240
验证场景：             60
测评场景：             100
每场景成功轨迹：       1～3
SFT 样本：             500～700
RL prompts：           150～240
GRPO group：           4
训练步数：             100～300
```

## 9.3 必做对照

```text
Base vs SFT
SFT vs RL
DeepSeek 轨迹 vs Oracle 轨迹
LoRA rank=8 vs rank=16 vs rank=32
有 progress shaping vs 无 progress shaping
group=2 vs group=4
```

每次只改变一个主要变量，固定：

```text
模型基座
场景划分
随机种子集合
工具 schema
最大步数
评测脚本
```

## 9.4 结果交付

```text
homeflow_demo/results/v7/
├── configs/
├── checkpoints_manifest.json
├── episode_records/
├── metrics/
├── plots/
├── ablations.csv
├── reproducibility.md
└── final_report.md
```

报告至少回答：

```text
SFT 是否提升合法工具调用？
RL 是否进一步提升任务成功率？
提升来自完成度 reward 还是终局 reward？
LoRA rank 是否影响泛化？
训练是否出现 reward hacking？
模型在未见组合和未见措辞上是否仍然有效？
单卡训练消耗多少时间和显存？
```

## 9.5 V7 验收标准

```text
所有结果可以从配置和 checkpoint 重新生成
train/val/eval 场景无泄漏
每个结果都记录 HomeEnv 版本和 reward 版本
至少完成一组完整消融
报告区分已验证事实和推断
失败实验也保留日志和原因
```

# 10. 版本交付目录总览

```text
V0：homeflow_demo/env + tests
  交付 HomeEnv 最小可运行内核

V1：env schema + scenario_generator + planner
  交付结构化场景、Oracle 轨迹和可复现环境

V1.1：AssistantTurn + ToolEvent + TurnResult + turn trajectory
  交付模型决策步与环境 step 对齐的接口

V2：deepseek_teacher + trajectory_verifier + raw data
  交付候选轨迹、成功轨迹、失败轨迹和请求审计

V3：dataset_builder + validate_dataset + TRL 环境
  交付可加载的 SFT JSONL 和训练环境

V4：sft.py + eval/
  交付 Base/SFT/Oracle 基线和首个 LoRA adapter

V5：rollout_types + home_rollout + logprob_utils
  交付 GRPO 所需完整在线轨迹

V6：grpo.py + checkpoint.py
  交付单卡 LoRA-GRPO 最小训练闭环

V7：对照实验 + 报告
  交付可复现结果、消融和研究结论
```

# 11. 当前执行顺序

当前不直接进入训练，执行顺序为：

```text
当前：V1.1 已完成
  |
  v
下一步：V2
  调用 DeepSeek，生成候选 assistant turn 并由 HomeEnv 筛选
  |
  v
验收 V2
```

V2 完成之前，下面这些工作暂缓：

```text
不进入正式 SFT 训练
不进入 GRPO 训练
不写 GRPO optimizer
不引入 vLLM
不扩大设备类型
```

## 12. 每个版本的结束报告格式

每个版本完成后新增一个版本报告，例如：

```text
homeflow_demo/reports/V1_report.md
```

固定包含：

```text
版本目标
实际交付文件
运行命令
测试结果
数据统计
已验证事实
未完成事项
残余风险
是否允许进入下一版本
```

这样可以避免“代码写了但不知道是否完成”，也能保留每个阶段的研究轨迹。
