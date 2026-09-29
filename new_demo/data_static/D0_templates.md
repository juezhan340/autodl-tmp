# D0_templates/

职责：
  存放已经定稿的提示词。D2-1 按 T 分文件；D2-2 和 D3 各一份全文，不按 T 拆。

```text
按任务族（D2 第一次）
  T1_single_control.md … T5_environment_query.md

用户指令（D2 第二次，共用）
  D0_request.md

D3 审指令（共用）
  D3_review.md

D6
  D6_T3.md D6_T4.md D6_T5.md

A
  A_policy.md

运行时只做
  读对应文件
  把 {{persona}} {{s0}} {{intent}} {{task}} {{display_names}} {{user_request}} 换成这一轮的值
```

不负责：调模型、选 T、写死户型。
对应目录：new_demo/data_static/D0_templates/
