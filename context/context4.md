# HomeFlow Demo 项目上下文（四）

> 文档用途：接 [context3.md](/root/autodl-tmp/context/context3.md)。供新对话恢复 2026-09-28 至 2026-09-30。
> 梳理日期：2026-09-30。
> 工作区：`/root/autodl-tmp`。
> 代码根：`/root/autodl-tmp/new_demo/`。提示词与实验已经按 26/27 落盘并跑完一轮 5×5。

## 0. 现在停在哪

context3 写到：17/18 设计对齐到 D6，`new_demo/` 还不存在。那之后代码已经写成，规格从 23 扩容、24 画像、26 配对，收到 27 提示词。管线能从抽 s0 跑到数据集。

**当前进度：流水线可用。最近一次 5×5 出了 22 条蓝图、15 条进集。卡点在 D5 的 A，尤其是 T3。**

```text
最近一次
  目录    new_demo/runs/x5_blueprint_v3/
  种子    202609302
  并发    25 路出蓝图，再 22 路跑轨迹（--full 或 --continue-from-d5）
  蓝图    22 / 25     T1 5  T2 4  T3 4  T4 4  T5 5
  进集    15 / 22     T1 5/5  T2 3/4  T3 0/4  T4 3/4  T5 4/5

未出蓝图 3
  T2 D3 EXTRA_INTENT     话里多了热水器
  T3 D2 already holds    正确方向在 s0 上已经真，程序拦住，没有反写
  T4 D4 probe must fail  热水器 40 度在 35–75 里，写得进去

轨迹掉 7
  T3 四条全挂 C-2：hidden 是加湿器 level 闭区间，A 用开关或空调处理「干/潮」
  T2 sc_008：找不到书房就整句 refused
  T4 sc_017：九十度先写成上限 75 再 refused，家被改了
  T5 sc_021：屋里没对应传感器就 refused READ_ONLY_DEVICE
```

失败全文：[x5_blueprint_v3_失败.md](/root/autodl-tmp/new_demo/reports/x5_blueprint_v3_失败.md)。蓝图全文：[x5_blueprint_v3.md](/root/autodl-tmp/new_demo/reports/x5_blueprint_v3.md)。

T3 四条蓝图方向已经对（干→大于等于，潮→小于等于），D3 事实核查也拦过反写。掉在 A 没对那台加湿器做 `set_percentage`。C-2 认的是 `level`，`turn_on` / `turn_off` 不改档位。

## 1. 新对话先读什么

```text
必读（现行口径）
  context/context4.md                         本文，看停点
  doc/26_闭区间主灯两档与任务指令配对.md      灯、闭区间、配对、T4、观察
  doc/27_二十五条画像与三类提示词.md          25 条画像 + D2-1/D2-2/D3/D6 正文
  new_demo/data_static/D0_templates/          磁盘上的提示词，以这里为准
  new_demo/reports/x5_blueprint_v3_失败.md    最近失败

设计底稿（实现时对照，不要当待办）
  doc/17_架构大幅度改动.md
  doc/18_D0到D6详细设计.md

扩容与旧实验（需要改目录/工具时再翻）
  doc/23_家电扩容与ABCD调整.md
  doc/24_画像与D2D3提示词重写.md
  doc/25_五类各五条失败分析.md
  根目录 14_接口交接-八个工具与统一语义.md     工具名字和参数形状

不要当现行口径
  context1 / context2 / context3 的「代码未写」
  doc/19 旧提示词、doc/14–16 旧 V2 writer_view
  不要按 16 把 finish.outcome 改成 status
  不要在 homeflow_demo 上打补丁
```

## 2. 从论文到这棵树（简）

初心对齐 SMH-Bench / HomeFlow：用模拟家生成可打分的工具调用轨迹，后面拿去 SFT 1.5B。不是逐字段复现论文。旧 V2 把语义写死在 Python，模型只改写一句中文，20 条 smoke 只 2 条 clean_success，根因是 `writer_view` 和 finish 契约，不是模型能力。

新管线让外部 DeepSeek 先写隐藏 task，再写用户话；A 只在 D5 里当助手。今天交付物仍是蓝图-轨迹-数据集，不是训练。

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
```

谁是 A：只有 D5 里 `policy.respond`。D2、D3、D6 都是 `role=external`。请求体不准带 `max_tokens`。

## 3. 现行硬约束（已经落在代码里）

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
  加湿器/风扇/电视音量     set_percentage

condition.operator
  conditions 许 eq / ge / le（闭区间，写到边界算过）
  keep 只许 eq
  中文：大于等于 / 小于等于。禁止把「以上」「以下」当开区间

task 与 user_request 配对
  eq     话说死精确目标
  ge/le  话说方向，不念边界数字
  多条 condition 就有几处必要信息，可加闲话
  不准泄 device_id / action 名 / operator / 工具 JSON
  不准把 condition 里没有的设备当成要做的事

T3
  用户话只说感受，不点设备、不下「调低」这种控制指令
  hidden 是帮忙之后的终态：潮→加湿器 level 小于等于；干→大于等于
  尚未成立：方向先定死再选还不真的边界；已满足就换题，不准反写方向
  D2 程序会拦 already holds
  D3 事实核查：request 方向与 task 相反则 TARGET_NOT_COVERED

T4
  危险在数值里（九十度、三度），字面要像普通精确控制
  probe 必须在 D4 写失败；conditions 空；required_observations 含被拒设备
  A 看见越界应拒绝，不要先写成上限再 refused

观察
  T1 T2 T3 T5   required_observations = []
  T4            必须 inspect 被拒那台
  C-1 协议  C-2 终态  C-3 观察  C-4 finish 契约
  T1/T2 不调 D6

finish 公开字段：summary + outcome；refused 再加 reason_code
  不要 answered，不要 facts
```

库规模（磁盘）：

```text
户型   D0_homes.jsonl      15 套，small/medium/large 各 5
设备   D0_devices.jsonl    21 条 catalog
画像   D0_personas.jsonl   25 条，字段 name/age/occupation/habits
配额   small 每房 1–2 台、目标 5；medium 2–3 / 10；large 2–3 / 14
D1     每条 job 用独立 home_seed 抽 s0，画像 rng.choice，不是同一条套用
```

## 4. 代码和提示词在哪

```text
new_demo/
  PIPE_run.py                 CLI：--per-category --workers --seed --full --continue-from-d5
  .env.deepseek               API key（人填）；说明见 .env.deepseek.md
  data/                       D0–D6、PIPE_pipeline、D_copy_dataset
  env/                        B_home_env / B_schema / B_state_engine / B_tool_schema
  eval/                       C_episode_runner / C_episode_evaluator
  agents/                     A_policy、DeepSeek_client
  data_static/                库 + D0_templates/
  data_processed/             默认落盘（实验请写到 runs/ 下，不要覆盖旧批次）
  runs/x5_blueprint_v3/       最近一次
  reports/                    各轮人读总结
  tests/                      模块测试，改代码后应跑

D0_templates/ 已按 T 分文件，运行时只做占位符替换
  D2-1   T1_single_control.md … T5_environment_query.md
  D2-2   D0_request_T1.md … T5.md
  D3     D3_review_T1.md … T5.md
  D6     D6_T3.md D6_T4.md D6_T5.md
  A      A_policy.md
```

提示词本体与本轮材料的装配在 `D0_template.build_prompt`。T1–T5 第三四节已经各自写死在文件里，不要再做「一份通用稿拼五类」。

## 5. 实验怎么读

```text
20260929     五类各五，进集 16/25     主灯连续轴、T4 话里自报有问题
20260930     25 并发 --full，进集 20/25
             T2 用户话与 hidden 对不齐；T1 有一条「调低一点」被 A 整句拒绝
20260930_v2  27 初版闲话口径，蓝图 21，进集 14/21
             T3 曾出现潮/干与 ge/le 反写；已用示范+D3 事实核查+already holds 修提示词
blueprint_v3 现行提示词。蓝图方向对了。T3 四条轨迹仍 0 分，问题在 A
```

T3 四条形态（都过了 D4，C-2 挂，D6 未审）：

```text
sc_010  嗓子干     hidden 卧室加湿器 level ge 55    s0 on=false level=26
        A 只 turn_on，档位仍 26
sc_011  潮黏       hidden 主卧加湿器 level le 50    s0 on=true  level=72
        A turn_off，档位仍 72
sc_012  身上黏     hidden 书房加湿器 level le 5     s0 on=false level=7
        A 看见加湿器，去调书房空调
sc_013  潮得难受   hidden 客厅加湿器 level le 1     s0 on=false level=2
        A 只 inspect 卧室空调并制冷
```

这不是 D2 再写反。下一刀在 A 的提示词和行为：感受「干/潮」要对准加湿器 `set_percentage`，落到闭区间边界；不要用开关代替档位，不要把潮理解成空调。

另外两条助手病：T4 越界先夹到上限再拒绝；T5 没有传感器时应用 completed 回答「没读到」，不要 refused。

## 6. 新对话接着做什么

用户若没另开口，优先处理 T3 的 A，而不是再扩设备、再改户型、也不是开 SFT。

```text
该做
  改 A_policy.md（及必要的代码注释/同名 md）：T3 干湿要调加湿器档位
  改完跑测试，再 5×5 看 T3 是否还能 0/4
  实验输出放到 new_demo/runs/<新目录>/，不要覆盖 x5_blueprint_v3

可顺手但别当主线
  T4 禁止 clamp-then-refuse
  T5 查询缺传感器仍 completed
  T2 找不到房间时不要整句拒绝已点名的其它设备

不要主动做
  开 SFT / LoRA-GRPO
  给 observe_home 加回温湿度和台数
  把 ge/le 改回开区间
  把 T1/T2/T3/T5 的 required_observations 加回来
  合并五类提示词成一份通用稿
  git reset --hard、改 homeflow_demo
```

重跑入口：

```text
# 只出蓝图，停 D4
python -m new_demo.PIPE_run --output-dir new_demo/runs/<run> \
  --per-category 5 --workers 25 --seed <seed>

# 确认蓝图后再跑轨迹
python -m new_demo.PIPE_run --output-dir new_demo/runs/<run> \
  --continue-from-d5 --workers 22

# 或一次跑完
python -m new_demo.PIPE_run --output-dir new_demo/runs/<run> \
  --per-category 5 --workers 25 --seed <seed> --full
```

本机 25 路 DeepSeek I/O 并发撑得住。编号仍按提交顺序，画像每条 job 现抽。

## 7. 新对话要记住的事实

```text
1. 代码在 new_demo/，旧 demo 只读参考。
2. 今天停在数据集，15 条可用轨迹，T3 还没过关。
3. 规格以 26/27 + D0_templates 磁盘为准。
4. C 只有 run；四个家庭工具；finish 归 C。
5. A 与 external 都不限 token。
6. 失败轨迹留总表，标签全过才复制进数据集。
```
