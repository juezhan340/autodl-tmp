# test_monitor.py 中文说明

```text
职责：回归实时指标、只读API、训练确认和进程身份。
输入：正式配置的临时副本、模拟Trainer事件、临时HTTP端口。
输出：pytest通过或失败结果。
读取：临时状态、指标与checkpoint索引。
写入：pytest临时文件，不写正式训练目录。
不负责：模型反向传播、真实GPU压力测试、完整训练。
```

测试覆盖未开始状态不混入smoke、每step进度与loss落盘、半行读取、NaN过滤、PID复用、中断展示、三个epoch索引及路径隐藏、HTTP路径白名单、POST拒绝、后台训练确认开关和服务健康识别。真实浏览器布局与动态更新另见reports/monitor_verification.md。

HEAD健康探测确认返回200且无正文，兼容实例转发侧的HTTP探测。
