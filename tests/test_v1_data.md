# `tests/test_v1_data.py` 说明

## 功能

验证 V1.1 结构化数据和规则基线，不调用 DeepSeek API。

## 测试内容

```text
场景生成可复现
跨 split 场景 ID 不重复
schema 拒绝重复设备
规划器可以解决可行任务
规划器拒绝越界目标
Gym 风格适配器返回标准五元组
全部生成场景通过 schema
可行场景 Oracle 全部成功
不可行场景不伪造成功
query_then_control 计划顺序正确
四类设备控制命令和值域边界
初始状态字段和值域校验
已生成 V1 数据可重放验收
JSONL 轨迹可读写
Oracle 记录包含 v1.1-turn、turns 和 tool_events
```

## 运行方式

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```
