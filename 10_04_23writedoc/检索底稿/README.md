# 检索底稿说明（小模型领域适配调研）

本文件夹是《小模型领域适配方法调研.md》的证据底稿，放三样东西：

```text
GRPO专项检索笔记.md    GRPO 专项的检索笔记：算法口径表、框架 star、1.5B~4B 复现项目、
                       小模型 RL 的坑与处置、三套超参方案。由子检索代理产出，
                       其中标注"未查证"的数字已在主文档里用 S2 核验补全。

脚本/                 两个一次性检索脚本（含同名 .md 说明）
  collect_evidence.py   OpenAlex 相关性检索 + Semantic Scholar batch 补引用数
  gh_stars_shields.py   shields.io 查 GitHub star（GitHub API 限流时的替代口径）

数据/                 脚本跑出来的原始证据 JSON（含同名 .md 说明）
  ev_candidates.json    563 篇候选论文（含引用数/年份/venue/arXiv ID）
  ev_classics.json      39 篇经典论文的精确引用数
  verify_final.json     小模型 RL 论文的核验结果（GSPO/Spurious Rewards/SimpleRL-Zoo 等）
  gh_stars_shields.json 26 个开源项目的 star 数（shields 口径）
```

两条使用提醒：

```text
1  引用数分两个口径：OpenAlex（免费、无 key，但对 arXiv 记录低估）
   和 Semantic Scholar（更准，但匿名限流严重，需走本机代理）。
   主文档里的所有引用数统一取 Semantic Scholar。
2  GitHub API 匿名配额是共享的，容易 403；shields 返回的是取整值
   （75k 表示 7.5 万量级），只用于分档。
```
