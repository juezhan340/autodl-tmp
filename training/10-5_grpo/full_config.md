# full_config.json 中文说明

这是直接执行的500任务池正式配置，不是冒烟配置。policy继续第一阶段最终adapter，并恢复对应AdamW状态；固定参考仍为SFT epoch3。训练数据仅train500，结束用原test200评测。

```text
每次更新：8组 × G4 = 32条轨迹 = micro16 × 累计2
同时rollout：4路
候选组上限：1500；单窗最多32组；实际更新最多64次
先覆盖剩余400与历史100，再按informative/hard/easy反馈加权复访
争取6组有差异 + 1组易题 + 1组困难；不足时用当前新组补满8组
奖励r2；A=R−组均值；KL beta=.02；学习率1e-5
上下文3072；每次输出最多192token；温度.7；seed=20261006
DeepSeek训练复核并发16，结束D6评测并发100
```

输出根目录为`/root/autodl-tmp/training_runs/10-5_grpo`，运行名`full500-*`。本文件不含API key，不自动降低micro、不自动重训。两个预算是上限，不承诺64次有效更新；必须完成500项覆盖后才能正常停止。
