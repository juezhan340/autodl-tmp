# V1 测试记录

日期：2026-09-28
命令：`python -m pytest new_demo/tests/C_test_run.py -q`
工作目录：`/root/autodl-tmp`
结果：16 passed

```text
B.reset 双向 id                 通过
B.reset 不译中文名               通过
B.reset 复制隔离                 通过
B.step 四工具 + finish 拒        通过
越界 / 只读传感器 / 未知 id      通过
发现链不是闸门                   通过
observation 无 task/库存         通过
C.run 每轮 1 工具                通过
纯文本不补 outcome               通过
C-1 协议                         通过
C-2 终态 / 拒绝未改写            通过
C-3 观察                         通过
C-4 finish 契约                  通过
summary-only：C-2 过 C-4 不过    通过
中间 UNKNOWN_DEVICE 可纠正       通过
十轮无 finish -> truncated       通过（本项用 max_turns=3）
```

未测：DeepSeek、D0–D6、SFT。那些属于 V2 及以后。
