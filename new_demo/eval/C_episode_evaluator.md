# C_episode_evaluator.py

职责：
  跑完读 task 和五项记录，打 C-1..C-4。不调大模型。

输入：
  Scenario、turns、final_state、finish、protocol、是否出现过 TOO_MANY_TOOL_CALLS。

输出：
  CLabels：C-1 协议、C-2 终态、C-3 观察、C-4 finish 契约。

读取：
  task.conditions / keep / required_observations / expected_finish
  scenario.home 的初值，供 ge/le 比较

写入：
  无。不覆盖五项记录。

不负责：
  补 outcome、把物理失败改成成功、D6。

对应文件：
  new_demo/eval/C_episode_evaluator.py

```text
C-1  有 finish、未 truncated、每轮没有超过 1 个工具
C-2  eq 比 value；ge 终态 > s0；le 终态 < s0
     keep 仍只 eq；空数组过；不冻整屋
C-3  required_observations 都成功 inspect 过，空数组过
C-4  outcome 对齐；refused 的 reason_code 落在允许集
```
