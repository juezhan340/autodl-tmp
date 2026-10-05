# evaluate_checkpoint.py 中文说明

职责：在正式训练仍复访时，独立评测已经冻结保存的里程碑权重，避免把500覆盖完成误写成64更新完成。

输入为`--training-run`、已保存checkpoint名称和`--confirm-api-review`；允许coverage500、update032、full500三个里程碑。默认输出在训练目录的`checkpoint_evaluations/`下，并用UTC时间隔离；`--detach`以独立会话启动。

```text
读取训练run_config与checkpoint stage_state
  ↓ 冻结adapter文件指纹，单独创建评测状态
复用evaluate_stage：原test200 → greedy自主环境交互 → 原D6三票
  ↓ 对比SFT epoch3、GRPO第一阶段、本里程碑
核对权重未变，写evaluation_report与完整评测证据
```

`evaluate`只写独立输出目录，不改训练的training_status、sampler、optimizer或active_run。`main`负责显式API确认、后台PID及stdout/stderr日志。训练继续运行，评测消耗另一个推理模型的显存；评测失败单独写failure.json/md，不停止训练、不自动重跑。模型标签包含checkpoint名称和step，不能把覆盖500阶段结果称为最终训练结果。

输出包括evaluate.log、process.json/md、run_config.json/md、training_status.json/md、evaluation/原轨迹、D6票、summary及comparison，均复用原有同名中文说明写入工具。没有新测试或冒烟分支。
