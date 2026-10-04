# launch.py 中文说明

```text
职责：将页面和训练启动到不同Linux会话，记录PID及日志。
输入：dashboard/train、配置路径、页面端口；训练确认或恢复路径。
输出：后台进程元数据，启动失败时抛异常。
读取：配置、历史服务PID和进程启动标识。
写入：output_root/services/{dashboard,train}.{json,md,log,lock}。
不负责：自动批准训练、守护重启、关机续跑、停止用户其他进程。
```

Popen采用start_new_session=True、stdin=/dev/null、日志重定向，不持有对话工具或SSH终端的输入输出。页面与训练可以分别退出、重启。实例关机、重启或平台主动清理进程仍会停止服务；训练恢复依赖已经保存的完整epoch检查点。

```bash
# 仅启动6008展示页面，不启动训练。
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/launch.py dashboard

# 用户批准后，才用这个独立后台入口启动完整训练。
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/launch.py train --confirm-full-training
```

同一服务启动时持有文件锁，并检查PID对应的启动标识，防止重复拉起。已有sft-main不能无确认覆盖，恢复还需传--resume-from-checkpoint；实际训练入口继续验证配置及数据版本。页面启动等待本机健康接口成功；没有停止、改配置或训练控制的网页接口。
