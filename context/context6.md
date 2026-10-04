# HomeFlow Demo 项目上下文（六）

> 文档用途：接 context2_演进与现状.md。记录 2026-10-01 至 2026-10-04 的最新进展与现场状态。
> 梳理日期：2026-10-04。
> 关系：context1–5 已合并为 context1_初心与设计.md 与 context2_演进与现状.md；本文件是最新快照。

## 0 现在停在哪

数据管线稳定可用，最近一次配额批次一次跑满 **1000 条成功轨迹（每类 200）**；提示词、画像、评测、仓库边界都更新到 10-04 的状态。SFT / LoRA-GRPO 尚未开始。

```text
最新数据批次   new_demo/runs/quota200_20261004_v2/
  1000 条进集（每类 200，C-1..C-4 全过 + D6 对/跳过）
  蓝图 1268、轨迹 1268（含失败留档）、尝试 1432、用时 722.5 秒
  每类尝试：T1 203 / T2 391 / T3 410 / T4 224 / T5 204
  服务：DeepSeek 官方 API（deepseek-chat），每类 10 路并发

失败批        new_demo/runs/quota200_20261004_partial/（崩后残留 172 条，改名保留）
提示词        new_demo/data_static/D0_templates/（19 份，02 重写版，commit bab3628）
画像库        100 条（p01–p100；2026-10-04 由 25 条扩到 100，commit d7f3645）
评测集        new_demo/eval_sets/quota50_20261002_v2/（250 条）

200 条本地评测（11 版 few-shot、12 轮、2 路并发）
  Qwen3.5-2B 112/200；Qwen2.5-1.5B 90/200；Qwen3-1.7B 63/200
  （三条版 few-shot 旧成绩：85/200；详见 newdoc/12 与 newdoc/09）

最近提交      d98b38f（千条批次 + 写盘重试补丁）
              d7f3645（画像扩到 100）
              fcb90e9（newdoc/10、11 审阅修正）
              391f94b（删除 Matter 副本） / 301d76a（仓库改全收录） / 114484a（.gitignore+source.md）
```

## 1 新对话先读什么

```text
必读（现状口径）
  context/context1_初心与设计.md        为什么做、设计原则、模块边界
  context/context2_演进与现状.md        走到哪一步、关键数字与文件指针
  context/context6.md                   本文：最近改动与现场状态
  newdoc/10_数据合成管线_全流程.md       D0→D6 真实管线
  newdoc/11_模块功能与输入输出示例.md    各模块职责与例子
  newdoc/02_提示词_重写稿与旧版全文.md   19 份提示词全文（上半=现行）
  source.md                             仓库边界、外部来源、模型登记

评测与数据
  newdoc/12_新模型200条评测.md
  newdoc/09_失败原因分析_200条.md
  new_demo/runs/quota200_20261004_v2/   最新千条批次

不要当现行口径
  已删除的 context1–5（内容合并进 context1/context2 两份）
  doc/14–16 旧 V2 writer_view、旧 A_policy 每轮重拼写法
  doc/23/26/27/28/29 是演进记录，不是待办
```

## 2 最近的改动（2026-10-03 → 10-04）

```text
2.1 文档
  newdoc 整理为 01/02/03/05/06/07/09/10/11/12 + README；
  09 每类失败占比、10 数据管线、11 模块说明、12 新模型评测；
  10、11 按代码审阅修正（D1 台数规则、T4 观察形状、probe 落盘、配额默认值、批次数字）。

2.2 仓库边界
  .gitignore 从白名单改为「除模型权重、llama.cpp、密钥、缓存外全收录」；
  Matter（connectedhomeip）本地副本删除（10,027 个文件/约 70MB），
  其目录里的自主分析移到 simuprocject/analysis_docs/；
  仓库跟踪文件从 336 → 2771 →（含新批次后更多）。

2.3 画像库
  25 → 100 条（新增 p26–p100）；全部与 21 条设备目录对齐、无违禁词；
  同步改 D0_personas.md、D0_template.py 注释、tests 与 newdoc/10、11。

2.4 千条数据
  quota200_20261004_v2 跑满 1000 条成功（每类 200）；
  第一次尝试在 125 秒时因 Windows 高频重写 D_dataset.jsonl 触发
  OSError(EINVAL) 崩溃；给 PIPE_pipeline、D_copy_dataset 的写盘加了重试后一次通过。

2.5 新服务器
  ssh -p 18378 root@connect.westd.seetacloud.com（新容器 a6a040af…）
  /root/autodl-tmp/10-04/ = 仓库，2026-10-04 已对齐到 1cb6b5a（与云端一致）
  /root/autodl-tmp 下没有 autodl-temp 目录（只建过 10-04）
  ~/.codex/codex-models.json：补 codex-auto-review；gpt-5.6-sol 改 low/medium/high/xhigh
  四档、上下文 480k；改前有 .bak-20261004-* 备份

  2026-10-04 20:55 按站实测再修：gpt-6.1-sol 档位 none → low/medium/high/xhigh/max
  （默认 medium，报错起因）、gpt-6-astra 去掉站不认的 ultra、补 gpt-6-luna 条目；
  config.toml effort none → medium；备份 .bak-20261004-205509

  仓库同步约定（2026-10-04 起）：云端 GitHub 为主仓库，本地与服务器都推云端；
  服务器 GitHub HTTPS 不可用（ls-remote 40s 超时），但 ssh github.com:22 通，
  已把 origin 换成 git@github.com:juezhan340/autodl-tmp.git，并生成部署密钥：
    ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK984B6QU9tkRJnpp5ncYlVpdLxeicbH9fTDHeJr1Cb6 autodl-18378
  2026-10-04 公钥已加到仓库 Deploy keys（Allow write access）；实测服务器 git fetch
  5.5s、临时分支推送成功并已删除，本地/服务器/云端三方同步打通。

2.6 网络
  本机直连 GitHub 不稳定，push 走本地代理：
  git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main
  服务器直连 GitHub HTTPS 超时；SSH(22) 可用，origin 走 git@github.com 拉取/推送
```

## 3 日志与产物位置

```text
每个批次目录结构一致：
  results/trajectories/summary/local_model.env/api/completions.jsonl（本地模型评测）
  或 data_processed/{D4_blueprints,D5_trajectories,D_dataset,D_manifest}
     + data_raw/{D2_drafts,D34_failures,api/completions}
     + reports/{progress.md,quota.md,D4_preview.md}

本机关键批次
  quota200_20261004_v2          最新千条（1000 进集）
  quota200_20261004_partial     崩溃残留（172 进集）
  quota50_20261002_v2           上一批 250 条
  qwen15b_eval_100/100b_*       1.5B 评测（11 版 / 三条版）
  qwen3_17b_eval_200_fs         63/200
  qwen35_2b_eval_200_fs         112/200

注意：runs/ 现在随仓库入库；llama-server 的 stdout 没有单独落盘（模型调用记录在 api/）。
```

## 4 复现

```text
千条配额批次
  python -m new_demo.PIPE_run --quota --target-success 200 --max-attempts 600 \
    --workers-per-category 10 --seed <seed> --output-dir new_demo/runs/<批次>

本地模型评测（11 版 few-shot，200 条 = A+B 两个 id 文件合并）
  llama-server.exe -m <gguf> --port 18080 -c 32768 --parallel 2 -ngl 99 --no-mmproj -rea off --jinja
  python new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py \
    --server http://127.0.0.1:18080 --model <name> --output-dir new_demo/runs/<批次> \
    --workers 2 --max-turns 12 --few-shot --task-ids "<200 个 id>"
```

## 5 风险与下一步

```text
1  服务器 10-04 已对齐 1cb6b5a；把部署公钥加到 GitHub 后，服务器可直接 fetch/push。
2  SFT 未开始；doc/21 是把轨迹转成 SFT 消息的方案底稿。
3  quota200_20261004_partial 是崩溃残留，可留作额外数据，也可删。
4  主提示词改动要走 newdoc/02 审阅流程；改完 pytest（当前 86 passed）。
5  本机 GitHub 推送依赖代理 7897；若代理关闭，push 会失败。
```
