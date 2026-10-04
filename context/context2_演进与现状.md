# HomeFlow Demo：演进与现状（合并自 context1–5，精简版）

> 用途：新对话快速知道「走到哪一步、现在的数字与位置」。
> 整理日期：2026-10-04。中间过程只保留结论级描述，细节看对应 newdoc / doc。

## 0 现在停在哪

数据管线（D0–D6）完全可用，最近一次配额批次一次跑满 **1000 条成功轨迹（每类 200）**；提示词、画像、评测三条线都有可查产物。SFT / LoRA-GRPO 尚未开始。

```text
最新数据批次   new_demo/runs/quota200_20261004_v2/
  每类 200 条进集（C-1..C-4 全过 + D6 对/跳过），共 1000
  蓝图 1268、轨迹 1268（含失败留档）、尝试 1432、用时 722.5 秒
  每类尝试：T1 203 / T2 391 / T3 410 / T4 224 / T5 204

提示词         new_demo/data_static/D0_templates/（19 份，02 重写版，commit bab3628）
画像库         100 条（p01–p100，2026-10-04 从 25 条扩到 100，commit d7f3645）
评测集         new_demo/eval_sets/quota50_20261002_v2/（250 条任务 + 真值）

200 条本地模型评测（11 版 few-shot、12 轮、2 路并发）
  Qwen3.5-2B     112/200   ← 目前最好
  Qwen2.5-1.5B    90/200
  Qwen3-1.7B      63/200
  （三条版 few-shot 的 1.5B 旧成绩：85/200）
```

## 1 演进简史（一段一层）

```text
V1        原子动作环境 + 规则 Oracle；140 条场景，验证状态机与谓词。
V1.1      修正信用分配：一次 assistant 输出 = 一个 turn = 一条策略 step。
V1.2      A/B/C 重写 + 八类任务；18 项测试、140 条场景与轨迹重放通过。
旧 V2     提出 D0 Blueprint + 外部模型改写用户话（writer_view）；
          20 条 smoke 仅 2 条 clean_success，暴露「语义写死、finish 契约不一致」两个根因，被推翻。
17 / 18   新架构设计：D0–D6 数据管线、两步打分（蓝图资格 / 轨迹复核）、D4 后停闸。
new_demo  按 17/18 落地新代码；之后多轮调整：
  23  家电扩容（户型 9→15、设备 15→21）、observe_home 瘦身
  26  主灯两档 dim/bright、闭区间、task 与用户话按 operator 配对、T4 危险藏在数值里
  27  25 条画像 + D2/D3/D6 提示词正文
  28  C-2 不冻整屋、加湿器只留开关、T4 讲意思、A 改 system 一次 + append、画像仅供参考
  29  ge/le 改为「相对 s0 初值」，不再设数字门槛
提示词重写  02 版：功能 + 小例子 + 完整例子 + 本轮输入；统一 eq/ge/le 说法并落盘。
评测阶段    1.5B few-shot 对照（90/85）、失败归因（newdoc/09）、新模型评测（newdoc/12）。
画像扩容    25 → 100 条（2026-10-04）。
千条数据    配额批次 quota200_20261004_v2 跑满 1000 条成功轨迹。
```

## 2 现状指针：哪份文件管什么

```text
现行规格        newdoc/10_数据合成管线_全流程.md      D0→D6 的真实管线
                newdoc/11_模块功能与输入输出示例.md   各模块职责/接口/例子
                newdoc/02_提示词_重写稿与旧版全文.md   19 份提示词全文（上半=现行）
                source.md                            仓库边界、外部来源、模型登记
提示词（运行）   new_demo/data_static/D0_templates/    19 份，运行时只填占位符
画像库          new_demo/data_static/D0_personas.jsonl 100 条
评测集          new_demo/eval_sets/quota50_20261002_v2/
评测记录        newdoc/05、newdoc/09、newdoc/12
历史设计        doc/17、18、23、26、27、28、29（演进记录，不再改）
```

```text
代码入口（new_demo/）
  PIPE_run.py        CLI：默认停 D4；--full；--continue-from-d5；--quota
  data/              D0_template、D1_home_maker、D2_task_writer、D2_request_writer、
                     D3_reviewer、D4_oracle、D5_run、D6_judge、D_copy_dataset、PIPE_pipeline
  env/               B_home_env / B_schema / B_state_engine / B_tool_schema / B_models
  eval/              C_episode_runner / C_episode_evaluator
  agents/            A_policy（DeepSeekPolicy）、DeepSeek_client
```

## 3 关键教训（别再犯）

```text
语义写死在 Python、模型只改写 -> 推翻（writer_view 之败）
finish 契约三处不一致 -> 公开 schema、评测、提示词必须同一套
用数字门槛描述方向题 -> 改「相对 s0 初值」
画像写进硬约束 -> 改「只借口吻，题面只用本轮 s0」
C-2 冻整屋 -> 只认 conditions 与 keep
加湿器做档位 -> 只留开关
失败样本静默消失 -> 一律留痕（D34_failures、总表不删）
Windows 高频重写同一文件偶发 EINVAL -> 写盘加 OSError 重试
```

## 4 服务器与仓库现状

```text
GitHub        https://github.com/juezhan340/autodl-tmp.git（私有）
             本机直连不稳，推送走本地代理：git -c http.proxy=http://127.0.0.1:7897 push origin main
本机仓库      D:\homeflow\autodl-tmp（除模型权重、llama.cpp、密钥、缓存，全部入仓库）

autodl 服务器（2026-10-04 起用）
  ssh -p 18378 root@connect.westd.seetacloud.com
  仓库副本   /root/autodl-tmp/10-04/（快照 commit fcb90e9，未含 100 画像与千条批次）
  Codex 模型表 ~/.codex/codex-models.json
    已补 codex-auto-review；gpt-5.6-sol 改为 low/medium/high/xhigh 四档、上下文 480k

模型权重（仓库外）D:\D_program\models\（Qwen2.5-1.5B、Qwen3-0.6B 系列、Qwen3-1.7B、Qwen3.5-2B）
  来源、SHA-256 见 source.md §3
```

## 5 接下来

```text
没让做就先不做
  SFT / LoRA-GRPO 未开始；doc/21 是轨迹转 SFT 的方案底稿
  主提示词改动要先审（newdoc/02 流程），改完跑 pytest

可做的自然下一步
  把 quota200_20261004_v2 的 1000 条轨迹转成 SFT 消息（按 doc/21）
  或继续扩数据 / 用新画像库做对照评测
```
