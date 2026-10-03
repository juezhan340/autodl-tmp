# HomeFlow Demo 项目上下文（五）

> 文档用途：接 [context4.md](/root/autodl-tmp/context/context4.md)。供新对话恢复 2026-09-30 至 2026-10-01。
> 梳理日期：2026-10-01。
> 工作区：`/root/autodl-tmp`。
> 代码根：`/root/autodl-tmp/new_demo/`。
> 现行规格：[doc/28_第一版最终调整方案.md](/root/autodl-tmp/doc/28_第一版最终调整方案.md) 已落地；T2 D2-1 在 28 之后又按原则稿重写。

## 0. 现在停在哪

context4 写到：管线能从抽 s0 跑到数据集，最近一次是 `x5_blueprint_v3`，蓝图 22/25、进集 15，T3 四条全挂在加湿器档位。那之后做了两刀：先按 28 改 C-2 / 加湿器 / T4 / A 多轮拼法 / D2 画像口径，再单独把 T2 的 D2-1 改成「原则 + 小例子 + 大例子」。

**当前进度：整条 D0–D6 可用。最近一次是 5×10、50 路并发 `--full`，蓝图 43/50，进集 41。T3 已经能进集。卡点从「加湿器档位 vs 开关」挪到范围题步长、D3 过严、T2 偶发清单又肥。还没开 SFT。**

```text
最近一次
  目录    new_demo/runs/x5x10_20261001/
  种子    20261001
  并发    50 路 --full
  尝试    50（五类各 10）
  蓝图    43 / 50     T1 10  T2 7  T3 8  T4 8  T5 10
  进集    41 / 43     T1 9/10  T2 7/7  T3 7/8  T4 8/8  T5 10/10
  D6      对 25（T3+T4+T5）  跳过 16（T1+T2）

未出蓝图 7（全是 D3，草稿在 D2_drafts.jsonl / D34_failures.jsonl）
  T2 ×3   intent 设备集又肥：多写加湿器/走廊灯；keep「别太低」对不上 eq
  T3 ×2   话里闷+黏，hidden 关加湿器，D3 按闷要空调
  T4 ×2   点了没有的书房；闲话「翻翻材料」被 EXTRA_INTENT

轨迹掉 2（蓝图过了，C-2 挂，不进数据集）
  T1 sc_004  「调高一点」，hidden ge 22，A 把 15 调到 17
  T3 sc_019  「闷得发燥」，hidden le 26，A 开机制冷，target 仍 27
```

失败全文（5×5 五条 + 5×10 九条）：[x5_20260930_t2_失败.md](/root/autodl-tmp/new_demo/reports/x5_20260930_t2_失败.md)。
5×10 总表：[x5x10_20261001.md](/root/autodl-tmp/new_demo/reports/x5x10_20261001.md)。
数据集：[D_dataset.jsonl](/root/autodl-tmp/new_demo/runs/x5x10_20261001/data_processed/D_dataset.jsonl)。

画像是每条 job `rng.choice`，本轮 50 条草稿用了 23 个不同 persona_id，有重复、不是同一张画像打完全场。

## 1. 新对话先读什么

```text
必读（现行口径）
  context/context5.md                         本文，看停点
  doc/28_第一版最终调整方案.md                 五条总调整，已落地
  doc/27_二十五条画像与三类提示词.md          25 条画像 + D2-1/D2-2/D3/D6 正文
                                              T2 D2-1 以这里的原则稿为准
  new_demo/data_static/D0_templates/          磁盘提示词，运行时读这里
  new_demo/reports/x5_20260930_t2_失败.md     最近失败

设计底稿（对照用，不要当待办）
  doc/17_架构大幅度改动.md
  doc/18_D0到D6详细设计.md
  doc/26_闭区间主灯两档与任务指令配对.md      灯两档、闭区间、配对仍有效
                                              其中「拒绝任务整屋冻结」已作废

交互拼法
  assitdoc/05_A上下文最简模式.md
  assitdoc/06_A通用开头提示词.md              与 D0_templates/A_policy.md 同步

不要当现行口径
  context1 / context2 / context3 的「代码未写」
  context4 的「T3 0/4、加湿器 level、C-2 冻整屋」
  doc/19 旧提示词、doc/14–16 旧 V2 writer_view
  旧 A_policy 每回合整份 user
  不要按 16 把 finish.outcome 改成 status
  不要在 homeflow_demo 上打补丁
```

## 2. 从论文到现在（只留主线）

初心对齐 SMH-Bench / HomeFlow：用模拟家生成可打分的工具调用轨迹，后面拿去 SFT 1.5B。不是逐字段复现论文。旧 V2 把语义写死在 Python，模型只改写一句中文，根因是 `writer_view` 和 finish 契约。

新管线让外部 DeepSeek 先写隐藏 task，再写用户话；A 只在 D5 里当助手。今天交付物仍是蓝图、轨迹、数据集，不是训练。

```text
D0  库：15 户型、21 条设备目录、25 条画像、按 T 分好的提示词
D1  程序抽 s0，不调模型
D2  第一次写 task JSON；第二次写 user_request
D3  程序硬泄露 + 外部 DeepSeek 审指令
D4  Oracle 复制 s0 打 B；T4 另打 probe 必须失败
      过 → D4_blueprints.jsonl 发 bp_*
      不过 → 失败表，不发号
D5  另发 sc_*，C.run；五项回合记录 + C-1..C-4
D6  只审 C 全过的 T3/T4/T5，三局两胜；T1/T2 标「跳过」
      标签全过 → 复制进 D_dataset.jsonl

PIPE 默认停 D4；--full 一次跑完；--continue-from-d5 只跑后半段
谁是 A：只有 D5 里 policy.respond。D2、D3、D6 都是 role=external
请求体不准带 max_tokens
```

## 3. 28 落地了什么，以及 28 之后又改了什么

28 的五条已经进代码和 `D0_templates`：

```text
1  C-2     只认 conditions ∪ keep，空数组过
           不再做整屋 unchanged
           sc_017 那种 clamp 再 refused，不再被 C-2 罚

2  加湿器  只有 on；动作只有 turn_on / turn_off
           T3 干=打开，潮=关掉
           禁止拿加湿器打数值越界 T4
           对加湿器 set_percentage → UNSUPPORTED_ACTION

3  T4 提示词  讲题意，不写禁词闭集
           危险在做不到的具体目标里，字面像普通控制

4  A 上下文  第一轮 system + 用户话
           之后只 append assistant JSON 和 observation:
           每条轨迹单独一份 DeepSeekPolicy
           （50 路并发不能共用 messages）

5  D2-1    画像仅供参考，题面跟本轮 s0
           不要写本轮没有的房间、传感器、家具
   D2-2    必要信息必须在，可加闲话
   D3      带上 {{rooms}} / {{display_names}}
```

28 落地后立刻跑了 `x5_20260930_v28`：T3 5/5 进集，T2 蓝图只 1/5（intent 设备集肥）。所以又重写了 T2 的 D2-1，覆盖 [T2_multi_control.md](/root/autodl-tmp/new_demo/data_static/D0_templates/T2_multi_control.md) 和 27 文档同一节：

```text
原则    intent 设备 = conditions 设备 ∪ keep 那一台，不多不少
        画像只借口吻
        没有的房间和设备不要写
小例子  电视关掉 + 空调调低 + 冰箱别动
错例    intent 多了主灯；keep 是冰箱却写灯别动；没有书房却写书房台灯
大例子  完整 s0 + JSON
```

原则稿后再跑 `x5_20260930_t2`：T2 五条都出蓝图。5×10 里 T2 出了蓝图的 7 条轨迹全部进集。清单对齐了，剩下的 T2 失败回到 D3 偶发回潮。

## 4. 现行硬约束

已经落在 `env/`、`eval/`、`D0_templates/`，改口径先改这里，不要只改提示词或只改评测。

```text
C 入口只有 run(scenario)
B.step 的 name 闭集 4 个
  observe_home / inspect_room / inspect_device / execute_action
finish 由 C 收，不是 B 的 name
每轮最多 1 个工具；max_turns=10

observe_home 只回 [{room_id, display_name}]
  不回温湿度、不回设备、不回台数
  找设备必须 inspect_room；读数/调参必须 inspect_device

动作
  模式走 set_mode.mode
  连续量走 set_percentage.value 或 set_temperature.value
  不要 set_brightness / set_volume
  主灯   on + mode dim|bright，无 level
  台灯   on + level 0–100
  夜灯廊灯厨灯浴灯阳台灯  只有 on
  风扇/电视音量           set_percentage
  加湿器                  只有 on

检验
  ge / le 是闭区间（大于等于 / 小于等于）
  keep 只许 eq
  T1/T2/T3/T5 required_observations=[]
  T4 keep=[]，probe 只给 D4，A 看不见

finish
  summary + outcome；refused 再加 reason_code
  不要 facts，不要 answered

DeepSeek 不带 max_tokens
户型 15（大中小各 5），设备目录 21，画像 25（p01–p25）
```

设备目录现在是这 21 条（[D0_devices.jsonl](/root/autodl-tmp/new_demo/data_static/D0_devices.jsonl)）：

```text
灯 7     主灯(dim/bright) 台灯(%) 廊灯 阳台灯 厨灯 浴灯 夜灯
气候     空调  风扇  排气扇  墙开
传感 3   温湿度  温度  湿度     都是只读
家电     电视  热水器  洗衣机  洗碗机  烤箱  冰箱  加湿器(仅开关)
```

## 5. 代码和提示词在哪

```text
new_demo/
  PIPE_run.py                 --per-category --workers --seed --full --continue-from-d5
  .env.deepseek               API key 已填
  data/                       D0–D6、PIPE、D_copy_dataset
  env/                        B；加湿器 ALLOWED_STATE 只有 on
  eval/                       C_episode_runner / C_episode_evaluator
                              C-2 只认 conditions 与 keep
  agents/                     DeepSeekPolicy 持有本场 messages
  data_static/
    D0_homes.jsonl            15 户型
    D0_devices.jsonl          21 目录
    D0_personas.jsonl         25 画像
    D0_templates/             运行时提示词（以这里为准，与 27 同步）
  runs/x5x10_20261001/        最近 5×10
  tests/                      80 collected（28 落地时 80 passed）
```

提示词运行时只做占位符替换，T1–T5 的第三节已经按任务族装配好，不要运行时再拼第三四节。

重跑（写到新目录，不要覆盖旧批次）：

```text
python -m new_demo.PIPE_run --output-dir new_demo/runs/<run> \
  --per-category 10 --workers 50 --seed <seed> --full
```

50 路是 I/O 并发，本机撑得住。DeepSeek 不限 token。

## 6. 实验怎么读

```text
x5_blueprint_v3        28 前。蓝图 22/25，进集 15。T3 0/4（档位 vs 开关）
x5_20260930_v28        28 后 5×5。蓝图 20/25，进集 19。T3 5/5；T2 蓝图 1/5
x5_20260930_t2         T2 原则稿。蓝图 23/25，进集 20。T2 蓝图 5/5，进集 3/5
                       掉的是 ge 步长和 10 轮写三台没 finish
x5x10_20261001         5×10 50 并发。蓝图 43/50，进集 41
                       T5 10/10；T2 出蓝图的 7 条轨迹全进
```

读失败时先看 `stage`：D2 / D3 / D4 是没出蓝图；D5 的 C-1..C-4 是轨迹掉。C 全过且 D6 对或跳过才进数据集。失败留总表，不要删。

旧 jsonl 里加湿器还带 `level` 的，不能再 `B.reset`。

## 7. 还没关的洞

这些是最近两轮重复出现的，不是单条噪声。

```text
范围题步长（最显眼）
  用户话「调高一点 / 调低一点」，hidden 是 ge 22、ge 26、le 26
  A 只 +2 或只切制冷不改 target
  出现在 t2 的 sc_005/sc_007，和 5×10 的 sc_004/sc_019
  蓝图和用户话是对齐的，掉在 A 看不见 hidden 数值

T3 D3 闷+黏
  潮→关加湿器方向对
  话里同时有「闷」，D3 按热要空调，TARGET_NOT_COVERED
  5×10 两条蓝图都死在这里

T2 D3 清单偶发回潮
  原则稿后 5×5 的 T2 五条都过了
  5×10 又有 3/10 把画像家具写进 intent（加湿器、走廊灯）
  keep 写成「别太低」也对不上 eq
  可以考虑 D2 之后程序核对 intent 设备集 = conditions ∪ keep

T4 D3
  闲话「翻翻材料」被 EXTRA_INTENT（28 说闲话该放过）
  没有的书房仍会写进 T4 话里（D2-1 弱化画像还没完全管住）

T3 D2 already holds
  方向对，但 s0 已经落在闭区间里，程序拦住
  5×5 t2 两条；5×10 没再出现，还在

T2 10 轮
  三台各 inspect+写入刚好用完 10 步，没喊 finish
  t2 的 sc_006；5×10 没再出现
```

## 8. 新对话接着做什么

用户若没另开口，优先范围题和 D3 过严。不要再扩设备、不要开 SFT。

```text
可做
  ge/le 的 A：用户说「调高一点」，要落到闭区间，不能只加两度
              这是助手策略 / A 提示词问题，不是 hidden 写错
  T3 D3：闷+黏不要只按热拒关加湿器
  T4 D3：闲话放过
  T2：清单偶发回潮，看要不要程序核对 intent 设备集

不要主动做
  开 SFT
  给 observe_home 加回温湿度或设备台数
  把 ge/le 改回开区间
  恢复加湿器档位
  拒绝任务再冻整屋
  扩一堆新电器
  git reset --hard、改 homeflow_demo
```

## 9. 记住的事实

```text
1. 代码在 new_demo/，提示词以 D0_templates 为准，27/28 是给人看的规格。
2. 今天停在 5×10 进集 41 条。T3 已通；T2 蓝图过了的轨迹稳。
3. C-2 不冻整屋。A 是多轮 messages，不是每回合一张考卷。
4. 失败留总表。C 全过且 D6 对/跳过才进数据集。
5. 每条 job 独立抽画像和户型，不是固定一张打完全场。
6. 旧 jsonl 里加湿器带 level 的，不能再 B.reset。
```
