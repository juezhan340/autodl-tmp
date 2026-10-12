# calc_token_stats.py

职责：
  统计 quota200_20261004_v2 数据集里单条轨迹的 token 长度（SFT 消息口径）。

输入：
  new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl（1000 行）
  tokenizer：D:\D_program\models\Qwen2.5-1.5B-Instruct（本地加载）

输出（stdout JSON）：
  行数、工具表/模板一致性、输入 token 统计、监督 token 统计、原始行字符数、分类均值。

读取：
  D0_template.build_a_prompt、B_tool_schema.available_tools、本地 tokenizer。

写入：
  无（只打印）。

不负责：
  不落盘缓存、不改数据集。

对应文件：
  _research_tmp/calc_token_stats.py

口径说明：
  消息构造与 training/10-5_sft/data.py 的 reconstruct_messages 一致；
  监督 token 用同款 generation 模板划定 assistant 区域，逐条校验渲染文本与官方模板一致。
