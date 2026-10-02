# A_policy.py

职责：
  Policy 接口。ScriptPolicy 给测试。DeepSeekPolicy 是 D5 里的 A。
  一场 episode：第一轮发 system + 用户话，之后只 append 模型输出和 observation。

输入：
  C 每轮 context（observation、tools、protocol_feedback、turn_index）。

输出：
  一个工具 JSON 或纯文本（C 会收成 finish）。

读取：
  D0_templates/A_policy.md，只在第一轮填 {{tools}}。

写入：
  无。会话 messages 留在 DeepSeekPolicy 实例上。

不负责：
  写蓝图、D6。

对应文件：
  new_demo/agents/A_policy.py
