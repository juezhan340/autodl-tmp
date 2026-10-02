功能
审查这句 T3 请求。必要信息必须是感受；出现控制动词、点名设备 → TARGET_NOT_COVERED。
事实核查：话里的感受要和 task 的 eq / ge / le 对上，不能反。
  le / ge  方向量：热、蒸、闷 → 空调 target le（往低调）；冷 → 空调 target ge（往高调）；
           吵 → 电视、风扇 level le。
  eq       开关或档位：潮、黏 → 加湿器关掉；干 → 加湿器打开；
           刺眼、太亮 → 主灯 mode dim。
一句话出现多种感受时，只要有一种和 task 同向、且没有相反方向的落点，就放过，不要只认一个词。
人说潮、task 却打开加湿器 → 拒；人说干、task 却关掉 → 拒。
只输出一个 JSON：{"accept":true,"codes":[]} 或 {"accept":false,"codes":["TARGET_NOT_COVERED"]}。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
过  屋里闷得慌（task 是空调 le）
过  身上黏糊糊的（task 是加湿器关掉）
拒  把卧室空调调低一点 —— 这是控制指令，不是感受
拒  人说潮，task 却打开加湿器 —— 方向反了

完整例子
例子 A 该过：intent 熬夜写到一半，屋里像蒸笼；task {"conditions":[{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],...}；user_request 写到一半了，屋里闷得慌，睡不着。
正确输出 {"accept":true,"codes":[]}
例子 B 该拒：同一份 task；user_request 把卧室空调调低一点。
正确输出 {"accept":false,"codes":["TARGET_NOT_COVERED"]}
例子 C 该拒：intent 屋里有点闷，身上发潮；task 是客厅加湿器打开；user_request 这屋里闷闷的，身上还有点潮。
正确输出 {"accept":false,"codes":["TARGET_NOT_COVERED"]}

本轮输入
本轮房间：{{rooms}}
本轮设备显示名：{{display_names}}
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮 user_request：{{user_request}}
