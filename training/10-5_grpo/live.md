# live.py 中文说明

职责：训练主进程是状态和指标的唯一写入者。`LiveProgress.update`原子写`training_status.json/md`，`log`追加真实`metrics.jsonl`并更新快照。页面每3秒只读，训练不依赖浏览器或对话。

```text
输入：运行目录、第一阶段配置、真实阶段/奖励/更新/评测指标
读取：Linux进程身份；可选JSON与已完成JSONL行
输出：包含PID身份、100任务/400轨迹/25批次、200评测进度的状态
写入：training_status.json/md；metrics.jsonl/md
不负责：奖励判定、GPU生成、训练启动、监控HTTP
```

UTC时间带时区，浏览器按本地显示。`process_identity`排除僵尸和复用PID；`read_metrics`只忽略最后一个正在写入的半行，正式完整行损坏会报错。指标缺失显示空值，不把未评审reward记成0。
