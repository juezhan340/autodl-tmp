# train_full.py 中文说明

正式500任务池入口，用户已批准直接运行，不包含新测试/冒烟分支。

输入：`full_config.json`，train500场景，第一阶段最终policy及AdamW状态，固定SFT epoch3参考，根目录DeepSeek配置。输出：独立`full500-*`运行目录，结束后原test200的C+D6评测。

```text
恢复policy/optimizer，独立加载SFT reference
  ↓ sampler给场景，四组为一个生成/复核chunk，每组四路rollout
候选组分别保存rollouts、packed、evidence、rewards、advantages
  ↓ 同policy最多32组，争取6个informative + 两个锚点
完整选8组，32条 → 重算old/ref → 两次micro16反向 → 一次step
  ↓ 写metrics、窗口selection、微批loss、概率pt、显存报告
未采用候选不带到下一policy；优先覆盖500，再反馈复访
  ↓ 最多1500组、64次实际step；全同分窗口跳过，不纯KL刷step
保存覆盖500、第32更新、final里程碑；自动评测固定200
```

`restore_optimizer`核对AdamW参数和动量形状；`collect_chunk`是候选轨迹与奖励的唯一写入者；`train_full`负责全局32条token分母、选组、真实step计数和checkpoint；`main`负责启动状态、失败落盘和结束评测。

训练状态为`training_status.json/md`，历史为`metrics.jsonl/md`，stdout/stderr由`start.py`写`train.log`。采样元数据由`sampler.py`写`sampler_state.json/md`。API无效或重放/token错误直接失败，不冒充任务低分；OOM不自动降micro。有更新时异常另存中断权重，旧checkpoint均保留。

本轮不是逐bit断点续训：恢复AdamW动量但使用新seed。动态采样无固定epoch；checkpoint是明确命名的里程碑。所有candidate组属于同一采样policy版本，后续step禁止复用旧轨迹。

第二次更新的大词表softmax OOM后，`resume_run`模式从中断adapter与AdamW状态继续：核对已完成step，继承首步真实曲线，恢复52项覆盖和采样反馈；新目录写`resume_manifest.json/md`，旧失败日志保留。第二批未提交轨迹全部丢弃，新采样后更新。续跑配置启用128token LM head分块与重算，micro16累计2不变；只恢复训练状态和采样元数据，不宣称重现原随机生成过程。
