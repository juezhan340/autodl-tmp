# D6_judge.py

职责：只审 C 四步全 true 且 D6=待审 的 T3/T4/T5。三票，对占多数才过。解析失败不记成错。
输入：总表一条。输出：写回 d6 与 d6_votes。
读取：D6_T3/T4/T5 固定提示词。写入：无，PIPE 回写总表。
不负责：当 A、覆盖 C 标签、重跑 B。
对应文件：new_demo/data/D6_judge.py
