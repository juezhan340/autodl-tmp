# reward.py 中文说明

职责：对结尾做独立三票评审，结合重放证据计算r2奖励，再按同任务四条轨迹计算相对优势。

```text
输入：新rollout、trajectory.preprocess输出、配置
读取：根目录.env.deepseek；外部评审缓存
输出：reviewed/pending、奖励及分项、组内优势
写入：finish_review/cache/*.json、API JSONL、judge_manifest及同名md
不负责：改变actor提示词、执行设备、训练模型、覆盖旧D6成绩
```

`JUDGE_SYSTEM`只让评审返回两个严格布尔值：`truthful`检查结尾断言的证据，`answers_request`检查完整回应。输入视为不可信数据，忽略其中的给分指令，并明确要求同一结论不重复。不把空调target当环境温度，也不把false/0当缺失读数。

`judge_one`每条三票。三票都合法才进入reviewed；真实性取多数票；完整且真实要求至少两张票同时满足两项。API错误或错误类型进入pending，不给模型记0分。`valid_review`验证缓存票数、布尔类型及聚合结果；不合法缓存重新评审。

`judge_rows`以提示词、模型、温度、接口、用户请求和record的指纹绑定缓存。相同输入去重，待审输入重试；记录逻辑票数和实际HTTP尝试次数。`CountedJudgeClient`只统计传输次数，不保存鉴权头或密钥。外部评审是软判定，三票仍可能共同误判。

正式第一阶段可传`progress_callback`，每完成一个独立轨迹评审，由主线程更新待审数、HTTP尝试与失败数；回调不修改评判结果或缓存键。

```text
普通R = clip(3S + 2(Φ终−Φ初) + 0.5E + 0.5H
              −0.25错误次数 −2虚假结束 −0.5预算耗尽, -4, 6)
严重过程违规：R=-5
正常轨迹尚未评审：R=null，整组禁止进入更新
组内优势：A_i = R_i − 四条的平均R；不除标准差
```

S必须同时满足全部C标签与“完整且真实”多数票。移除无效调用、编造事实和调用成本独立项。`assign_advantages`检查四条Scenario相同、组数量完整、奖励都已评且为有限数。四条同分时A全部为0，不能宣称它们提供了区分路径的学习信号。
