# D4_oracle.py

职责：
  第一步打分的可行性关。复制 s0 打 B，只看每次 ok / error.code。不调大模型，不走 C.run。

输入：
  home、task、T4 才有的 probe。

输出：
  OracleResult。过：ok=true。不过：error_code，无 blueprint_id。

读取：
  副本上的 B.reset / B.step。打完丢副本，原来的 s0 不动。

写入：
  无。编号和 jsonl 由编排在停闸前写。

不负责：
  审用户指令、发 sc_*、看终态是否满足 conditions（那是 C-2）、打 keep。

对应文件：
  new_demo/data/D4_oracle.py

```text
eq     写成目标值
ge/le  按当前值加减一档；顶到 min/max 则失败
T2     每条 condition 各打一次，keep 不打
T4     probe 必须失败且 state 不变
T5     空观察过；若仍列出观察则 inspect，不 execute
operator 只认 eq/ge/le
主灯 mode 走 set_mode；台灯 level 走 set_percentage
```
