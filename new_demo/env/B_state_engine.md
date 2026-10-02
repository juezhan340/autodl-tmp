# B_state_engine.py

职责：
  复制一份 home，提供四个家庭语义操作。发现链不是闸门。

输入：
  静态 Home；随后是 room_id / device_id / action / params。

输出：
  observe：只回房间 id 和名称，无设备、无温湿度、无台数
  inspect_room：该房间设备摘要，含 device_id
  inspect_device：完整 state 和 actions
  execute_action：成功则写 state，返回 state_after 和 state_diff

读取：
  内存里的房间和设备副本。

写入：
  只在 execute_action 校验通过后改副本 state。

不负责：
  处理 finish、读 task、翻译中文名。

对应文件：
  new_demo/env/B_state_engine.py

```text
observe_home 只含 rooms[].room_id / display_name
inspect_room 仍派生该房间温湿度摘要
inspect_device 稀疏，不补六个 null
未知房间     UNKNOWN_ROOM
未知设备     UNKNOWN_DEVICE
动作不存在   UNSUPPORTED_ACTION   夜灯调光、传感器写入走这条
参数越界     BAD_REQUEST          state 不变；finish 的 OUT_OF_SAFE_RANGE 不在这里
set_temperature 只改 target，范围看该设备 actions
set_percentage 只改 level：风扇、电视音量、台灯、加湿器
set_mode 改 mode：空调/洗衣机等，以及主灯 dim/bright
```
