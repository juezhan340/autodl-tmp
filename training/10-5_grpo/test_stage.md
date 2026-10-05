# test_stage.py 中文说明

职责：CPU离线回归第一阶段选择、显式启动确认、只读状态投影、部分日志读取、奖励统计和原C+D6评测口径，不启动训练或GPU预测试。

```text
输入：pytest、stage1_config；选择测试读取服务器原划分
输出：6项通过/失败；其他机器缺原划分时明确skip
写入：pytest tmp_path内隔离的JSON/JSONL及说明
覆盖：100任务五类各20、16×1不降档、双确认、死亡进程、半行日志
      pending不进reward曲线、同分组比例、查询D6错与系统待审
不负责：GPU显存测量、收费API、正式模型生成和训练
```

运行：`/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_grpo/test_stage.py -q`。本轮训练中的真实更新另外验证持续optimizer、固定参考和非零后续KL。
