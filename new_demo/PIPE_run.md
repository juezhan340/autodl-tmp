# PIPE_run.py

职责：命令行。默认 generate_until_d4 后停闸。`--full` 一次跑到数据集。`--continue-from-d5` 只跑后半段。
`--quota` 每类凑满成功轨迹（默认目标 50、最多 100 次、每类 10 路）。
`--workers 25` 按条并发；`--categories T1` 只跑一类。
`--quota` 不能和 `--continue-from-d5` 一起用。
对应文件：new_demo/PIPE_run.py
