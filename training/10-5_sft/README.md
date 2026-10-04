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
progress.py  训练独写状态快照、每step真实指标
monitor.py   6008端口只读HTTP服务，不加载模型
dashboard.html 单页曲线、进度、GPU、checkpoint表
launch.py    页面和训练独立后台启动，PID/日志记录
evaluate.py  本地模型接入A/C/B、C标签与可选D6
preflight.py 最小GPU闭环和逐张量重载核对
test_pipeline.py 自动回归测试
test_monitor.py 只读页面接口与后台确认回归
browser_check.py 可选Playwright桌面/手机验证
```

## 只做准备与测试

当前正式配置为4条轨迹×梯度累计2次=有效batch8，三个epoch全部保留完整checkpoint。以下入口不启动完整500条训练。GPU冒烟现在只用一个micro-batch的最长训练轨迹（默认四条）、两次更新，保存两份epoch检查点；训练样本中的五条学生交互仅测试接口。此次修改没有重新执行GPU冒烟，reports/preflight_report仍保留旧2×4配置的历史证据。

```bash
/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_sft/test_pipeline.py training/10-5_sft/test_monitor.py -q
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/data.py
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/train.py
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/preflight.py --gpu-smoke --report-dir training/10-5_sft/reports
```

检查阶段修复后可通过`--reuse-smoke <已有smoke目录>`继续重载和接口检查，不重复更新模型。不同评测应使用不同输出目录，防止覆盖已有证据。

旧2×4冒烟与新配置不同，不能通过reuse继续冒充新配置验证。此次仅重新登记数据manifest的配置版本，所有划分文件内容SHA-256保持不变；旧manifest另存仓库外version_history，不改旧checkpoint。

## 训练监控

```text
训练进程 -> sft-main/training_status.json、metrics.jsonl、checkpoint_index.json
                ↓ 只读
独立页面进程 -> 0.0.0.0:6008 -> 浏览器每3秒更新
```

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/launch.py dashboard
```

启动页面不会启动训练。页面和训练使用不同独立Linux会话，日志分别位于output_root/services/dashboard.log和train.log。用户已批准正式训练，2026-10-05 02:06（Asia/Shanghai）通过独立后台入口启动4×2、3个epoch；实时状态以页面为准。历史smoke不作为正式进度。

本次页面、独立进程、公网访问和浏览器核验见reports/monitor_verification.md。浏览器验证是可选工具，不属于训练运行依赖。

```text
本机：http://127.0.0.1:6008
公网：https://uu753393-afb3-4b7a916d.westd.seetacloud.com:8443
```

## 训练与评测入口

下面是完整训练、恢复和评测入口。正式训练已按用户批准启动，请勿重复启动；最终200条测试仍需另一个确认开关，本次未执行。训练连续3个epoch，中间自动验证并保存，每个都保留，验证loss选择adapter。初期测速记录见reports/training_start.json及同名md；其中ETA是估算，不代表训练已完成。

```bash
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/launch.py train --confirm-full-training
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/launch.py train --confirm-full-training --resume-from-checkpoint /root/autodl-tmp/training_runs/10-5_sft/sft-main/checkpoint-63
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/evaluate.py --split validation --adapter /root/autodl-tmp/training_runs/10-5_sft/sft-main/selected_adapter --output /root/autodl-tmp/training_runs/10-5_sft/validation-selected
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/evaluate.py --split test --confirm-final-test --adapter /root/autodl-tmp/training_runs/10-5_sft/sft-main/selected_adapter --output /root/autodl-tmp/training_runs/10-5_sft/test-selected
```

默认不开D6，报告仅给C程序通过情况，T3/T4/T5语义待审不计完整成功。需要完整成功率时显式加`--semantic-judge deepseek`，会发收费请求，要求已有密钥；日志留在仓库外，不提交密钥。基础模型对照不传`--adapter`，其余协议和集合保持一致。

正式检查点编号取决于Trainer实际step；`checkpoint-63`只是当前500条、有效batch8下的预计首epoch路径，实际以`checkpoint_index.json`为准。
