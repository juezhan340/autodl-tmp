# B_tool_schema.py

职责：
  给出 A 可见的四个家庭工具和 finish 公开 schema，并校验调用形状、动作参数。

输入：
  ToolCall，或设备 ActionSchema + params。

输出：
  ValidationResult，或统一 ok/error 外壳。外壳不含 elapsed_ms。

读取：
  无。

写入：
  无。

不负责：
  改 state、判任务成败。

对应文件：
  new_demo/env/B_tool_schema.py

```text
B.step 只认
  observe_home / inspect_room / inspect_device / execute_action
observe_home 描述：房间 id 和名称；不返回设备、不返回温湿度
C 才认 finish
  必填 summary
  可选 outcome=completed|refused
  可选 reason_code
  出现 facts -> BAD_REQUEST
```
