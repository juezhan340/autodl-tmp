# 10-5 GRPO落地与冒烟

详细规格与实测见[第12文档](../../newdoc/1004推进文档/12_GRPO落地设计_轨迹预处理奖励判定与4x4冒烟.md)。历史micro2冒烟保留；用户已批准100任务第一阶段，正式配置micro16累计1，完成后自动评测原固定200任务。未启动500任务完整训练。

```text
runtime / config    读写、指纹、配置校验与中文产物说明
rollout             同组4路A/B/C交互，保存真实采样token
trajectory          逐事件重放，生成进度、取证、错误和安全证据
reward              结尾三票、奖励明细、同任务组内优势
model_math          共享BF16基座与两个FP32 adapter、稀疏词表输出、clip/KL
smoke               CPU校验 / GPU一次更新；显式确认入口
  test_grpo           CPU回归与批量路由验证
  stage1_config       用户批准100任务、16×1的正式配置
  run_stage           五类各20、25批次、共享optimizer、阶段结束保存
  evaluate_stage      原200任务greedy + 原D6；对照已有epoch3
  live / dashboard_server / dashboard   独立6008只读监控
  start               独立会话启动训练/页面；显式双确认
  browser_verify / test_stage           页面检查与第一阶段CPU回归
```

使用已有`/root/autodl-tmp/sft-venv/`，没有安装新的训练框架。输出位于仓库外`/root/autodl-tmp/training_runs/10-5_grpo/`。密钥只读根目录`.env.deepseek`，不能提交。

```bash
/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_grpo/test_grpo.py -q
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/smoke.py --mode check
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /root/autodl-tmp/sft-venv/bin/python -u \
  training/10-5_grpo/smoke.py --mode smoke --confirm-smoke --confirm-api-review
```

2026-10-05已完成4×4冒烟：实际4路生成、16轨迹、micro2累计8、一次更新。原SFT adapter和固定参考保持不变。参数与奖励权重仍待小规模训练校准，不能把一次更新当成效果提升证明。

正式第一阶段启动入口：

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/start.py dashboard
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/start.py train \
  --confirm-stage-training --confirm-api-review
```

当前运行：`training_runs/10-5_grpo/stage1-100-20261005T160227906618Z/`，训练PID7783，页面PID7001。实时状态见`training_status.json`及6008页面；不要拿本索引静态PID代替进程启动身份校验。运行目录包含每批日志/证据，只有阶段结束保存完整checkpoint，异常后已有更新时保留一次中断快照。OOM不降批、不自动重跑。

实例重启后公网映射已变化，当前6008地址为：

```text
http://127.0.0.1:6008
https://uu753393-981f-3f635753.westd.seetacloud.com:8443
```

新地址页面与健康接口200，Playwright四种屏幕检查、真实曲线像素、轮询和注入防护通过。截图和报告在仓库外`training_runs/10-5_grpo/monitor_checks/stage1-100/`。本轮CPU回归149 passed；未额外执行GPU冒烟。图片查看工具当前不支持图像输入，布局结论依据浏览器边界与像素检查，未宣称人工看图验收。

第一阶段100任务训练已经完成，400轨迹、25次实际更新、无OOM；分配峰值24.88GiB、预留峰值27.15GiB。最终模型保存到上述运行目录`checkpoint-stage1/policy/`。原固定200任务评测已自动开始，完成结果会出现在同一页面与`evaluation/comparison.json`。
