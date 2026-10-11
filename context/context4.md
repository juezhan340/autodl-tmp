# HomeFlow Demo 项目上下文（四）

更新于2026-10-11，Asia/Shanghai。本文是最新进度入口；`context3.md`保留10-04历史，不应把其中"SFT尚未开始"等状态当当前状态。
第1~6节保留10-06的GRPO训练与评测快照（仍是有效历史）；第7节是10-07以来的"1007新任务族设计"进度，是当前工作前沿。

## 1. 当前停在哪

2026-10-11 补记：GRPO 部分最后一次核对是 10-10，主训练 52/64 次更新、4720/6000 条轨迹，status=running；10-11 服务器端口 31037 连不上，未再核对。实时状态一律看 active_run.json → training_status.json；若已跑完，先看 checkpoint-full500 和自动最终评测。下面 1~6 节的数字是 10-06 快照，保留作历史对照。

1.5B的3轮LoRA SFT与四模型固定200评测已完成。100任务GRPO阶段也已训练、评测完成。正式500任务池已经全部首遍覆盖，主训练仍按原方案反馈复访；截至上述快照为39/64次实际更新、872个候选组、1248条采用轨迹，status=running，无新错误，固定SFT参考未变。**500/500是任务覆盖数，不表示整轮训练已经结束。**

用户本次要求开始评测并总结。已独立评测冻结的`checkpoint-coverage500`（本轮step21），原200条和原D6全部完成：182/200，91%，无待确认。最终`checkpoint-full500`尚未产生，不能把91%称作最终权重成绩。训练结束会按原入口自动评测最终权重；本次没有停掉复访，也没有中途改奖励/归一化或启动另一轮训练。

```text
SFT epoch3                          176/200，88%
  ↓ 100任务GRPO：25更新、400采用轨迹
GRPO stage1                         179/200，89.5%
  ↓ 正式500池首遍：2000候选、672采用、21更新
GRPO checkpoint-coverage500 step21   182/200，91%，本次完整阶段评测
  ↓ 仍在反馈复访，当前39/64更新
checkpoint-full500                  尚未完成，最终评测尚未开始
```

综合文档已经先写完，再更新本文：[第13文档](../newdoc/1004推进文档/13_GRPO500任务阶段评测_训练复盘与下一步改进.md)。它包含实际评测、训练量、曲线与日志、OOM定位、奖励/归一化讨论、真实失败案例及下一版可实施规格。后续状态会变化，实时以active_run指向的training_status为准，不把本静态快照当常驻状态。

## 2. 新对话先读什么

```text
当前进度        context/context4.md
1007新任务族    newdoc/1007推进文档/01~05（当前工作前沿；05 是结构与字段的对齐基准）
MCP接口基准     newdoc/1007推进文档/对齐_目前方案与交付接口.md、
                对齐_一次性调度与持久化调度-两个通用语义接口.md
论文与训练辅助   assitdoc/05~07（交叉领域论文、OPD 小模型调研、两版 GRPO 对比）
本次综合复盘    newdoc/1004推进文档/13_GRPO500任务阶段评测_训练复盘与下一步改进.md
GRPO落地规格    同目录12_GRPO落地设计_轨迹预处理奖励判定与4x4冒烟.md
GRPO原理讨论    同目录11_GRPO必要性_奖励与分组原理_5090训练方案.md
SFT效果/方法    同目录08_1.5B_SFT四模型效果_固定200条测试.md、09_1.5B_SFT训练复盘_数据方法日志与调整.md
资源与迁移      同目录10_5090算力支持能力.md、source_server.md
目录映射        newdoc/README.md
更早历史        context1_初心与设计.md、context2_演进与现状.md、context3.md
```

newdoc已经由用户重新排布，旧18/19对应现在1004推进文档的08/09，旧5090文档对应10。旧Windows GGUF、额外FewShotPolicy与12轮评测属于不同实验，不能同本次HF、10轮、固定200的分数混用。

## 3. 数据与提示词口径

教师数据源为`new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl`：1000成功轨迹排除6条带越界尝试的T4，剩994。按家庭初态与目标分组，划分500训练/100验证/200测试/194备用，组id互斥；五类训练各100、验证各20、测试各40。

SFT保留整条多轮轨迹，一条样本含多次assistant监督；500条有2790段assistant输出，3epoch访问8370段，实际optimizer更新189次。system、用户消息与工具观察参与上下文，不计算loss；每次assistant JSON与结束token计算loss。SFT使用TRL SFTTrainer、PEFT LoRA、BF16、SDPA、gradient checkpointing，r16/alpha32、七类attention/MLP投影，18,464,768可训练参数。

```text
SFT最终配置   micro4×累计2，有效batch8，学习率1e-4，3epoch，3072上下文
保留权重      checkpoint-63 / 126 / 189；按验证loss选epoch3，selected_adapter
历史效果      原模型0/200；epoch1 145/200；epoch2 169/200；epoch3 176/200
历史峰值      SFT allocated22.43GiB / reserved29.06GiB，不能用旧13GB冒烟代替
```

few-shot已经核查：教师、SFT训练及当前HF环境评测保留相同A提示词和公开工具表，以及A内嵌JSON/拒绝示例。代码旧`few_shot=false`指没有额外拼接旧FewShotPolicy多轮对话，不表示system里没有示例。GRPO训练温度0.7，评测沿用greedy；提示词相同不表示采样方式相同。

旧SFT评测310条语义复核、930票已完成。当前GRPO阶段评测107条、321合法票也已完成；原200轨迹、标签、模型文件均未被补审改写。比较文件中13条字面D6“待审”来自C已经失败的记录，按协议无需D6，final_success=false；实际pending_semantic=0。

## 4. GRPO真实方法与已验证结果

GRPO入口是本项目`train_full.py`，复用Torch/PEFT/TRL工具；共享一个BF16基座和两套FP32 LoRA。policy接续100任务最终adapter、恢复AdamW；reference仍固定SFT epoch3，beta=0.02，学习率1e-5。不得关闭adapter后把原无SFT基座误当SFT参考。

```text
8任务组×每组G4=32条完整轨迹
  → micro16反向 + micro16反向 → 一次step
rollout同时4路；old/ref概率放CPU；真实生成token计算loss
奖励r2；A=R−本组均值；本轮未除标准差
整组新候选筛选，未采用轨迹不跨policy训练
最大1500候选组/64实际更新，全500首遍覆盖后反馈复访
```

100阶段78%组同分、平均每更新0.88个有差异组；正式500首遍138/500有差异，采用128/168有差异，平均每更新6.10组。500项均生成评分，只有168唯一任务进入这21次梯度更新。T2/T3采用109/168组，分类覆盖均衡不等于梯度采用量均衡。

初始16×2正式运行首步成功，第二步大词表log_softmax前向OOM；已保存首步、中断权重与AdamW。修复仅在概率计算层：完整micro16 decoder不变，真实生成token的LM head按128分块、非重入checkpoint重算。原CUDA autocast的log_softmax也会用FP32，显存下降来自矩阵筛选/分块/重算，不应归因于精度升级。续跑恢复52项覆盖及首步，未提交候选丢弃后重新生成，没有降micro，也没有新冒烟。

500覆盖前缀的修复后峰值allocated14.52GiB/reserved17.96GiB；主训练截至快照allocated仍14.52GiB、reserved约19.42GiB，后者包含与独立评测共卡期间的缓存变化。两项有包含关系，不能相加。动态采样无固定epoch，按update032、coverage500、final里程碑保留checkpoint，异常另存interrupted，不每batch复制完整权重。当前coverage500和update032均已保存。

| 模型 | T1 | T2 | T3 | T4 | T5 | 完整成功 | 严格安全成功 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SFT epoch3 | 40 | 34 | 26 | 39 | 37 | 176/200 | 175/200 |
| GRPO 100任务 | 40 | 35 | 28 | 39 | 37 | 179/200 | 178/200 |
| GRPO覆盖500，step21 | 40 | 37 | 28 | 39 | 38 | 182/200 | 182/200 |

相对SFT逐题9改善/3退步，相对100阶段5改善/2退步。严重过程违规轨迹2→2→0，但规则只覆盖已实现的写入/越界/keep等范围，不保证一切安全。新模型仍有12条规则错误finish、3条预算耗尽。探索性配对p≈0.146/0.453，不能夸大成显著泛化提升；200测试已经反复查看，后续应另留新未查看集合。

## 5. T5、归一化与下一步边界

T5没有放弃训练。E取证与F规则假finish停用，Φ=0，因为目前必查对象/字段主要在自然语言，TaskSpec未保存query_targets。S整体成功3分、H结尾真实0.5分及普通错误/预算/严重违规仍有效。满分3.5比其他类别低，不会直接跨任务压低A；组内分差尺度、同分和判分可靠性才是需分析的问题。

采用有差异组中43组仅S/H差异，不等于43组噪声：仅H变化的只有1组，跨度0.5；跨度小于1的采用有差异组共6个。带标准差下限的组内标准化只是下一版候选，尚未批准实施或改当前训练；它不能给同分组创造方向，也会改变PG/KL相对力度。

```text
当前训练完成 → 自动原200最终评测 → 与冻结500阶段及SFT对照
  ↓ 用隔离validation与严格安全决定保留哪个版本，不按已看test假称盲选
优先修T3意图/设备/方向、T2剩余目标与finish预算
  ↓ 新训练场景对照：热/冷、吵/安静、干/湿，正确教师路径回放验证
再补T5 query_targets、必要回执E与有限规则F、软审校准
  ↓ 独立版本比较优势标准化/分类采用配额，不同时混改所有目标
新未查看评测：新家庭/措辞、缺失读数、false/0、矛盾状态和安全边界
```

18条阶段失败中12条是T3，相对100阶段的成功任务集合未变；实际有“热却升温”“电视吵却动加湿器”“缺温度却把台灯24当温度24%”等问题。添加query_targets先支持必要观察判定，不会自动把自然语言summary变成完全可硬判的答案。具体模块输入输出、对应文件、改动边界见13文档第7节。不要把这200测试案例直接塞入训练，也不自动启动下一轮/0.6B/2B训练。

## 6. 文件与服务位置

```text
仓库          /root/autodl-tmp/10-04/
训练环境      /root/autodl-tmp/sft-venv/
基础模型      /root/autodl-tmp/models/Qwen2.5-1.5B-Instruct/hf/
SFT数据       /root/autodl-tmp/training_runs/10-5_sft/data/
SFT权重       同根sft-main/selected_adapter，固定参考
GRPO代码      training/10-5_grpo/，Python及配置均配中文md
100阶段       /root/autodl-tmp/training_runs/10-5_grpo/stage1-100-20261005T160227906618Z/
原OOM运行     同根full500-20261005T180454543706Z/
当前续跑      同根full500-resume-20261005T181501989146Z/
当前配置      full_resume_config.json；实际运行快照见run_config.json
覆盖500权重   当前续跑/checkpoint-coverage500/policy/，step21
32更新权重    当前续跑/checkpoint-update032/policy/
本次完整评测  当前续跑/checkpoint_evaluations/checkpoint-coverage500-20261005T191100770011Z/
评测结果      上述评测/evaluation/{comparison,grpo_summary}.json及reviewed_trajectories.jsonl
分析证据      当前续跑/analysis/coverage500-step21/analysis.json及同名md
曲线图片      newdoc/1004推进文档/assets/grpo_coverage500_20261006.png
复现分析      evaluate_checkpoint.py、analyze_run.py（不改主训练状态）

真实状态      GRPO根active_run.json → 运行目录training_status.json
过程日志      train.log、metrics.jsonl、sampler_state.json、candidates/、windows/
训练进程      PID24357，独立会话；PID实际存活按services启动身份核对
展示进程      PID22658，0.0.0.0:6008，只读，每3秒刷新
当前本机      http://127.0.0.1:6008
当前公网      https://uu753393-981f-3f635753.westd.seetacloud.com:8443
```

旧afb3域名已经失效。6008展示主训练；本次独立checkpoint评测已自然退出，其完成状态在自己的目录。模型、venv、llama.cpp与大运行产物在仓库外，clone代码不能代替迁移这些文件。DeepSeek根目录密钥被Git忽略，不打印、不写入文档或提交。未新跑pytest或额外冒烟；本次闭环为完整200实际评测、321票复核、重放统计及来源指纹校验。图片查看工具不支持图像输入，不声称人工截图验收。

```text
1007设计文档   newdoc/1007推进文档/01~05 与两份"对齐_"文档（TC6/TC7、时间机制、数据管线）
仓库同步       云端 github.com/juezhan340/autodl-tmp 为主仓；本地最新 f8082dd（10-11）
              本地推送走代理 127.0.0.1:7897；服务器 ssh -p 31037（10-11 连接被拒，待恢复后 git pull --rebase）
```

## 7. 1007 阶段：新任务族设计进度（当前前沿）

10-07 起进入新任务族设计，文档集中在 `newdoc/1007推进文档/`。

```text
两条新管线
  TC6 时间调度   TC6A 绝对时间、TC6B 相对时间；一次性预约，不做持久规则
  TC7 记忆       TC7A 读预置记忆（单轮）、TC7B 单轮内读写、TC7C 多轮会话（轮间不 reset）

已定关键决策
  时间机制   静止时间：now 全程冻结、不推进、无 tick；到点执行用影子执行验证；
             due_state 只保留"目标已达成/被别人改过"，掉线不处理
  时间表示   YYYY-MM-DD HH:MM，分钟精度，不存星期；7 天窗口；base_time 由 D1 抽样
  任务结构   task = base_task / time_task / memory_task；intent 与 expected_finish 必填；
             time_task、memory_task 可为 {}（老任务只有 base_task）
  字段命名   time_mention、at_time_expected、offset_minutes、due_steps、
             memory_initial、memory_expected、forbidden_actions、required_calls（待审）
             已删除：action_steps、required_effects（正面约束统一写 base_task.conditions）
  存储方案   方案 3（写入时分层）：判定真值进 task、世界初值进 world；
             蓝图真实键 blueprint_id / category / home(s0) / task / user_request；
             memory_initial 蓝图在 task.memory_task，D5 搬运到 scenario.world 供 B reset
  数据管线   新路径 data_tc/、D0_templates_tc/、data_raw_tc/、data_processed_tc/、
             eval_sets/TC_20261010_v1/；老管线只读不改
  抽样       户型/设备/画像/时间继续抽样；记忆不抽样，由 D2 依据真实 s0 与画像生成
  工具面     TC6/TC7 下发全部 8 个工具；T1~T5 不变
  其他       轮数上限 10→12（文档已改、代码待改）；新增空气净化器（文档已写、目录待加）

文档地图
  01  总体方案（TC6/TC7 定义、ABCD、仿真器与数据管线方向）
  02  时间机制对比（照搬 SimuHome 内核 vs 静止时间；已选静止时间）
  03  两条新管线设计（路径、ABCD、13 个提示词、评测方案）
  04  字段清单与存储方案（A.1~A.17 / C.1~C.26；已选方案 3；待审清单）
  05  TC6A 与 TC7A 完整管线示例（提示词→例子→轨迹→数据集；当前对齐基准）
  对齐_目前方案与交付接口 / 对齐_一次性调度与持久化调度（MCP 侧接口基准，10-09 修订）

05 文档的关键口径
  蓝图：blueprint_id / category / tc_schema / home(s0) / task 三块 / user_request / world
  world = base_time / horizon_minutes / session_turns / due_state
  D5 产出沿用 {scenario, record, labels, category, d6, d6_votes}
  新增标签：TC6A place_ok / steps_ok / settle_ok；TC7A read_ok / comply_ok / summary_ok
  TC6A 的 C-2 改走影子结算（evaluator 待改）；record 拟新增 tc_trace 块

待拍板/待落地
  required_calls 是否采用；tc_trace 字段；persona_id 是否入蓝图；kind vs category；
  memory_initial 的 D5 搬运口径；C-2 分支；12 轮与净化器的代码/数据落地
```
