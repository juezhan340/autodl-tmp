# `homeflow_demo/tests/test_env_v1_2.py` 说明

## 覆盖范围

```text
真实 room_id 在 observe_home 前不可直接访问
真实 device_id 在 inspect_room 前不可直接访问
设备 action 在 inspect_device 前不可执行
只读传感器拒绝写入且状态不变
越界、NaN、Infinity 参数失败时无部分写入
snapshot/fork 继承发现状态且运行状态相互隔离
observation 不泄露隐藏目标和 elapsed_ms
恶意非字符串引用只返回 schema 错误，不触发 TypeError
畸形 ToolCall 字段类型返回 BAD_REQUEST 统一外壳
```

输入使用 `demo_scenario.py`，输出为标准 `unittest` 断言结果。
