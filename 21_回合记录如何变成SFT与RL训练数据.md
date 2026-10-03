# 回合记录如何变成 SFT 与 RL 训练数据

> 日期：2026-09-28
> 性质：对照说明。不改代码。
> 对照：`doc/17_架构大幅度改动.md` 第三节 C 的输出

C 导出的五项是审计记录：谁在哪一轮叫了什么工具，环境回了什么，最后停在哪。它不是训练框架要的张量，也不能直接丢进 TRL / PEFT。SFT 和 RL 都要先做一层改造。改造之后，回合记录里已经有 o、a 的全部语义，不缺字段。

```text
C 回合记录
  scenario_id
  turns[]     每轮：observation_before、tool_calls、events、observation_after
  final_state
  finish
  protocol
        |
        |  改造，不重跑环境
        v
SFT  messages JSONL     只在 assistant 上算 loss
RL   (o_t, a_t, r)      学生模型当 A 重新 rollout 时再采 logprob
```

## 1. o、a 在哪一层

一次 assistant 输出是一个策略步，也就是一个 turn。17 规定每轮最多 1 个工具调用。一轮里出现两个，C 记 TOO_MANY_TOOL_CALLS，本轮不执行。不能事后把一个 completion 切成几个不存在的决策。

```text
o_t   C 这一轮交给 A 的 context
      observation（user_request、tools、last_tool_result）
      history
      protocol_feedback
      turn_index / max_turns

a_t   A.respond 的那一次输出
      恰好一个 tool_call，或一个 finish

环境  C 把家庭工具交给 B.step，finish 自己留下
      得到 events[]

o_{t+1}  下一轮 context
      上一轮 events 变成 last_tool_result
      history 多了一轮 assistant 和 tool
```

所以 `turns[].turn`、`tool_calls`、`events` 三件套已经是 o-a-o：

```text
turn
  observation_before   ->  o_t 的可见部分
  tool_calls           ->  a_t
  events               ->  环境回执，写进 o_{t+1}
  observation_after    ->  o_{t+1} 的可见部分
```

卧室空调那条，五轮就是五对 (o, a)：

```text
o0  用户话「卧室太热了，把空调调到 24 度」，还没有 device_id
a0  observe_home
o1  房间目录，没有设备 id
a1  inspect_room(room_bedroom)
o2  看到 device_bedroom_climate
a2  inspect_device(...)
o3  target=25.0，范围 7.0..32.0
a3  execute_action(set_temperature, 24.0)
o4  state_after.target=24.0
a4  finish(outcome=completed)
结束
```

RL 教材里写的 o,a,o,a 就是这个序列。差的只是：C 把它按 turn 包成 JSON，训练器要 chat messages 或 token 序列。

## 2. 为什么不能直接拿去训练

回合记录缺三样训练器要的东西，多一样训练器不要的东西。

```text
缺
  1. 拼给 tokenizer 的 messages / input_ids
  2. 哪些 token 算 assistant，哪些是 observation（loss mask）
  3. 学生模型的 logprob     教师 DeepSeek 的 token 概率不能当 1.5B 的 logprob

多
  审计字段：call_id、elapsed、protocol 细节
  这些 SFT 用不到，RL 的 reward 也不从这里读
```

因此要有一个纯函数改造，不调 B，不调 A：

```text
to_sft(回合记录, Scenario) -> messages 样本
to_rl_view(回合记录, Scenario, 条件2/3/4) -> 逐步 (o_t, a_t) + 终局 R
```

今天 17 只要求 D5 落盘回合记录。这两个函数属于以后的 E、F，还没写。

## 3. 改造成 SFT

SFT 学的是「看见这些 context，吐出这个 a」。把每一轮的 a 写成一条 assistant 消息，把 events 写成 tool 消息，串成一段对话。loss 只打在 assistant 上。

卧室空调成功轨迹改完是：

```json
{
  "scenario_id": "sc_001",
  "blueprint_id": "bp_001",
  "messages": [
    {
      "role": "system",
      "content": "工具 schema：observe_home / inspect_room / inspect_device / execute_action / finish"
    },
    {
      "role": "user",
      "content": "卧室太热了，把空调调到 24 度"
    },
    {"role": "assistant", "tool_calls": [{"name": "observe_home", "arguments": {}}]},
    {"role": "tool", "content": "房间目录：卧室... 没有 device_id"},
    {"role": "assistant", "tool_calls": [{"name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}]},
    {"role": "tool", "content": "device_id=device_bedroom_climate"},
    {"role": "assistant", "tool_calls": [{"name": "inspect_device", "arguments": {"device_id": "device_bedroom_climate"}}]},
    {"role": "tool", "content": "target=25.0，set_temperature 7.0..32.0"},
    {"role": "assistant", "tool_calls": [{"name": "execute_action", "arguments": {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 24.0}}}]},
    {"role": "tool", "content": "ok，target=24.0"},
    {"role": "assistant", "tool_calls": [{"name": "finish", "arguments": {"outcome": "completed", "summary": "已把卧室空调调到 24 度。"}}]}
  ]
}
```

进入主 SFT 集的条件是 17 第四节：C 程序审查四步全过；T3/T4/T5 还要 D6 过。失败轨迹不进主集。中间某步 `UNKNOWN_DEVICE` 随后改对了，只要终局审查过，整段对话仍可进 SFT：模型能从 protocol_feedback 学到纠正。

每轮只有一个 tool_call，SFT 里就是一条 assistant 消息接一条 tool 消息。

## 4. 改造成 RL

RL 要的就是 o,a,o,a，外加奖励。回合记录已经按 turn 排好了 (o_t, a_t)。还差两件事：奖励从哪来、logprob 从哪来。

```text
奖励
  17 第四节给出一个终局 R
  C 四步（及需要时 D6）全过：R = 1
  有不过：R = 0
  今天不做逐步 shaping。HomeFlow 的逐步 RLVE 以后再说

logprob
  必须来自正在训练的学生模型
  D5 里若 A 是 DeepSeek，那条轨迹只适合 SFT
  做 GRPO 时：同一条 Scenario（同一个 sc 或同一条 bp 新开 sc）让学生当 A，C 再跑 G 条
  学生每吐一个 a_t，本地记下 logprob
```

一条学生 rollout 在优化器眼里是：

```text
o0 -> a0(logprob0) -> o1 -> a1(logprob1) -> ... -> a_T
                                              |
                                              v
                                         R = C 四步（及 D6）
```

GRPO 的组是「同一任务定义下的多条轨迹」。任务定义是 `blueprint_id`。每次开跑是 `scenario_id`。所以：

```text
bp_001
  sc_001  学生轨迹 1，R=1
  sc_002  学生轨迹 2，R=0
  sc_003  学生轨迹 3，R=1
组内比高低，更新 LoRA
```

终局 R 会回灌到这条轨迹里每一个 a_t 的 token。这就是为什么一个 completion 不能拆步：拆了会把一次采样当成两次独立动作，优势函数会算错。

C 的五项里没有 logprob，这是故意的。教师轨迹不拿去做 GRPO。学生 rollout 时，F 模块在 `A.respond` 那一层截 logprob，再和 C 的回合记录按 turn 对齐。

## 5. 和论文、现有代码的对齐

```text
本项目
  一次 assistant 输出 = 一个 turn = 一个 a_t
  与 SimuHome ReAct「每次模型只出一个 action」同一层
  与 HomeFlow「一条轨迹是 (o1,a1,...,oT,aT)，SFT 对 a_t 做因果 LM」同一层

C 现在真正写下的 turn_record（代码）
  turn_index
  assistant_output
  observation_before
  observation_after
  tool_events
  已经够做上面两种改造

17 的五项是把这些字段收成审计包
  turns 里要能还原 observation_before / tool_calls / events
  第三节示例为了短，只写了 tool_calls 和 events
  落盘时必须把 observation_before 留下，否则 SFT 的 o_t 拼不回来
```

HomeFlow 的 SFT 公式里还把蓝图 Φ 写进条件。本项目 A 看不见 task，SFT 消息里也不放 `conditions`。RL 的 R 由 D5 事后算，不进 observation。

## 6. 结论

```text
直接拿 C 的 JSONL 去 train          不行
按 turn 改造成 messages 做 SFT      行，而且字段够
按 turn 看成 o,a,o,a 做 RL          行，但要学生重新 rollout 拿 logprob
每轮 1 个 tool_call                 一个 a，SFT 一条 assistant，RL 一步
```

E 读成功回合记录，写出 SFT JSONL。F 让学生当 A 进 C，复用同一套回合记录形状，只多记 logprob 和终局 R。C 自己继续只导出五项，不负责训练格式。
