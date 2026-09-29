# B_schema.py

职责：
  reset 前静态校验。房间 device_ids 与设备 room_id 必须双向配对。不对、不补、不把中文名译成 id。
  参数范围以该设备自己的 actions 为准，不用全局空调法。

输入：
  场景字典或已构造的 Scenario。

输出：
  通过则返回 Scenario；失败抛 SchemaValidationError，消息里列出全部错误。

读取：
  无。

写入：
  无。

不负责：
  执行工具、翻译 display_name、抽样户型。

对应文件：
  new_demo/env/B_schema.py

会拦下的典型错误：

```text
房间挂了客厅灯，灯的 room_id 却是卧室
task 里塞了 user_request
expected_finish 出现 facts 或 answered
传感器 actions 非空
空调 target=180（超出该台 7–32）
烤箱 mode=cool（不在该台 enum）
夜灯带 set_percentage 却没有 state.level
```
