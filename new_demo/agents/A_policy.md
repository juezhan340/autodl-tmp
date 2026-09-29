# A_policy.py

职责：
  Policy 接口。ScriptPolicy 给测试。DeepSeekPolicy 是 D5 里唯一的 A，role=A，不限 token。

输入：
  C 每轮 context。

输出：
  一个工具 JSON 或纯文本（C 会收成 finish）。

读取：
  D0_templates/A_policy.md，只填本轮观察。

写入：
  无。

不负责：
  写蓝图、D6。

对应文件：
  new_demo/agents/A_policy.py
