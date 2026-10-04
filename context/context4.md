# HomeFlow Demo 项目上下文（四）

记录时间：服务器本地2026-10-05凌晨，Asia/Shanghai，对应UTC的2026-10-04晚间。接`context3.md`；本文是当前进度入口。运行文件部分时间为UTC，所以日志里的2026-10-04 18点对应本地2026-10-05 02点。

## 1 当前停在哪

Qwen2.5-1.5B-Instruct的第一轮LoRA SFT已经完成，基线与三个epoch的固定200条环境评测、DeepSeek D6复核也全部完成。训练、评测都已退出，GPU空闲；6008只读展示页面仍在。GRPO没有开始，0.6B与2B也没有进行正式SFT。

```text
千条教师成功轨迹
  -> 排除6条带越界错误尝试的T4轨迹，剩994条
  -> 500训练 / 100验证 / 200测试 / 194备用
  -> 1.5B LoRA SFT：micro4 × 累计2，有效batch8
  -> 连续3个epoch，共189次更新
  -> 保留checkpoint-63 / checkpoint-126 / checkpoint-189
  -> 按验证loss选择epoch3，另存selected_adapter
  -> 四模型各200条自主环境评测，共800条、4285次generate
  -> 310条待审轨迹补D6三票，100并发上限，930次API调用
  -> 完整成功率：0% / 72.5% / 84.5% / 88%，没有待审项
```

最近已完成的训练与评测总结提交是`4252b9e`，已推送GitHub。当前这批新增算力记录、context改名及进度文档随后单独提交，不把历史提交号当作永远不变的HEAD。

## 2 新对话先读什么

```text
context/context4.md                              最新进度，先读本文
newdoc/18_1.5B_SFT四模型效果_固定200条测试.md       四模型完整分数、分类与失败例子
newdoc/19_1.5B_SFT训练复盘_数据方法日志与调整.md    训练方法、实际日志、batch调整、checkpoint
newdoc/5090算力支持能力.md                        本机资源、已验证负载、迁移检查项
source_server.md                                 服务器仓库外模型、环境、源码与产物

需要追背景再读
  context/context1_初心与设计.md、context2_演进与现状.md、context3.md
  newdoc/10_数据合成管线_全流程.md、11_模块功能与输入输出示例.md
  newdoc/02_提示词_重写稿与旧版全文.md
```

`context3.md`由原`context6.md`改名，主要正文保留10-04历史状态；其中“SFT尚未开始”等说法已经过时。旧Windows few-shot、GGUF、12轮评测也属于另一套实验，不能同本次HF、10轮、固定200条的分数直接混用。

## 3 本轮训练与数据口径

训练数据来自`new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl`。按家庭初始状态和任务目标分组，四个集合的组id互斥；训练五类各100条，验证各20条，测试各40条。没有把轨迹不同轮拆到不同集合，也没有把隐藏目标作为模型输入。

```text
一整条轨迹 = 一条训练样本
  system和用户原话保留
  工具回执作为user observation保留
  每次assistant JSON输出及结束token计算loss
  system、user、角色头、padding的label为-100

500条训练轨迹包含2790段assistant输出
  -> 3个epoch访问8370个监督输出段
  -> 优化器更新仍然只有189次
```

使用TRL SFTTrainer、PEFT LoRA，BF16基座、SDPA、gradient checkpointing。LoRA为r16、alpha32、dropout0.05，目标为attention和MLP七类投影，18,464,768个可训练参数。学习率1e-4，max_length3072、动态padding、packing关闭。

最初计划micro2×累计4；两条轨迹短冒烟后，用户要求调整为micro4×累计2，学习率、数据与epoch数量不变。用户批准后直接正式开跑，没有另外做4×2压力测试；正式运行已验证三轮完整完成，189条step日志、3条验证日志、1条训练汇总落盘。

训练本地时间02:06:02至02:13:57，端到端475.557秒。allocated显存峰值22.43 GiB，reserved峰值29.06 GiB；旧约13GB冒烟数字不能代表正式4×2。每轮只保存一份训练checkpoint，没有大量逐step模型副本，基础模型也没有重复保存。

## 4 提示词和few-shot已核查

用户曾担心千条教师轨迹带few-shot、SFT却删除示例；核查历史代码与实际500条训练输入后，确认A提示词和公开工具表均保留，500/500训练system与历史装配一致，首次user与原始请求一致。基线、epoch1/2/3测评使用相同A提示词。

```text
保留：A_policy内的JSON格式、危险拒绝等内嵌示例
没有额外拼接：旧FewShotPolicy的多轮示范对话

代码few_shot=false
  -> 指没有额外示范对话
  -> 不表示A提示词里面没有示例
```

历史千条批次未保留完整HTTP请求线日志，结论依据提交历史、装配代码和实际SFT消息；详细证据见第19篇。这轮没有因此重训，也没有改提示词重跑测试。

## 5 完整效果与尚存问题

主分数采用C-1到C-4全过，并对T3/T4/T5追加D6三票多数决；T1/T2沿用项目规则跳过D6。程序通过率和完整成功率需分开引用。

| 模型 | 验证loss | 程序C通过 | C+D6完整成功 | T1 / T2 / T3 / T4 / T5，各40条 |
|---|---:|---:|---:|---|
| 基线 | 0.34534628 | 0/200 | 0/200，0% | 0 / 0 / 0 / 0 / 0 |
| Epoch1 | 0.08731062 | 154/200 | 145/200，72.5% | 39 / 19 / 15 / 36 / 36 |
| Epoch2 | 0.07568157 | 175/200 | 169/200，84.5% | 40 / 30 / 23 / 37 / 39 |
| Epoch3 | 0.07202742 | 183/200 | 176/200，88% | 40 / 34 / 26 / 39 / 37 |

Epoch3总分最高，T3模糊意图仍只有26/40；T5查询从epoch2的39/40降到37/40。T4中epoch3仍有一条曾尝试越界写入、被环境挡住后再正确拒绝，所以88%不等于没有过程风险。D6三票来自同一个deepseek-chat模型，不等于三个独立人工评审。

固定200条来自同一合成分布，训练与测试仍有25种相同请求文本，场景组不同；T4训练池缺READ_ONLY_DEVICE示范。当前测试集已经用于问题分析，之后据此调整训练时应另留未查看的新测试集。详细例子和限制留在第18篇，不在本文重复展开。

## 6 DeepSeek复核与当前现场

用户在仓库根目录配置`.env.deepseek`后，新增`training/10-5_sft/review.py`及同名中文说明、6项无网络回归测试。复用原D6模板，只对已经保存且C通过的T3/T4/T5补审，不加载本地模型、不改原始record、Scenario或C标签。

```text
待审数量：epoch1 96 / epoch2 105 / epoch3 109，合计310
并发上限：100条任务，每条顺序投3票
结果：930次HTTP尝试，930次合法回复，9.567秒
      288条判对 / 22条判错 / 0系统失败 / 0待审
保存：semantic_review/，投票日志与可恢复缓存独立于原轨迹
```

实际根目录密钥已确认在Git忽略范围，未写入报告或提交。包括新复核测试在内，129项自动测试通过。所有生成与API执行已结束，不能因6008仍有页面就判断训练尚在运行。

本机为单张5090，容器CPU配额相当于25个逻辑核、内存限额92 GiB；宿主机显示的754 GiB不属于本实例完整可用内存。详情和官方架构对照在`5090算力支持能力.md`。

## 7 文件、服务与下一步边界

```text
仓库代码    /root/autodl-tmp/10-04/training/10-5_sft/
基础模型    /root/autodl-tmp/models/Qwen2.5-1.5B-Instruct/hf/
训练环境    /root/autodl-tmp/sft-venv/
数据划分    /root/autodl-tmp/training_runs/10-5_sft/data/
训练产物    同根目录sft-main/
            checkpoint-63、checkpoint-126、checkpoint-189、selected_adapter
训练日志    services/train.log、sft-main/metrics.jsonl
训练统计    sft-main/training_summary.json、training_status.json、run_config.json
测试产物    comparison_test_20261005/{baseline,epoch1,epoch2,epoch3}/
语义补审    comparison_test_20261005/semantic_review/
完整统计    comparison_test_20261005/final_comparison_statistics.json

展示页面    0.0.0.0:6008，只读，每3秒刷新；当前HTTP 200
本机访问    http://127.0.0.1:6008
当前映射    https://uu753393-afb3-4b7a916d.westd.seetacloud.com:8443
独立进程    monitor PID95819，PPID1；训练已completed
```

模型、venv、llama.cpp和大运行产物在仓库外；git clone只能恢复代码和文档，换服务器需按`source_server.md`另行迁移这些内容。展示服务与对话和SSH解耦，但实例关机仍会停止；公网映射属于当前实例，换机后重查。

当前没有训练或评测待完成项。下一步可以讨论T3/T5数据覆盖、严格危险拒绝指标或GRPO方案；用户尚未要求启动新训练，不自动重训、不改当前checkpoint、不把0.6B/2B下载完成写成训练完成。真实中断恢复、多卡及GRPO容量都仍待验证。
