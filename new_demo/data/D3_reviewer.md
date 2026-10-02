# D3_reviewer.py

职责：
  D3 两步。程序先扫硬泄露；过了再用 D3_review_T1.md … T5.md 问外部 DeepSeek。

输入：
  category、task、user_request、intent、可选 home。

输出：
  accept 与 codes。

读取：
  第二步读对应 T 的 D3_review_T*.md，填房间名和设备显示名。

写入：
  原始响应由客户端写 data_raw/api/。

不负责：
  写用户话、打 B。

对应文件：
  new_demo/data/D3_reviewer.py
