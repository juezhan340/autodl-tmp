# HomeFlow Demo 项目上下文（三）

> 文档用途：接 [context2.md](/root/autodl-tmp/context/context2.md)。供新对话恢复 2026-09-27 至 2026-09-28 这一轮。
> 梳理日期：2026-09-28。
> 工作区：`/root/autodl-tmp`。
> 这一轮仍只改文档。没有写 `new_demo/` 新代码，也没有改 `homeflow_demo/`。

## 0. 现在停在哪

context2 写到：当前任务是改 17，不是冻 finish。17 当时还是「目标规格」，代码仍是 V1.2 写死户型加 V2 `writer_view` 改写。

这一轮把 17 收成三节，并另写了新代码的详细设计 18。**进度是设计已对齐到 D6 数据集，实现还没开工。**

```text
已完成（文档）
  17  目标规格，三节已按调用链和两步打分改完
  18  新包 new_demo/ 的 D0–D6 详细设计（不是给旧 demo 打补丁）
  19  D0 前三类提示词审阅稿：20 条画像、T1–T5、用户指令
  21  回合记录如何改成 SFT/RL（今天不做训练）

未做
  还没有 /root/autodl-tmp/new_demo/ 这棵新树
  没有按 17/18 改 homeflow_demo
  D6 提示词正文还没写（等 19 审过）
  D3 审指令提示词正文还没单独成稿
  SFT / LoRA-GRPO 未开始
```

## 1. 新对话先读什么

```text
context/context3.md          先读本文，看进度
doc/17_架构大幅度改动.md     目标规格，口径以磁盘为准
doc/18_D0到D6详细设计.md     新代码怎么拆文件、每个模块干什么
doc/19_D0前三类提示词.md     画像和 T1–T5 / 用户指令，待用户审
doc/21_回合记录如何变成SFT与RL训练数据.md   轨迹改形状，今天不实现

context1.md / context2.md    背景。V1.2 能跑、V2 smoke 2/20 的事实仍有效
doc/14、doc/15               旧 V2 方案和 20 条 smoke，用来理解为什么推翻 writer_view

不要读、不要当现行口径
  已删除的旧 18 接地检查、旧 19 的 change/keep/query/refusal、旧 20 的 SimuHome 五例
  不要按 16 去改 finish 的 status 字段名
  不要在 homeflow_demo 上打补丁实现 17
```

17 现在的三节：

```text
1. 要改的数据管线          画到 D6，今天停在数据集
2. D5-C-A-B 的交互过程    C 只有 run 一个启动入口
3. D4-D6 的详细设计       第一步审蓝图，第二步审轨迹
```

## 2. 这一轮定下来的结构

根因仍是：语义写死在 Python，模型只改写一句现成中文。新管线让 DeepSeek 先写 task JSON，再写用户话。

```text
D0 库（homes、20 条画像、提示词文件）
        |
        v
D1 抽 s0（程序，不调模型）
        |
        v
D2 第一次  外部 DeepSeek 写 task（不是 A，不限 token）
D2 第二次  外部 DeepSeek 写 user_request（不是 A，不限 token）
        |
        v
未编号草稿 <s0, task, request>；T4 另带 probe
        |
        v
D3 审指令（程序泄露 + 外部 DeepSeek）
D4 Oracle 复制 s0 打 B，只看 ok/error.code
        |
        +-- 不过：D34_failures.jsonl，不发 blueprint_id
        +-- 都过：D4_blueprints.jsonl，发 bp_*
                    |
                    v
                  D5 另发 sc_*，编 Scenario，C.run
                    五项回合记录进 D5_trajectories.jsonl
                    打 C-1..C-4；失败也留，不删
                    |
                    v
                  D6 只审 C 全过的 T3/T4/T5
                    外部 DeepSeek，只输出对/错，三局两胜
                    写回同一条 sc_*
                    T1/T2 的 D6 标签=跳过
                    |
                    v
                  标签全过 -> 复制进 D_dataset.jsonl
今天停在这里。不做 SFT。
```

两步打分：D3+D4 是蓝图资格；C 四步 + D6 是助手轨迹。

## 3. 接口口径（实现时按这个）

```text
C 启动入口只有 1 个：run(scenario)

C 调用 B 的模块口
  1. reset  2. step  3. observation  4. runtime_state
这次不用
  5. events  6. snapshot  7. restore  8. fork

step 的 ToolCall.name 闭集 4 个
  observe_home / inspect_room / inspect_device / execute_action
  finish 由 C 留下，不是 B 的 name
  每轮最多 1 个工具

Scenario 六项
  scenario_id、blueprint_id、home、user_request、task、episode_config
  scenario_id ≠ blueprint_id
  user_request 顶层，不塞进 task
  max_turns=10，max_tool_calls_per_turn=1

C 输出五项回合记录（不含对错）+ 另附 C-1..C-4
  events 必须是完整工具回执；17 第二节 JSON 前三轮的 {"ok":true} 只是示意缩写

谁是 A
  只有 D5 里 C.run 的 policy.respond
  D2、D3、D6 都是外部 DeepSeek，不限 token、不截断
```

公开 finish：`summary` + `outcome`；refused 再加 `reason_code`。不要 answered，不要 facts。字段名仍是 `outcome`，不要改成 16 的 `status`。

T4 的 probe 只活在草稿里，不进蓝图文件，不进 Scenario。category 进蓝图和轨迹总表，不进 C 循环。T4 的 required_observations 含被拒绝的那台设备。

## 4. 新代码根，不补旧树

用户已重申：这一回重写一套代码，可借鉴 V1.2，不在 `homeflow_demo` 上打补丁。

```text
新代码根    /root/autodl-tmp/new_demo/     尚未创建
旧 demo     /root/autodl-tmp/homeflow_demo/  只读参考
文件名前缀  D0_homes.jsonl、B_home_env.py、C_episode_runner.py、A_policy.py
```

18 里的模块、输入输出、对应文件以 18 为准。17 管口径，18 管落地文件。

## 5. 提示词进度

```text
已有审阅稿（doc/19）
  20 条画像：occupation 已加；habits 含环境偏好，无 env_pref
  T1–T5：先说干什么，再给完整「画像+s0→task」例子，再给本轮 {{persona}}/{{s0}}
  角色句：你是数据辅助生成器
  用户指令模板：按 task+intent 写一句中文

未写
  D0_templates/D3_review.md
  D0_templates/D6_T3.md、D6_T4.md、D6_T5.md
```

T1–T5 和用户指令还在等用户审。不要在没说改代码时去建 `new_demo/`。

## 6. 旧 V2 还需要记得的事实

```text
V1.2：18 项测试、140 条场景和轨迹重放通过。环境能跑。
V2 20 条 smoke：2 条 clean_success。进环境的 16 条里 14 条死在 finish 契约。
公开 schema 当时只有 summary。Policy 80 次里 length 仅 1 次；Judge 30 次里 29 次截断。
4 条 Blueprint 在 TaskReviewer 阶段静默消失。
这些用来理解为什么推翻 writer_view、为什么 D6 不限 token、为什么失败要留在总表。
不要把 2/20 当成模型能力。
```

## 7. 新对话不要做的事

```text
不要改 homeflow_demo 里的旧模块来「实现 17」
不要 git reset --hard
不要按已删除的旧 18 去做 check_grounding
不要把 D2/D3/D6 当成 A
不要把 seed 当作 scenario_id 或 s0 编号
不要让 D5 模块去调 D6
不要开始 SFT，除非用户明确说做
没让写代码就不要创建 new_demo/ 目录
```

## 8. 新对话要记住的事实

```text
1. 当前进度：17/18 设计对齐到 D6 数据集；代码未写。
2. 实现时新建 new_demo/，旧 demo 只参考。
3. 今天的交付物是蓝图-轨迹-数据集，不是 SFT。
4. 提示词：19 待审；D3/D6 提示词未写。
5. C 只有 run；B 的 step 内部路由四个家庭工具；finish 归 C。
6. 轨迹总表全留，标签全过再复制进数据集。
```
