# collect_evidence.py 说明

功能：为"小模型领域适配"调研收集论文证据。分两步：

```text
步骤 A  OpenAlex 相关性检索（直连，无代理）
        16 个检索词 × 每词前 50 条，按标题归一化去重，
        产出候选池（标题/年份/DOI/arXiv ID/venue/OpenAlex 引用数）

步骤 B  Semantic Scholar batch 接口（走本机代理 127.0.0.1:7897）
        把候选池 + 39 篇指定经典论文按 100 个一批 POST 查引用数，
        429 时按 12s 起步退避重试，最终把 S2 引用数并回候选记录
```

输入：脚本内的 `QUERIES`（16 个检索词）和 `CLASSICS`（39 篇必引论文的 arXiv ID）。

输出（写到 `C:\Users\洛涧北府\AppData\Local\Temp\hf_analyze\`）：

```text
ev_candidates.json   去重后的候选论文池（约 570 篇）
ev_by_query.json     每个检索词按引用数排序的前 15 条
ev_classics.json     39 篇经典论文的精确引用数（S2 口径）
```

依赖：Python 3 标准库（urllib/json）、本机代理 7897 端口在跑（S2 必须走代理，否则 429）。

重跑方式：

```text
python collect_evidence.py
```

注意：脚本里的 PROXY/MAILTO 是写死的本机值；换机器要改这两处。
