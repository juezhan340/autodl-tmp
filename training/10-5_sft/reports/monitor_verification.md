# 4×2配置与实时页面核验

本次只修改配置和运行展示服务，未重新运行GPU冒烟，未启动500条完整训练，未评测200条测试，未调用D6。

```text
正式配置：micro-batch 4 × 梯度累计2 = 有效batch 8
完整训练：3个epoch，每个都保存并保留完整checkpoint
页面：独立Linux会话，0.0.0.0:6008，每3秒读取真实进度
状态：尚未开始训练；旧smoke不作为正式进度
```

## 已核验

训练、验证、测试及备用集合的全部JSONL内容SHA-256与修改前完全一致，规模仍为500/100/200/194。旧数据manifest另存仓库外version_history，原始权重和旧smoke/checkpoint未修改。新manifest绑定4×2配置，默认check入口通过。

自动测试合计123项通过：训练数据及入口27项、实时监控10项、原new_demo86项。包括4×2参数、save_strategy=epoch、save_total_limit=None、优化器状态要求、只读路由、HEAD健康请求、无确认不得后台训练、PID复用识别、半行指标读取及NaN过滤。

页面进程PID与SID相同，PPID为1；启动工具退出后服务仍存活。页面未导入PyTorch，不加载权重；核验结束时GPU显存与利用率均为0。训练后台入口同样使用独立会话、断开标准输入及独立日志，但本次没有实际拉起完整训练进程。

本机页面、API与健康接口正常；用户提供的公网映射返回200，真实浏览器在公网页面成功读取4×2配置和“尚未开始训练”状态，并完成同源API轮询。

```text
本机：http://127.0.0.1:6008
公网：https://uu753393-afb3-4b7a916d.westd.seetacloud.com:8443
日志：/root/autodl-tmp/training_runs/10-5_sft/services/dashboard.log
```

## 浏览器核验

Playwright实际打开1440×1000、390×844、360×800、1920×1080页面，检查整页横向溢出、关键文字边界、分区重叠与canvas像素，均通过。隔离浏览器路由模拟训练状态，验证step从85自动刷新到86、loss随之更新、三个epoch checkpoint全部可见、错误文本不会作为HTML执行。模拟数据未写到真实服务或sft-main。

截图和完整浏览器JSON/同名md位于仓库外`/root/autodl-tmp/training_runs/10-5_sft/monitor_checks/`，含真实等待页、模拟曲线页和公网页面。曾尝试把截图交给模型查看，但当前图像工具拒绝图片输入；因此这里记录的是实际浏览器几何与像素检查，不宣称完成目视审查。

为浏览器核验额外安装了可选Playwright 1.58.0、Chromium、libgbm1/libasound2及Noto CJK字体，不更换PyTorch/CUDA，也不作为展示服务运行依赖。Python环境pip check通过。

## 尚未验证

4条最长轨迹并行时的实际训练峰值显存及吞吐没有测量；此前12.74 GiB属于旧2条轨迹冒烟。完整3个epoch训练的实际损失、显存与checkpoint会由训练回调落盘后展示。实例关机或平台强制清理仍会停止进程，独立会话不承担关机保活。
