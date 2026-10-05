# dashboard_server.py 中文说明

2026-10-06：每次读取active_run对应`run_config.json`，跟随新运行的500池配置，避免常驻页面沿用旧100配置。只公开stage_label和白名单参数以及聚合状态，不暴露场景、密钥或文件系统。监控进程独立于训练，重新拉起页面不影响训练。

职责：在`0.0.0.0:6008`提供独立只读GRPO页面。沿用SFT监控的HTTP白名单、状态轮询和nvidia-smi缓存模式，不加载Torch模型，不提供训练控制接口。

```text
输入：stage1_config.json；output_root/active_run.json
读取：活动运行的training_status、metrics、checkpoint_index、evaluation/comparison
输出：GET /、/api/status、/healthz；POST返回405
写入：无；进程日志由start.py保存
不负责：训练、奖励评审、修改数据、下载权重、暴露密钥或原轨迹
```

每3秒查询一次GPU，显示当前显存/利用率/温度和服务存活期间NVML观测峰值；离散采样峰值不能冒充连续精确峰值。进程身份不一致时把仍running的状态投影为interrupted。状态缺失显示未开始，绝不引用旧冒烟结果。

公网页面继续使用平台6008映射。页面只读聚合指标及简短奖励分项，没有路径下载接口。CSP限制所有资源为页面内代码与同源API。
