# C_episode_evaluator.py

职责：
  跑完读 task 和五项记录，打 C-1..C-4。不调大模型。

输入：
  Scenario、turns、final_state、finish、protocol、是否出现过 TOO_MANY_TOOL_CALLS。

输出：
  CLabels：C-1 协议、C-2 终态、C-3 观察、C-4 finish 契约。

读取：
  task.conditions / keep / required_observations / expected_finish
  s0 的初始 state（拒绝任务要比有没有被改）

写入：
  无。不覆盖五项记录。

不负责：
  补 outcome、把物理失败改成成功、D6。

对应文件：
  new_demo/eval/C_episode_evaluator.py

```text
C-1  有 finish、未 truncated、每轮没有超过 1 个工具
     只有 summary 仍算有 finish
C-2  conditions/keep 全过，空数组过
     refused 还要终态等于 s0
C-3  required_observations 都成功 inspect 过，空数组过
C-4  outcome 对齐；refused 的 reason_code 落在允许集
     查询也是 completed；facts 或缺少 outcome -> 失败
```
