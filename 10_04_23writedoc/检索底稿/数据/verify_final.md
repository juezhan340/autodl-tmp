# verify_final.json 数据说明

内容：终稿前的一批核验结果，主要补小模型 RL 方向的论文引用数与智能家居侧
论文的存在性核对（Semantic Scholar 口径，2026-10-05）。

```text
论文                                              arXiv        引用数
──────────────────────────────────────────────────────────────────
SimpleRL-Zoo: Zero RL for Open Base Models        2503.18892    564
RL for Reasoning in Small LLMs: What Works        2503.16219     78
GSPO: Group Sequence Policy Optimization          2507.18071    720
The Entropy Mechanism of RL for Reasoning LLMs    2505.22617    452
Spurious Rewards: Rethinking Training Signals     2506.10947    228
ProRL: Prolonged RL Expands Reasoning             2505.24864    179
VAPO                                              2504.05118    263
Does RL Really Incentivize Reasoning Capacity     2504.13837   1097
Towards Privacy-Preserving Smart Homes (SLM)      2507.08878      7
SAGE: Smart Home Agent with Grounded Execution    2311.00772     24
```

另外核到的负结果（用于排除错误引用，不要写进论文）：

```text
2504.09566 是 "Syzygy of Thoughts"，不是 SimpleRL-Zoo
2502.16902 / 2412.13655 不是 HomeBench
HomeBench 的正确出处：ACL 2025 long paper，
DOI 10.18653/v1/2025.acl-long.597（OpenAlex 仅 3 次引用，S2 未单独核）
```
