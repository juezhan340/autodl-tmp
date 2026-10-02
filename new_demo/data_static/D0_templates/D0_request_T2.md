功能
代用户写一句家里的口语请求。conditions 有几条，话里就要有几处对得上的必要信息；keep 再带一截「某某别动」。
每截按那条 condition 的 operator 说话：eq 说精确目标，ge / le 只说方向，不要念数字。
可以加与设备无关的闲话，让句子自然；闲话不是多出来要调的设备。
不要出现 device_id、action 名、field、operator。
不要让 conditions 或 keep 里没有的设备变成要做的事。只输出这一句话。

示例说明：小例子与完整例子都只是示例，不是输出范围；不要把你的输出限制在例子涉及的设备类型或用户请求上，按本轮输入重新选。

小例子
对  电视关掉 + 空调调低一点 + 加湿器别动
错  少说「加湿器别动」
错  空调 le 说成「调到二十六度」
错  电视 eq 说成「声音小一点」
错  多带一台本轮没让动的设备

完整例子
intent：合租怕吵到别人，只想客厅安静、卧室凉一点，加湿器别动
task：{"intent":"合租怕吵到别人，只想客厅安静、卧室凉一点，加湿器别动","conditions":[{"device_id":"device_living_tv","field":"on","operator":"eq","value":false},{"device_id":"device_bedroom_climate","field":"target","operator":"le","value":27.0}],"keep":[{"device_id":"device_bedroom_humidifier","field":"on","operator":"eq","value":false}],"required_observations":[],"expected_finish":{"outcome":"completed","allowed_reason_codes":[]}}
可用显示名：卧室主灯、卧室空调、卧室加湿器、卧室温湿度传感器、客厅电视
正确输出：我先歇一会儿，把客厅电视关掉，卧室空调调低一点，卧室加湿器别动。

本轮输入
本轮 intent：{{intent}}
本轮 task：{{task}}
本轮可用显示名（display_name）：{{display_names}}
