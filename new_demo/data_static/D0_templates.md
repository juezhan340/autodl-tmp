# D0_templates/

职责：
  存放已经定稿的提示词。D2-1、D2-2、D3、D6 都按 T 分文件。

```text
按任务族（D2 第一次）
  T1_single_control.md … T5_environment_query.md

用户指令（D2 第二次，按 T）
  D0_request_T1.md … D0_request_T5.md

D3 审指令（按 T）
  D3_review_T1.md … D3_review_T5.md

D6
  D6_T3.md D6_T4.md D6_T5.md

A
  A_policy.md

运行时只做
  读对应 T 的文件
  把 {{persona}} {{s0}} {{intent}} {{task}} {{display_names}} {{user_request}}
     {{rooms}} {{category}} {{finish}} {{turns}} {{tools}} 换成这一轮的值
  A_policy.md 只在第一轮填 {{tools}}，后面不再渲染
```

不负责：调模型、选 T、写死户型。
对应目录：new_demo/data_static/D0_templates/
