# D0_devices.jsonl

职责：
  二十一种设备和传感器能力模板。符合 B 的 kind / device_type / actions / state。不绑定某一间房。范围写在该条 actions 里。

```text
灯 light
  主灯    on + mode dim/bright，set_mode；没有 level
  台灯    on + level，set_percentage 0–100
  廊灯、阳台灯、厨灯、浴灯、夜灯     只有 on

空调 / 风
  空调 climate          7.0–32.0
  风扇、排气扇 fan

开关
  墙开关 switch

家电
  电视 tv
  热水器 water_heater   35–75
  洗衣机 washer
  洗碗机 dishwasher
  烤箱 oven             50–250
  冰箱 refrigerator     2–8
  加湿器 humidifier     只有 on，开关

传感器 actions=[]
  温湿度 / 温度 / 湿度
```

每条有 catalog_id、id_token、name_stem、kind、device_type、allowed_room_kinds、state、actions。同一盏灯不能同时公开 set_mode 和 set_percentage。

读取：D1。写入：人工维护。不负责：生成 device_id。
对应文件：new_demo/data_static/D0_devices.jsonl
