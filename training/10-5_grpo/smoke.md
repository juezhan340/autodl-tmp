# smoke.py 中文说明

职责：CPU核对800条旧轨迹，或执行4任务×4轨迹、四路生成、micro2累计8、一次参数更新的GPU冒烟。没有完整500任务训练入口。

```text
输入：--mode check/smoke、--config、两项显式确认
读取：已有SFT数据、模型和adapter；smoke模式才读DeepSeek配置
输出：check_report或smoke_report；失败生成failure.json及同名md
写入：training_runs/10-5_grpo/<模式-UTC时间戳>/
不负责：完整训练、长期后台服务、自动评测最终泛化效果
```

`select_tasks`仅从500条训练Scenario中按教师token长度选T2/T3/T4/T5各一项，教师动作不喂给actor；同时检查validation/test的group_id不重叠。`check_archives`重放四模型各200条旧测试轨迹，核对源文件指纹未变，不调用API、不加载GPU模型。

`run_smoke`检查GPU与API确认，加载两套相同SFT adapter，生成16条新轨迹，完成重放、语义评审、奖励、组内优势和原始token打包。old与ref按micro重算并保存CPU；首次policy/ref概率必须一致。各阶段同步GPU并重置显存峰值，allocated/reserved分别记录。

`train_once`做8次micro反向，再梯度裁剪和一次AdamW更新；每个micro已按整次token总数归一，不额外再除8。同分无信号时不执行step或假报权重更新。更新后核对固定参考及原始SFT文件均未变化。冒烟adapter只保存到新运行目录，不能替换selected_adapter。这里只是最小执行闭环，不能直接恢复成完整训练。

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/smoke.py --mode check
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /root/autodl-tmp/sft-venv/bin/python -u \
  training/10-5_grpo/smoke.py --mode smoke --confirm-smoke --confirm-api-review
```

已执行的GPU目录：`/root/autodl-tmp/training_runs/10-5_grpo/smoke-20261005T145556954487Z`。16条、观察到4路批量、8次micro、1次更新、56.035秒；最长2762 token。PyTorch分配峰值4780.01MiB，预留峰值6990MiB；来自不同阶段，不能相加。测试结束，未启动完整训练。完整结果及限制见第12文档。
