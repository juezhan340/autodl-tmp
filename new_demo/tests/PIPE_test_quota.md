# PIPE_test_quota.py

职责：
  测配额编排。不调 DeepSeek，用假 sample_fn 看停闸。

输入：
  tmp_path，假 runner。

输出：
  断言每类成功数、尝试次数、拒绝覆盖旧目录。

读取：
  run_quota_pipeline

写入：
  pytest 临时目录里的 jsonl。

不负责：
  真模型、真 B。

对应文件：
  new_demo/tests/PIPE_test_quota.py
