# D2_request_writer.py

职责：
  D2 第二次。读共用的 D0_request.md，写一句中文。不是 A。

输入：
  category、task、home（只用来抽 display_name）。

输出：
  一句 user_request。

读取：
  D0_template.build_prompt(kind=request)

写入：
  无（API 原文走客户端）。

不负责：
  读画像库、调 B。

对应文件：
  new_demo/data/D2_request_writer.py
