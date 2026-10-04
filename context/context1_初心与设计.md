# HomeFlow Demo：初心与设计（合并自 context1–5，精简版）

> 用途：新对话恢复项目的「为什么做、怎么做、边界在哪」。
> 整理日期：2026-10-04。原 context1–5 已删除，结论都收在本文与 context2_演进与现状.md。
> 工作区：服务器 `/root/autodl-tmp`；本机 `D:\homeflow\autodl-tmp`（同一套仓库）。

## 0 一句话初心

从 SMH-Bench、HomeFlow、SimuHome 里提炼一条**可验证、可重放、能支撑 SFT 与 LoRA-GRPO 的最小智能家居闭环**，不逐字段复刻论文：

```text
程序造出家庭状态与隐藏任务
  -> 模型（或 Oracle）用四个家庭工具与 HomeEnv 交互
  -> C 管回合、执行工具、读隐藏任务判对错
  -> 得到可审计的成功轨迹（蓝图 + 用户话 + 轨迹）
  -> SFT 1.5B
  -> 再用环境 reward 做 LoRA-GRPO
```

当前交付到「数据集」为止；SFT / LoRA-GRPO 还没开始。

## 1 研究问题

```text
在一个轻量、符号状态、确定性反馈的智能家居环境里，SFT 过的 1.5B 模型能否学会：
  发现房间与设备、读公开能力、按参数边界执行
  完成多设备目标、理解模糊意图
  拒绝越界与只读写入
  在有限轮内正确结束（finish 契约）
并在环境 reward 下继续提升？
```

## 2 设计原则（为什么这样搭）

```text
符号状态 + 确定性反馈
  可验证、可复现、reward 可算、失败可归因；不追求连续物理仿真。

一次 assistant 输出 = 一个 turn = 一条策略 step
  turn 内的工具执行记成 tool events；不能让一次 completion 事后被拆成多步。

发现链是信息需求，不是闸门
  observe_home 不给 device_id，所以模型必须 inspect_room / inspect_device；
  但 B 不强制顺序，未知 id 才报错。

隐藏真值与可见信息分离
  Scenario.task 只有 C 评测时读；A（轨迹里的助手）永远看不见。

真值程序造，自然语言模型写
  户型、设备、画像、任务模板放 D0 数据文件；外部模型写 task JSON 与一句用户话。
  画像只借口吻，不进任何判定；不许写本轮 s0 里没有的房间/设备/传感器。

分层交付、小步验证
  环境 -> Oracle -> 数据管线 -> 数据集 -> SFT -> RL；
  每层先小规模 smoke 再放大；失败必须留痕，不允许静默丢样本。
```

## 3 模块与角色

```text
A  外部交互：给定 context 产生一次 assistant 响应；不直接改环境
B  HomeEnv：房间/设备/状态/四个家庭工具；不读 task、不处理 finish、不判成功
C  回合与评测：唯一入口 run(scenario)；驱动 A 与 B，读隐藏 task 打 C-1..C-4
D  数据管线：D0 静态库 -> D1 抽家 -> D2 写 task/用户话 -> D3 审话 -> D4 Oracle 验蓝图
   -> 停闸 -> D5 跑轨迹 -> D6 复核 -> 复制数据集
E  SFT（未开始）      F  LoRA-GRPO（未开始）
```

```text
谁是 A：只有 D5 里 C.run 调用的 policy.respond。
D2 / D3 / D6 都是 role=external 的外部模型，不是 A；请求体一律不带 max_tokens。
```

## 4 关键取舍与教训（早期版本沉淀下来的）

```text
1  writer_view 教训
   旧 V2 把任务语义写死在 Python，模型只把一句现成中文改写一遍：
   数据不可控、失败难归因（20 条 smoke 只有 2 条 clean_success）。
   结论：语义结构由程序定义，task 与用户话都由外部模型写。

2  finish 契约必须唯一
   公开 tool schema、C 的校验、expected_finish、提示词必须是同一套；
   否则会出现「动作做对了但 finish 缺 outcome 判失败」。
   最终契约：summary 必填；outcome 只许 completed / refused；refused 加 reason_code；
   不要 facts / answered。

3  方向题相对初值
   ge/le 不设数字门槛：终态比 s0 初值严格更高/更低即算；
   写 task 时 value 填 s0 当前值；D4 用「挪一档」验证。

4  画像仅供参考
   画像只影响 intent 口吻；没有厨房的家不许写洗碗机。

5  B 不做接地检查、不存户型库
   只认已经配对好的 home；房间与设备 id 双向校验；
   D4 复制 s0 用副本真打 B，靠报错判断蓝图可行性。

6  失败必须留痕
   D2/D3/D4 失败进 D34_failures；轨迹失败留在总表；标签全过才复制进数据集。
```

## 5 训练侧定位（简）

```text
训练尚未开始。稳妥路线：
  数据（现状）-> doc/21 把轨迹转成 SFT 消息 -> 1.5B SFT -> 环境 reward 的 LoRA-GRPO
框架倾向：Transformers + TRL + PEFT（科研可读性）；MiniMind 只做机制练习。
本机现状：RTX 5060 Laptop 8GB（早期文档按 4090/5090 评估，资源结论已过时）；
  1.5B LoRA 需要把序列长度压到 2048–4096。
```

## 6 十条记住

```text
1  目标是「可验证的轨迹数据」，不是复刻论文。
2  代码在 new_demo/，homeflow_demo/ 只读参考。
3  A 只做下一步；B 只执行；C 管回合与判分；D 造数据。
4  四个家庭工具 + finish（finish 由 C 收）。
5  隐藏 task 不进 A 的视野。
6  finish = summary + outcome(+reason_code)。
7  ge/le 相对 s0 初值；keep 只许 eq。
8  画像仅供参考，题面只落在本轮 s0 上。
9  失败留总表，标签全过才进数据集。
10 每轮改动：跑测试 -> 小批验证 -> 再规模化。
```
