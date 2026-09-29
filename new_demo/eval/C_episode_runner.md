# C_episode_runner.py

职责：
  C 的唯一启动入口 run(scenario)。每轮把 context 给 A；家庭工具走 B.step；finish 自己留下。

输入：
  Scenario 六项 + Policy.respond。

输出：
  五项回合记录（不含对错）+ 另附 C 标签。

读取：
  循环用 scenario_id、home、user_request、episode_config。
  task 循环不读，审查时交给 evaluator。

写入：
  不落盘。调用方以后才写入 D5_trajectories.jsonl。

不负责：
  处理 probe、把 summary-only 补成 completed、调 D6、算 reward。

对应文件：
  new_demo/eval/C_episode_runner.py

```text
每轮最多 1 个工具
  两个 -> TOO_MANY_TOOL_CALLS，本轮不执行，消耗 turn
纯文本终答
  收成 finish，能解析到什么记什么，不补 outcome
turns[]
  turn / observation_before / tool_calls / events / observation_after
events
  完整 result，下一轮 last_tool_result 就是它
```
