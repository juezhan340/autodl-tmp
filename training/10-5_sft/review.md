# review.py 中文说明

```text
职责：对已经生成的四模型测试轨迹并发补D6三票，保留原始程序评测。
输入：source目录、根目录.env.deepseek路径、workers、收费确认开关。
输出：semantic_review下的三票缓存、进度、四组复核轨迹与汇总。
读取：四组原始trajectories/summary、D6源码与提示词、非提交密钥文件。
写入：source/semantic_review/，不覆盖原始轨迹或checkpoint。
不负责：加载本地模型、生成新动作、SFT/GRPO、修改C判定。
```

默认workers=100，限制最多100条轨迹同时审，每条依次调用三次API，因此同时在途的API调用不超过100。原D6逻辑要求三票全部有效，然后多数决；票不足写system_failure，并保留为待确认，不能计成模型错误或成功。

原始轨迹以模型名与sample_id区分，相同任务在不同模型的输出独立评审，不跨模型复用投票。缓存绑定原始行指纹与D6源码/模板/模型/温度；中断后可以继续缺失任务。完整坏行或源版本变化报错，最后半行可以安全去掉。system_failure只有显式加retry-system-failures才再次投票；新投票作为另一次完整三票结果保存。

进度、汇总和JSONL均配同名中文md。HTTP尝试数包括客户端自动网络重试，逻辑投票数与HTTP发包数分开报告。日志不记录key、请求头、完整请求体；根目录密钥由.gitignore排除。

```bash
/root/autodl-tmp/sft-venv/bin/python -u training/10-5_sft/review.py \
  --source /root/autodl-tmp/training_runs/10-5_sft/comparison_test_20261005 \
  --env-path /root/autodl-tmp/10-04/.env.deepseek \
  --workers 100 --confirm-api-review
```

复核结果保留原generation_attempts、program_success和C标签，重新计算完整成功率、D6判错与待确认数。T1/T2无需D6；C失败轨迹直接失败，不发API请求。T3/T4/T5程序通过才入队，本轮预期310条、930个逻辑投票。

本轮已实际完成310条补审、930次HTTP调用，无系统失败，耗时9.567秒。相同基础轨迹文件未修改；效果总结仅见newdoc第18篇，训练复盘见第19篇。六项无网络回归覆盖确认、并发上限、三票与源文件保留、缓存恢复、系统失败重投以及缓存版本检查。
