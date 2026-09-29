# PIPE_pipeline.py

职责：
  编排入口。默认 D0→D4 停闸。确认前禁止 C.run、禁止发 sc_*。

输入：
  未编号草稿列表；输出目录。

输出：
  data_processed/D4_blueprints.jsonl
  data_raw/D34_failures.jsonl
  摘要：blueprint_count / failure_count / stopped_after=D4

读取：
  D4_oracle.check_blueprint

写入：
  上述两个 jsonl。若目录里已有 D5_trajectories.jsonl 会删掉，避免未确认残留轨迹被当成新结果。

不负责：
  调 D2/D3/D6、编 Scenario、跑 C。

对应文件：
  new_demo/data/PIPE_pipeline.py

continue_from_d5 在未实现 D5 前直接报错，防止跳过停闸。
