# D0_template.py

职责：
  读提示词文件，只填本轮材料。task / request / review / D6 都按 T 分文件。

输入：
  kind = task / request / review / d6
  category = T1 或 single_control
  values = 这一轮的 dict

输出：
  一整段可以发给 DeepSeek 的正文。

读取：
  data_static/D0_templates/ 下固定 md
  data_static/D0_personas.jsonl

写入：
  无。

不负责：
  调模型。

对应文件：
  new_demo/data/D0_template.py
