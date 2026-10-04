# progress.py 中文说明

```text
职责：训练进程写入原子状态快照，追加官方Trainer真实指标。
输入：run_dir、配置、训练模式、Trainer回调事件。
输出：TrainingProgress及LiveProgress回调。
读取：Linux进程身份、PyTorch显存、checkpoint_index.json。
写入：运行目录中的training_status.json、metrics.jsonl及各自中文md。
不负责：训练调度、页面服务、检查点删除、生成虚构指标。
```

训练入口先写starting/preparing，再经过loading_model、running/training、evaluating、saving、finalizing，最后completed；异常写failed或interrupted。优化器每次更新写进度，正式训练每次更新也记录loss与学习率。页面每3秒读取，因此并非逐token流式推送。

状态中的PID同时绑定Linux启动标识，进程死亡或PID复用可以被页面识别。恢复训练更新进程身份、保留旧metrics历史；页面合并相同step的最新指标。时长统计指本次启动后的运行时间。

非数值或非有限值不写入JSON指标，防止NaN/Infinity导致浏览器无法解析整份状态；训练loss有限性的最终检查仍由train.py负责。
