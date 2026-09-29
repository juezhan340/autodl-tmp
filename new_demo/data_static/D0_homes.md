# D0_homes.jsonl

职责：
  十五种户型，大中小各五。只存房间和大小，不挂设备。

```text
small
  ht_small_1  卧室、客厅
  ht_small_2  卧室、客厅、卫生间
  ht_small_3  卧室、书房
  ht_small_4  卧室、厨房、卫生间
  ht_small_5  卧室、客厅、书房

medium
  ht_medium_1  卧室、客厅、厨房、卫生间
  ht_medium_2  主卧、次卧、客厅、卫生间
  ht_medium_3  卧室、客厅、书房、厨房、走廊
  ht_medium_4  主卧、客厅、厨房、卫生间、阳台
  ht_medium_5  卧室、客厅、厨房、卫生间、书房

large
  ht_large_1  主卧、次卧、客厅、厨房、卫生间、书房
  ht_large_2  主卧、次卧、客厅、厨房、卫生间、阳台
  ht_large_3  主卧、次卧、客厅、厨房、卫生间、书房、走廊
  ht_large_4  主卧、次卧、客厅、厨房、卫生间、书房、阳台
  ht_large_5  主卧、次卧、三卧、客厅、厨房、卫生间
```

每条有 home_template_id、size、rooms[]。房间字段是 room_id、display_name、room_kind。没有 device_ids。room_kind 仍是 bedroom / living / kitchen / bath / study / corridor / balcony。三卧的 room_id 是 room_third，kind 仍是 bedroom。

读取：D1。写入：人工维护。不负责：实例化 s0。
对应文件：new_demo/data_static/D0_homes.jsonl
