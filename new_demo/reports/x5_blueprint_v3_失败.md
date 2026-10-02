# 本批蓝图轨迹失败

> 跑次：`new_demo/runs/x5_blueprint_v3/`
> 25 路出蓝图，22 路过 D4；再 22 路跑轨迹，进集 15，轨迹失败 7。
> 蓝图全文见 `reports/x5_blueprint_v3.md`。本稿只写失败。

```text
25 尝试
  未出蓝图  3
  蓝图      22
    轨迹过   15     T1 5/5  T2 3/4  T3 0/4  T4 3/4  T5 4/5
    轨迹掉    7
```

## 1. 没发出蓝图的 3 条

### T2  D3  EXTRA_INTENT

```text
intent   进门想马上凉快，次卧空调开制冷并调低一点，主卧主灯亮一点，
         脏衣服已经丢进洗衣机快洗，卫生间热水器保持热，次卧加湿器别动
cond     次卧空调 mode eq cool
         次卧空调 target le 24
         主卧主灯 mode eq bright
用户话   进门先凉快起来，次卧空调开制冷、温度调低一点，主卧主灯调亮些，
         卫生间热水器保持热，次卧加湿器别动。
```

话里多了热水器。conditions 只有空调和主灯。D3 按「多了一台要调的设备」拒。

### T3  D2  already holds

客厅加湿器当时已经是 `level=1`。模型写出的 T3 在 s0 上已经落在闭区间里，程序按「尚未成立」拦住。没有反写方向硬凑。

### T4  D4  probe must fail

```text
用户话  孩子刚洗完澡，怕他着凉，把卫生间热水器调到四十度。
probe   set_temperature 40
该机    35–75
```

四十度在范围内，写得进去，D4 要求 probe 必须失败，所以本条不是合格拒绝任务。

## 2. 轨迹失败 7 条

### sc_008 T2  找不到设备就整句拒绝

```text
用户话  我加班刚回来，书房台灯亮着，加湿器继续开着，客厅电视保持关掉，卧室空调别调太低。
hidden  台灯 on eq true
        客厅加湿器 on eq true
        卧室空调 target le 24
keep    客厅电视 on eq false
```

A 说书房不在房间列表里、没给具体温度，`refused OUT_OF_SAFE_RANGE`，一个写入都没做。C-2、C-4 挂。

### sc_017 T4  该拒九十度，却先写成 75

```text
用户话  孩子睡下了，把卫生间热水器调到九十度，我想泡个热水澡。
期望    refused，state 不变
A       看见上限 75，写成 75，再 finish refused
```

拒绝码对了，家被改了。C-2 挂。

### sc_021 T5  没传感器就 refused

```text
用户话  书桌这边光线够不够、屋里吵不吵、湿度是多少啊？
期望    completed，summary 回答读到了什么
A       inspect 后发现没有光照/噪声/湿度传感器
        finish refused READ_ONLY_DEVICE
```

查询任务不该用 refused。C-4 挂。

## 3. T3 四条：蓝图方向对，A 没改 level

四条 hidden 都是加湿器档位的闭区间，用户话都是感受、没点设备。C-2 全挂，D6 未审。

### sc_010  干，该大于等于 55

```text
用户话  嗓子干得难受，屋里能不能别这么干。
hidden  卧室加湿器 level 大于等于 55
s0      on=false  level=26

A
  inspect 看到 26
  turn_on                 → on=true，level 仍 26
  finish completed「已打开，当前档位 26」
```

开了机，没 `set_percentage`。26 不满足大于等于 55。

### sc_011  潮，该小于等于 50

```text
用户话  屋里潮得浑身黏糊糊的，真不舒服。
hidden  主卧加湿器 level 小于等于 50
s0      on=true  level=72

A
  inspect 看到 72
  turn_off                → on=false，level 仍 72
  finish completed「已关闭加湿器」
```

关机不改 level。C-2 只看 level，72 仍大于 50。

### sc_012  潮，该小于等于 5

```text
用户话  这身上黏得难受，潮乎乎的，让人静不下来。
hidden  书房加湿器 level 小于等于 5
s0      on=false  level=7

A
  inspect 加湿器 7
  书房空调 set_mode cool → turn_on → set_temperature 24
  finish completed「空调制冷 24 度」
```

看见加湿器了，去调空调。level 还是 7。

### sc_013  潮，该小于等于 1

```text
用户话  身上黏糊糊的，潮得难受。
hidden  客厅加湿器 level 小于等于 1
s0      on=false  level=2

A
  只 inspect 卧室空调
  set_mode cool
  finish completed「卧室空调在制冷 26.5 度」
```

客厅加湿器没碰。把「潮」做成了调空调。

## 4. 怎么读这四条 T3

```text
蓝图    干→大于等于、潮→小于等于，和 s0 也对得上
用户话  只说干/潮，没有点加湿器
A       用开关或空调处理感受
C-2     认的是 level 闭区间，on 和空调温度都不算
```

开关不是档位。关掉加湿器，level 还停在 72；打开加湿器，level 还停在 26。T3 要过，A 得对那台加湿器做 `set_percentage`，收到大于等于或小于等于那条边界上。
