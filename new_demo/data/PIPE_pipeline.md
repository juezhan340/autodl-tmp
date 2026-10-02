# PIPE_pipeline.py

职责：
  编排入口。默认 D0→D4 停闸。`--full` 时 D4 之后立刻 D5→D6→复制。
  `--quota` 时每类一边生成一边跑轨迹，凑满成功条数或用尽尝试次数。
  workers>1 时按样本并发。D5 模块不调 D6。

输入：
  条数或配额（目标成功数 / 最大尝试次数）、种子、输出目录、客户端、可选类别和并发。

输出：
  data_processed/D4_blueprints.jsonl
  data_raw/D34_failures.jsonl
  data_raw/D2_drafts.jsonl
  `--full` / `--quota` 另写 D5_trajectories.jsonl、D_dataset.jsonl
  配额模式另写 reports/progress.md、reports/quota.md
  摘要含 blueprint_count / failure_count / workers / stopped_after
  配额另含 per_category、target_success、max_attempts

读取：
  D1、D2、D3、D4、D5、D6、D_copy_dataset

写入：
  上述 jsonl。generate_until_d4 若发现旧 D5_trajectories.jsonl 会删掉。
  配额模式禁止写到已有 D4_blueprints.jsonl 的目录。

不负责：
  当 A、写提示词。

对应文件：
  new_demo/data/PIPE_pipeline.py
