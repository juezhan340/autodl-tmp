# V2 闸 1 测试记录

日期：2026-09-28
命令：`python -m pytest new_demo -q`
工作目录：`/root/autodl-tmp`
结果：27 passed

```text
已过
  D1 抽样配对、种子不进 s0、户型不写死在 Python
  D4 T1 过、T2 keep 不打、T4 probe 必须失败、T5 inspect、缺 id 不合格
  PIPE 默认停在 D4_blueprints.jsonl
  失败草稿进 D34_failures，无 blueprint_id
  continue_from_d5 直接报错

未做
  D2 / D3 / D5 / D6
  DeepSeek 客户端
  提示词拷入 data_static（19 仍是审阅稿）
```
