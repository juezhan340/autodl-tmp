# D2_task_writer.py

职责：
  D2 第一次。外部 DeepSeek 按 T 固定模板写 task JSON。不是 A。

输入：
  s0、一条画像、category。

输出：
  task；T4 另附 probe。形状不对则 error_code=INVALID_TASK_JSON。operator 只许 eq/ge/le；T1/T2 只许 eq。

读取：
  D0_template.build_prompt(kind=task)

写入：
  原始响应由客户端写 data_raw/api/。

不负责：
  写用户那句话、打 B、发 blueprint_id。

对应文件：
  new_demo/data/D2_task_writer.py
