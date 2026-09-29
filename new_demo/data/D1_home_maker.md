# D1_home_maker.py

职责：
  从户型库抽一套房间，从设备库抽若干模板，生成 id、配对、命名，再随机初始 state。不用模型。

输入：
  抽样种子；可选两个库路径。

输出：
  s0：rooms[] + devices[]。种子不写进这份 JSON。

读取：
  D0_homes.jsonl（十五种户型，大中小各五）
  D0_devices.jsonl（二十一种设备）

写入：
  无。调用方决定是否落盘。

不负责：
  写 task、写用户指令、调 B。

对应文件：
  new_demo/data/D1_home_maker.py

配对规则：

```text
抽户型
  得到房间 room_id / display_name / room_kind
        |
        v
抽设备
  只挂 allowed_room_kinds 包含该房间的模板
  先保证：一台空调、一台传感器、至少两盏灯（优先可调光）
  房间允许再挂：冰箱、烤箱、洗碗机、热水器、洗衣机、电视、加湿器
        |
        v
生成
  device_id     device_{房间token}_{id_token}
                传感器前缀 sensor_
  display_name  房间中文名 + name_stem    例：卧室空调
  device.room_id = 该房间 room_id
  room.device_ids 追加这个 device_id
        |
        v
随机 state，输出 s0（不再带 room_kind）
```
