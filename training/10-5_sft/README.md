# 10-5 SFT：1.5B 训练准备与预测试

本轮使用已有 Qwen2.5-1.5B-Instruct HF 权重。每类训练100、验证20、测试40，总计500/100/200，五类混合训练。

```text
代码与说明：本目录；每份py/config均有同名中文md
运行环境：/root/autodl-tmp/sft-venv
原始权重：/root/autodl-tmp/models/Qwen2.5-1.5B-Instruct/hf
运行产物：/root/autodl-tmp/training_runs/10-5_sft
小型验证报告：reports/preflight_report.json及.md

common.py    配置、指纹和中文产物说明
data.py      筛选、分组划分、可见消息、监督mask
train.py     TRL/PEFT、epoch保存、恢复入口
evaluate.py  本地模型接入A/C/B、C标签与可选D6
preflight.py 最小GPU闭环和逐张量重载核对
test_pipeline.py 自动回归测试
```

## 只做准备与测试

以下入口不启动完整500条训练。GPU冒烟只用两条最长训练轨迹、两次更新，保存两份epoch检查点；训练样本中的五条学生交互仅测试接口。

```bash
/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_sft/test_pipeline.py -q
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/data.py
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/train.py
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/preflight.py --gpu-smoke --report-dir training/10-5_sft/reports
```

检查阶段修复后可通过`--reuse-smoke <已有smoke目录>`继续重载和接口检查，不重复更新模型。不同评测应使用不同输出目录，防止覆盖已有证据。

## 后续批准后才执行

下面命令是未来的完整训练和评测入口，本轮不执行。完整训练要求确认开关；最终测试要求另一个确认开关。训练最多3个epoch，每个都保留，验证loss选择adapter。

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/train.py --mode train --confirm-full-training
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/train.py --mode train --confirm-full-training --resume-from-checkpoint /root/autodl-tmp/training_runs/10-5_sft/sft-main/checkpoint-63
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/evaluate.py --split validation --adapter /root/autodl-tmp/training_runs/10-5_sft/sft-main/selected_adapter --output /root/autodl-tmp/training_runs/10-5_sft/validation-selected
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/evaluate.py --split test --confirm-final-test --adapter /root/autodl-tmp/training_runs/10-5_sft/sft-main/selected_adapter --output /root/autodl-tmp/training_runs/10-5_sft/test-selected
```

默认不开D6，报告仅给C程序通过情况，T3/T4/T5语义待审不计完整成功。需要完整成功率时显式加`--semantic-judge deepseek`，会发收费请求，要求已有密钥；日志留在仓库外，不提交密钥。基础模型对照不传`--adapter`，其余协议和集合保持一致。

正式检查点编号取决于Trainer实际step；`checkpoint-63`只是当前500条、有效batch8下的预计首epoch路径，实际以`checkpoint_index.json`为准。
