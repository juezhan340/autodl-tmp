# start.py 中文说明

2026-10-06：配置可白名单选择`run_stage.py`或`train_full.py`；正式500使用`--config training/10-5_grpo/full_config.json`，仍要求训练/API两个显式确认。active_run记录配置路径，后台`start_new_session=True`与独立train.log保留；不会自动测试、降批或重跑。

职责：沿用既有SFT独立会话启动模式，启动第一阶段GRPO或6008监控。训练与页面各自有PID、启动身份、文件锁和日志，不依赖对话、SSH或浏览器；服务器关机会中断。

```text
输入：dashboard/train；stage1_config；训练和API两个确认参数
读取：services/<服务>.json中的旧PID身份；当前配置
输出：已启动PID、运行目录和日志；重复启动报错
写入：services元数据及同名md；active_run.json/md；独立日志
不负责：更改micro、自动OOM重试、训练计算、API判分
```

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/start.py dashboard
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/start.py train \
  --confirm-stage-training --confirm-api-review
```

默认只起页面。训练输出独立`stage1-100-UTC时间戳/`，stdout/stderr写该目录train.log；线程数4。启动使用`start_new_session=True、stdin=DEVNULL`。监控启动后检查`/healthz`确为grpo-monitor，训练启动后检查子进程未立即退出。
