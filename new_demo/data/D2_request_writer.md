# D2_request_writer.py

职责：
  D2 第二次。读 D0_request_T1.md … T5.md，写一句中文。不是 A。

输入：
  category、task、home。

输出：
  一句 user_request。

读取：
  D0_template.build_prompt(kind=request)

写入：
  原始响应由客户端写 data_raw/api/。

不负责：
  写 task、审指令。

对应文件：
  new_demo/data/D2_request_writer.py
