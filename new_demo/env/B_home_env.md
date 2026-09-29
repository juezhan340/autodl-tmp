# B_home_env.py

职责：
  HomeEnv 沙箱。C 和以后的 D4 都调这一份。

输入：
  reset(scenario)
  step(ToolCall)

输出：
  reset -> observation
  step -> EnvStepResult(observation, event)
  observation：scenario_id、user_request、tools、last_tool_result
  runtime_state：给 C-2 / final_state，无 actions

读取：
  Scenario.home，复制进 StateEngine。

写入：
  只通过 execute_action 改运行时 state。原 Scenario 对象改了不影响环境。

不负责：
  解析 A、处理 finish、max_turns、打分。finish 传进 step 是 BAD_REQUEST。

对应文件：
  new_demo/env/B_home_env.py

这次实现的模块口：reset / step / observation / runtime_state。events、snapshot、restore、fork 按 18 先不写。
