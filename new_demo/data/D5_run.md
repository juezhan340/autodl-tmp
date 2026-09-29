# D5_run.py

职责：停闸确认后编 Scenario，交给 C.run。不调 D6，不删失败轨迹。
输入：蓝图、A、新的 scenario_id。
输出：scenario、五项记录、C 标签、category、D6 初值（T1/T2 跳过，其余待审）。
读取：蓝图。写入：由 PIPE 写入 D5_trajectories.jsonl。
不负责：发 blueprint_id、重算 C 标签、跑 D6。
对应文件：new_demo/data/D5_run.py
