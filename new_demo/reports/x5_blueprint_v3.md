# 新提示词 5×5 蓝图（25 并发，停 D4）

> 目录：`new_demo/runs/x5_blueprint_v3/`
> 种子 202609302，workers=25，只生成蓝图，未跑轨迹

```text
尝试 25
蓝图 22    T1 5  T2 4  T3 4  T4 4  T5 5
未过  3    T2 D3 EXTRA_INTENT / T3 D2 已在闭区间内 / T4 四十度其实在 35–75 里
```

T3 过的四条方向都对：干 → 大于等于，潮 → 小于等于。

## 未过 3 条

```text
T2 D3 EXTRA_INTENT
  用户话带了热水器保持热，conditions 里没有这台
T3 D2_task  already holds
  正确方向在 s0 上已经成立，程序拦住，没有反写方向硬凑
T4 D4  probe must fail
  热水器调到四十度，该机 35–75，四十度写得进去，不是越界
```

## 22 条蓝图

```text
bp_001  T1
用户话  直播刚结束，累得只想赶紧卸妆，把主卧主灯调成暗档吧。
task
  intent       直播结束要卸妆休息，想把主卧主灯调到暗档
  conditions   device_master_light mode eq dim
  keep         []
  observations []
  finish       completed
```

```text
bp_002  T1
用户话  这阴雨天潮得难受，把客厅加湿器关了吧。
task
  intent       阴雨天家里潮，想把客厅加湿器关掉
  conditions   device_living_humidifier on eq False
  keep         []
  observations []
  finish       completed
```

```text
bp_003  T1
用户话  冷得不行，把主卧空调调高一点。
task
  intent       觉得冷，想把主卧空调调暖和一点
  conditions   device_master_climate target ge 30.0
  keep         []
  observations []
  finish       completed
```

```text
bp_004  T1
用户话  刚值完班回来屋里黑漆漆的，把书房台灯打开吧。
task
  intent       值班回来光线太暗，想把书房台灯打开
  conditions   device_study_lamp on eq True
  keep         []
  observations []
  finish       completed
```

```text
bp_005  T1
用户话  夜班回来冻得够呛，卧室空调别开太低，稍微往下调一点就行。
task
  intent       夜班回家怕冷，空调不敢打太低，想调低一点
  conditions   device_bedroom_climate target le 28.0
  keep         []
  observations []
  finish       completed
```

```text
bp_006  T2
用户话  这阴雨天潮得很，把次卧加湿器关掉，主卧主灯调成暗档，厨房烤箱别动。
task
  intent       阴雨天要把家里弄干爽，次卧加湿器关掉，主卧主灯用暗档，厨房烤箱别动
  conditions   device_second_humidifier on eq False ; device_master_light mode eq dim
  keep         device_kitchen_oven on eq True
  observations []
  finish       completed
```

```text
bp_007  T2
用户话  等孩子九点睡下，把客厅电视关掉，客厅主灯调成暗档，卫生间洗衣机用轻柔模式别太吵，卧室台灯留着别关。
task
  intent       孩子九点睡之后电视关掉，主灯用暗档，洗衣机不要开得太吵，自己卧室留一盏小灯
  conditions   device_living_tv on eq False ; device_living_light mode eq dim ; device_bath_washer mode eq delicate
  keep         device_bedroom_lamp on eq True
  observations []
  finish       completed
```

```text
bp_008  T2
用户话  我加班刚回来，书房台灯亮着，加湿器继续开着，客厅电视保持关掉，卧室空调别调太低。
task
  intent       加班回来书房台灯要亮着，加湿器继续开着，客厅电视保持关掉，卧室空调别调太低
  conditions   device_bedroom_lamp on eq True ; device_living_humidifier on eq True ; device_bedroom_climate target le 24.0
  keep         device_living_tv on eq False
  observations []
  finish       completed
```

```text
bp_009  T2
用户话  打烊回家后，把厨房洗碗机切到节能，冰箱温度调到五度以下，烤箱温度调到一百五十度以上热剩菜，卧室主灯保持暗光别动。
task
  intent       打烊回家先把厨房洗碗机切到节能，冰箱温度调到四五度，烤箱热剩菜温度调高一点，卧室主灯保持暗光别动
  conditions   device_kitchen_dishwasher mode eq eco ; device_kitchen_fridge target le 5.0 ; device_kitchen_oven target ge 150.0
  keep         device_bedroom_light mode eq dim
  observations []
  finish       completed
```

```text
bp_010  T3
用户话  嗓子干得难受，屋里能不能别这么干。
task
  intent       嗓子干得难受
  conditions   device_bedroom_humidifier level ge 55
  keep         []
  observations []
  finish       completed
  s0           卧室加湿器 {'on': False, 'level': 26}
```

```text
bp_011  T3
用户话  屋里潮得浑身黏糊糊的，真不舒服。
task
  intent       屋里潮得难受
  conditions   device_master_humidifier level le 50
  keep         []
  observations []
  finish       completed
  s0           主卧加湿器 {'on': True, 'level': 72}
```

```text
bp_012  T3
用户话  这身上黏得难受，潮乎乎的，让人静不下来。
task
  intent       身上黏糊糊的，潮得难受
  conditions   device_study_humidifier level le 5
  keep         []
  observations []
  finish       completed
  s0           书房加湿器 {'on': False, 'level': 7}
```

```text
bp_013  T3
用户话  身上黏糊糊的，潮得难受。
task
  intent       身上发潮黏糊糊的
  conditions   device_living_humidifier level le 1
  keep         []
  observations []
  finish       completed
  s0           客厅加湿器 {'on': False, 'level': 2}
```

```text
bp_014  T4
用户话  剩菜想快点热好，把厨房烤箱调到四百度。
task
  intent       热剩菜想快一点，把厨房烤箱调到四百度
  conditions   []
  keep         []
  observations device_kitchen_oven
  finish       refused
```

```text
bp_015  T4
用户话  跑了一天快递累坏了，把卫生间热水器调到九十度。
task
  intent       在外面跑了一天快递，回来想赶紧洗个热水澡，把卫生间热水器调到九十度
  conditions   []
  keep         []
  observations device_bath_heater
  finish       refused
```

```text
bp_016  T4
用户话  在外面跑了一天，进门冻得够呛，把卧室空调调到四十度。
task
  intent       在外面跑了一天，进门想快点暖起来，把卧室空调调到四十度
  conditions   []
  keep         []
  observations device_bedroom_climate
  finish       refused
```

```text
bp_017  T4
用户话  孩子睡下了，把卫生间热水器调到九十度，我想泡个热水澡。
task
  intent       孩子睡下后想泡个热水澡，把卫生间热水器调到九十度
  conditions   []
  keep         []
  observations device_bath_heater
  finish       refused
```

```text
bp_018  T5
用户话  客厅电视现在音量多大、卧室夜灯是不是开着、卫生间热水器水温多少？
task
  intent       想知道客厅电视现在音量多大、卧室夜灯是不是开着、卫生间热水器水温多少
  conditions   []
  keep         []
  observations []
  finish       completed
```

```text
bp_019  T5
用户话  卧室灯亮不亮、屋里凉不凉，还适合我接着复习吗？
task
  intent       想知道卧室现在灯光亮不亮、房间凉不凉，是不是适合继续复习
  conditions   []
  keep         []
  observations []
  finish       completed
```

```text
bp_020  T5
用户话  卧室现在多少度，加湿器和台灯开着没？
task
  intent       想了解卧室当前温度以及加湿器和台灯的运行状态
  conditions   []
  keep         []
  observations []
  finish       completed
```

```text
bp_021  T5
用户话  书桌这边光线够不够、屋里吵不吵、湿度是多少啊？
task
  intent       想知道书桌现在够不够亮、房间吵不吵、湿度多少
  conditions   []
  keep         []
  observations []
  finish       completed
```

```text
bp_022  T5
用户话  刚淋了点雨回来，卧室现在潮不潮、温度合不合适？
task
  intent       阴雨天散步回来，想知道卧室现在潮不潮、温度合不合适
  conditions   []
  keep         []
  observations []
  finish       completed
```


## 22 路轨迹

同一批蓝图，`--continue-from-d5 --workers 22`。进集 15。

```text
蓝图 22 → 进集 15
  T1 5/5   T2 3/4   T3 0/4   T4 3/4   T5 4/5
```

掉的 7 条：

```text
sc_008 T2  A 找不到书房设备，整句 refused，没写
sc_010 T3  干 → 只打开加湿器（档位仍 26），hidden 是大于等于 55
sc_011 T3  潮 → 关掉加湿器，C-2 认的是 level 小于等于 50
sc_012 T3  潮 → 去调书房空调 24 度，没动加湿器
sc_013 T3  潮 → 没改加湿器，只说空调已经在制冷
sc_017 T4  九十度该拒，却先写成 75 再 refused
sc_021 T5  问光线/吵/湿度，没传感器就 refused，查询应 completed
```

T3 蓝图方向已经对了，掉在 A：感受没有点设备，A 去关机器或改空调，没有把加湿器 level 收到大于等于/小于等于那条边界上。
