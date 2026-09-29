# `homeflow_demo/tests/test_env_v1_2.py` 说明

## 覆盖范围

```text
observe_home 不返回 device_id
真实 room_id / device_id 可以直接 inspect 和 execute
不存在的 id 才返回 UNKNOWN_*
只读传感器拒绝写入且状态不变
越界、NaN、Infinity 参数失败时无部分写入
snapshot/fork 后子环境写入不影响父环境
observation 不泄露隐藏目标和 elapsed_ms
恶意非字符串引用只返回 schema 错误，不触发 TypeError
畸形 ToolCall 字段类型返回 BAD_REQUEST 统一外壳
```

输入使用 `demo_scenario.py`，输出为标准 `unittest` 断言结果。
