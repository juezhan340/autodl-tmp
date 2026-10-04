# common.py 中文说明

```text
职责：配置读取、稳定指纹、原子文件写入、JSON配套中文说明。
输入：config路径、JSON/JSONL记录、文件路径。
输出：配置字典、SHA-256、JSON及同名md。
读取：本目录config.json，调用方指定的文件。
写入：调用方指定的仓库外产物或小型报告。
不负责：样本筛选、分词、模型加载、训练、评测。
```

相对路径固定到仓库根，避免启动位置改变数据来源。默认启用 Hugging Face 离线访问，不下载模型。JSON短数据完整展示在同名md；长manifest只展示结构，完整数据仍在JSON中。Trainer自行生成的JSON由`annotate_json_tree`补充说明。原子写入采用唯一临时文件名，避免不同写入者共用一份临时文件。
