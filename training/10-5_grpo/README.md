# 10-5 GRPO落地与冒烟

详细规格与实测见[第12文档](../../newdoc/1004推进文档/12_GRPO落地设计_轨迹预处理奖励判定与4x4冒烟.md)。本目录仅支持旧轨迹奖励证据核对和一次GRPO参数更新，未启动500任务完整训练。

```text
runtime / config    读写、指纹、配置校验与中文产物说明
rollout             同组4路A/B/C交互，保存真实采样token
trajectory          逐事件重放，生成进度、取证、错误和安全证据
reward              结尾三票、奖励明细、同任务组内优势
model_math          共享BF16基座与两个FP32 adapter、稀疏词表输出、clip/KL
smoke               CPU校验 / GPU一次更新；显式确认入口
test_grpo           CPU回归与批量路由验证
```

使用已有`/root/autodl-tmp/sft-venv/`，没有安装新的训练框架。输出位于仓库外`/root/autodl-tmp/training_runs/10-5_grpo/`。密钥只读根目录`.env.deepseek`，不能提交。

```bash
/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_grpo/test_grpo.py -q
/root/autodl-tmp/sft-venv/bin/python training/10-5_grpo/smoke.py --mode check
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /root/autodl-tmp/sft-venv/bin/python -u \
  training/10-5_grpo/smoke.py --mode smoke --confirm-smoke --confirm-api-review
```

2026-10-05已完成4×4冒烟：实际4路生成、16轨迹、micro2累计8、一次更新。原SFT adapter和固定参考保持不变。参数与奖励权重仍待小规模训练校准，不能把一次更新当成效果提升证明。
