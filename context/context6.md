# HomeFlow Demo 项目上下文（六）

> 文档用途：接 [context5.md](context5.md)。供新对话恢复 2026-10-01 至 2026-10-03 的进展。
> 梳理日期：2026-10-03。
> 工作区：服务器 `/root/autodl-tmp`；本机 Windows `D:\homeflow\autodl-tmp`（同一套仓库内容）。
> 注意：本文件在 `context/` 下，该目录不进 git，属于本地笔记。

## 0 现在停在哪

数据合成管线 D0–D6 仍是可用的主链，最近一次配额批次已经换成了统一 eq/ge/le 说法的提示词（commit `bab3628`）：`new_demo/runs/quota50_20261002_v2/`，302 条蓝图、302 条轨迹、250 条进集（每类 50）。这两天的工作重心从「继续跑数据」转到了三件事：把 newdoc 整理成可读的现状文档（09–12）、把新下载的两个小模型在同一批 200 条任务上评测完、把仓库边界（.gitignore 与 source.md）补到最新。

```text
本地小模型 200 条排行榜（同一批任务、11 版 few-shot、12 轮、2 路并发）
  Qwen3.5-2B     112/200   ← 目前最好
  Qwen2.5-1.5B    90/200   ← 旧基线
  Qwen3-1.7B      63/200   ← 协议弱（失败 119/137 带 C-4）
（三条版装配的旧成绩：85/200，仅作历史参考）

模型文件
  D:\D_program\models\Qwen3-1.7B-GGUF\Qwen3-1.7B-Q8_0.gguf        2.02 GB
  D:\D_program\models\Qwen3.5-2B-GGUF\Qwen3.5-2B-Q8_0.gguf        1.87 GB
  （均已登记进 source.md §3，含 SHA-256）

GPU 状态：llama-server 已停止，显存回到桌面基线（约 874 MiB / 8151 MiB）
```

## 1 新对话先读什么

```text
必读（现状口径）
  context/context6.md                     本文，看停点
  newdoc/10_数据合成管线_全流程.md          D0→D6 真实管线（对应 doc/17，已按 23/26/27/28/29 更新）
  newdoc/11_模块功能与输入输出示例.md       各模块职责与输入输出例子（对应 doc/18）
  newdoc/12_新模型200条评测.md              本次两个新模型的评测结果与复现
  newdoc/09_失败原因分析_200条.md           11 版 vs 三条版的失败原因占比（200 条）
  source.md                                仓库边界、外部来源、模型权重登记
  new_demo/data_static/D0_templates/       运行时提示词（19 份）
  new_demo/eval_sets/quota50_20261002_v2/fewshot_by_task/   当前 11 版 few-shot 装配

历史对照（不要当待办）
  context1–context5
  doc/17、doc/18（初始设计；现状见 newdoc/10、11）
  doc/23、26、27、28、29（四轮调整，已全部落地到代码与提示词）
  newdoc/01、02、03、05、06、07（轨迹、提示词全文、评测记录）

明确无关或已删除
  newdoc/04、newdoc/08 已按作者要求删除（内容在 git 历史）
  三条版 few-shot 只在 git 历史（fa872cf），当前工作区是 11 版
  doc/14–16 旧 V2 writer_view、旧 A_policy 每轮重拼写法：都不要再参照
```

## 2 这两天的进展（2026-10-01 → 10-03）

### 2.1 newdoc 整理

原来 15 份文档按主题两两合并成 8 份，之后删掉 04（few-shot 对比）和 08（LoRA 可行性）两份，又新增了 09–12。当前 newdoc 共 10 份：01 轨迹记录、02 提示词新旧全文、03 250 条任务与轨迹案例、05 1.5B 评测、06 few-shot 装配、07 换批验证、09 失败原因分析、10 数据合成管线、11 模块功能与输入输出、12 新模型评测，外加 README 索引。

### 2.2 失败原因分析（newdoc/09）

在同一批 200 条任务上对比两种 few-shot 装配：11 版 90/200、三条版 85/200。每条失败任务只归一个主因后，两版最大的失败原因都是「选错/漏做目标设备」（条件级复核 63 次 vs 63 次，属于 1.5B 的能力瓶颈）；三条版真正的退化在 T4——「拒绝理由码抄工具错误码」从 11 条涨到 27 条，原因是模型把 inspect 到的参数 schema 当成参数值传给设备，被 B 拒后又拿工具错误码当拒绝理由。

### 2.3 数据合成文档（newdoc/10、11）

10 号文档按十个阶段（D0、D1、D2-1、D2-2、D3、D4、停闸、D5、D6、进数据集）把真实管线讲了一遍，并列出 17/18 之后 12 处最终生效的差异：户型 9→15、画像 20→25、设备 15→21、主灯两档、加湿器去档位、observe_home 瘦身、T5 空观察、ge/le 相对初值、C-2 不冻整屋、A system 一次、提示词按 T 拆五份、配额跑法。11 号文档逐个模块写「职责自然语言 + 输入输出 + 边界 + 例子」，并附一题全链路（sc_T2_006）和错误码总表。

### 2.4 新模型评测（newdoc/12）

```text
模型           T1     T2     T3     T4     T5      总      用时
Qwen3.5-2B     38     19      9     15     31     112/200  302.7s
Qwen2.5-1.5B   28      7      6     17     32      90/200   —
Qwen3-1.7B     22      2      4     21     14      63/200  201.8s
```

两次运行都没有报错。Qwen3.5-2B 的增益集中在 T1/T2，弱点仍是 T3/T4；Qwen3-1.7B 总分低但 T4 最好，主要问题是收尾契约（C-4）。评估时统一关思考（`-rea off`，实测响应无 `reasoning_content`），few-shot 统一用当前 11 版，所以可直接和 newdoc/09 的 90/200 对比。

### 2.5 仓库管理

`.gitignore` 补了模型/缓存规则（`*.bin`、`*.h5`、`*.npz`、`**/venv/`、`**/.cache/` 等）；`source.md` §3 登记了本机 1.5B、Qwen3-0.6B、Qwen3-1.7B、Qwen3.5-2B 四个权重（含 SHA-256），§1 补了本机 Windows 布局（`D:\homeflow\autodl-tmp` ↔ `/root/autodl-tmp`，外部目录 `D:\D_program`）。相关提交：`114484a`、`5b14cd4`。

## 3 日志与产物位置

每个评测批次目录都完整落盘，结构一致：

```text
new_demo/runs/<批次>/
  results.jsonl        每条任务的 labels(C-1..C-4)、turn_count、finish、elapsed_sec
  trajectories.jsonl   完整轨迹（scenario + record 五项 + labels）
  summary.json         总数、c_all_pass、errors、用时、workers、max_turns、model、few_shot
  local_model.env      指向本地服务的配置（base_url / model，不含密钥）
  api/completions.jsonl 每一次模型调用的请求记录（request_id、role、usage、正文）
  api/errors.jsonl     只有出错时才有
```

```text
本机关键批次
  quota50_20261002_v2                最新数据合成批次（302 蓝图 / 302 轨迹 / 250 进集）
  qwen15b_eval_100_fs_by_task        1.5B 11 版 A 批（100 条）
  qwen15b_eval_100b_fs               1.5B 11 版 B 批（100 条）
  qwen15b_eval_100_fs_by_task3       1.5B 三条版 A 批
  qwen15b_eval_100b_fs3              1.5B 三条版 B 批
  qwen3_17b_eval_200_fs              Qwen3-1.7B 200 条（本次新增）
  qwen35_2b_eval_200_fs              Qwen3.5-2B 200 条（本次新增）
```

注意两点：`new_demo/runs/` 和 `context/` 都不进 git；llama-server 的 stdout 这次没有单独落盘（服务日志只在运行时可见），每次模型调用的内容在 `api/completions.jsonl` 里，下次起服务可以加 `--log-file` 把服务侧日志也存下来。

## 4 新模型评测复现

```text
服务（模型二选一，端口 18080；2 slot × 16K；关思考；不加载多模态投影）
  llama-server.exe -m <gguf> --host 127.0.0.1 --port 18080 ^
    -c 32768 --parallel 2 -ngl 99 --no-mmproj -rea off --jinja

评测（200 条 = _eval100_ids.txt + _eval100b_ids.txt 合并成逗号串）
  python new_demo/eval_sets/quota50_20261002_v2/run_local_eval.py ^
    --server http://127.0.0.1:18080 --model <name> ^
    --output-dir new_demo/runs/<批次名> --workers 2 --max-turns 12 ^
    --few-shot --task-ids "<200 个 id>"

模型来源（hf-mirror，直连 HF CDN 不通）
  ggml-org/Qwen3-1.7B-GGUF   Qwen3-1.7B-Q8_0.gguf
  unsloth/Qwen3.5-2B-GGUF    Qwen3.5-2B-Q8_0.gguf
```

## 5 风险与下一步

```text
1  不要拿 context5 的旧数字当最新：x5x10 的 43/50、进集 41 是 10-01 的状态，
   现在的数据基准是 quota50_20261002_v2 的 250 条进集。

2  主提示词 new_demo/data_static/D0_templates/ 不要擅自改；
   改动走 newdoc/02 的审阅流程，落盘后跑 pytest。

3  Qwen3.5-2B 的 T3（9/40）和 T4（15/40）仍是弱项；
   Qwen3-1.7B 的 C-4 问题（119/137）适合单独做失败归因。

4  如果要做「模型 × 装配」2×2：把 fa872cf 的三条版恢复到
   fewshot_by_task_3shot/，用 --few-shot-dir 指过去再跑 200 条，
   不要覆盖当前 11 版目录。
```
