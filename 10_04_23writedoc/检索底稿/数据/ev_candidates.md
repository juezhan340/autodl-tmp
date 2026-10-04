# ev_candidates.json 数据说明

内容：小模型领域适配调研的候选论文池，563 篇（其中 541 篇带 arXiv/DOI、查到了引用数），按标题去重。

```text
每条的字段
  title          论文标题
  year           年份
  doi            DOI（没有则为空）
  arxiv          arXiv ID（从 landing page 里提取，没有则为空）
  venue          发表 venue（OpenAlex 口径）
  oa_citations   OpenAlex 引用数（低估，仅作参考）
  citations      Semantic Scholar 引用数（主文档统一用这个）
  s2_title       S2 返回的标题（用于核对是否同一篇）
  queries        命中该论文的检索词列表
```

使用方式：按 `citations` 降序就是"高引优先"的阅读清单；按 `queries` 分组
就是每个检索词的检索结果。数据量大（26 万字符），不适合全量人读，
主文档里已经筛出 100 余篇写成了分档榜单。
