# 10-5 GRPO落地与冒烟

详细规格与实测见[第12文档](../../newdoc/1004推进文档/12_GRPO落地设计_轨迹预处理奖励判定与4x4冒烟.md)。历史micro2冒烟与100任务第一阶段保留；第一阶段最终179/200。本轮已直接启动500任务池正式反馈采样，micro16累计2、32条一次更新，结束自动评测原200任务。

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
  full_config / train_full / sampler    全500覆盖、反馈复访、同policy选8组、32条更新
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

最终200评测已完成、无待审：SFT epoch3为176/200（88%），GRPO第一阶段179/200（89.5%）；逐题6改善、3退步。页面completed并保留全部训练曲线、checkpoint和结果。固定参考与SFT原文件不变，原始评测轨迹未被D6补审改写。小幅提升不等于已证明收敛或所有类别都改善，详见第12文档末尾。

2026-10-06正式500运行已启动，不追加冒烟或规模测试：

```text
配置       full_config.json；入口train_full.py；采样器sampler.py
运行       /root/autodl-tmp/training_runs/10-5_grpo/full500-20261005T180454543706Z/
后台PID    训练22635；页面22658（实际存活按services元数据启动身份核对）
起点       第一阶段最终policy和AdamW状态；KL参考仍固定SFT epoch3
更新       8组×G4=32，micro16累计2；rollout仍四路
预算       全500优先覆盖，最多1500候选组、64实际更新；不是64步效果承诺
日志       train.log、metrics.jsonl/md、training_status.json/md、sampler_state.json/md
证据       candidates/逐组轨迹/证据/奖励；windows/采用组/old-ref概率/微批loss
保存       第32次更新、覆盖500、结束；异常后已有更新保存中断权重
评测       完成训练后原200 test，原C+D6，页面同时保留epoch3与stage1对照
```

正式启动命令为`start.py train --config training/10-5_grpo/full_config.json --confirm-stage-training --confirm-api-review`。正常运行中不要重复执行；本次已经后台启动，日志不绑定对话。此处启动记录不代表训练已结束。

随后第二次更新softmax OOM，首步与失败日志已保留。已直接从中断checkpoint续跑，当前入口配置为`full_resume_config.json`、训练PID24357、目录`full500-resume-20261005T181501989146Z`。保留micro16累计2，完整decoder不变，只把LM head的真实生成token概率改为128token分块与checkpoint重算；恢复52项覆盖和反馈，不复用未提交轨迹。6008页面自动切换新运行。详见12文档11.5节。

续跑首批已完成：累计step2、覆盖80项、micro16×累计2实际执行；该批allocated/reserved峰值13.52/15.04GiB。训练仍在后台，实际最新状态以6008页面或运行状态文件为准。
