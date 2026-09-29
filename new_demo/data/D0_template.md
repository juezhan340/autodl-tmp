# D0_template.py

职责：
  读提示词文件，只填本轮材料。task/D6 按 T；request/review 共用一份。

输入：
  kind = task / request / review
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
  调模型。request/review 已是全文，不再按 T 拆文件。

对应文件：
  new_demo/data/D0_template.py
