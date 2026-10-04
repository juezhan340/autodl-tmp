# browser_check.py 中文说明

```text
职责：实际浏览器验证桌面/手机布局、画布和轮询更新。
输入：展示页URL、截图及报告输出目录。
输出：真实等待页与隔离模拟训练页截图、browser_report.json及中文md。
读取：真实HTTP页面与只读状态API。
写入：默认仓库外output_root/monitor_checks，不写sft-main。
不负责：模型训练、GPU压力测试、向真实服务写虚构指标。
```

可选验证依赖Playwright 1.58.0与Chromium，训练及展示服务不依赖它。真实页分别检查1440、390、360、1920像素宽度，验证无横向溢出、无页面脚本异常、canvas非空。动态验证用Playwright路由在单个测试浏览器内替换API，检查step与loss自动刷新、三个epoch checkpoint展示、错误文本不作为HTML执行；模拟数据不会写入监控服务。

验证显式使用Playwright安装的完整Chromium可执行文件，以无界面模式运行，不依赖系统浏览器或额外headless-shell路径。

文字边界与分区重叠用浏览器几何测量检查，模拟训练曲线另检查真实绿色绘图像素，不仅检查canvas存在。轮询等待使用locator断言，兼容页面禁用unsafe-eval的CSP，不为测试放宽服务安全策略。

```bash
/root/autodl-tmp/sft-venv/bin/python -m pip install -r training/10-5_sft/requirements-browser.txt
/root/autodl-tmp/sft-venv/bin/python -m playwright install chromium
/root/autodl-tmp/sft-venv/bin/python training/10-5_sft/browser_check.py
```
