# gh_stars_shields.py 说明

功能：GitHub 官方 API 匿名配额被限流（403 rate limit exceeded）时的替代口径，
用 shields.io 的徽章 JSON 接口查 26 个小模型微调/RL 训练相关项目的 star 数。

```text
接口    https://img.shields.io/github/stars/<owner>/<repo>.json
返回    {"value": "75k"}（取整到 k，shields 自有缓存，通常几小时内更新）
```

输入：脚本内的 `REPOS` 列表（26 个项目，覆盖微调框架、RL 训练、推理/评测、早期 LoRA 样板）。

输出：`C:\Users\洛涧北府\AppData\Local\Temp\hf_analyze\gh_stars_shields.json`
（每个项目一条：`{"stars_text": "75k"}`），同时打印到控制台。

依赖：Python 3 标准库。

重跑方式：

```text
python gh_stars_shields.py
```
