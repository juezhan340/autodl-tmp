# C_test_run.py

职责：
  V1 出门测试。手写 Scenario，用 ScriptPolicy，不调 DeepSeek。

输入：
  测试内构造的两房四设备 home。

输出：
  pytest 断言。在 V1 项之外补 observe 瘦身、冰箱拒绝、T5 只 observe 不算观察。

读取：
  new_demo.env / new_demo.eval / new_demo.agents

写入：
  无。

不负责：
  D0–D6 管线、API、SFT。

对应文件：
  new_demo/tests/C_test_run.py

覆盖：

```text
B.reset 双向 id、不译中文名、复制隔离
B.step 四工具、finish 拒、越界、只读传感器、发现链不是闸门
observation 无 task、无设备库存
C.run 每轮 1 工具；两个工具不执行
纯文本不补 outcome
C-1..C-4：completed 全过、summary-only、拒绝（C-2 不冻整屋）、keep 被破坏、缺观察、截断
中间 UNKNOWN_DEVICE 后来改对仍可通过
facts 进 finish 是形状错误，C-4 失败
```
