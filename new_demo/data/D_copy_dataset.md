# D_copy_dataset.py

职责：只读总表，C 全过且 D6 为对或跳过的复制进 D_dataset.jsonl。
不改总表。两次落盘（D_dataset.jsonl、D_manifest.json）带 OSError 重试
（Windows 高频重写同一文件偶发 EINVAL）。
对应文件：new_demo/data/D_copy_dataset.py
