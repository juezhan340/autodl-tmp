# rollout.py 中文说明

职责：沿用当前A/B/C交互生成四条独立轨迹，并记录训练可以原样重算的token序列。

```text
输入：一个训练Scenario、共享policy、tokenizer、生成配置
读取：现行A_policy、EpisodeRunner、B环境
输出：四条rollout；input_ids/generated_ids；完整上下文与policy_mask
写入：无；调用方负责落盘
不负责：奖励、参数更新、额外few-shot装配、载入第二份基座
```

`generate_group`创建四个episode，每个独立reset环境及会话。`ActorClient`把现有A_policy的请求交给`BatchService`，保留原提示词及内嵌示例；不额外套三条few-shot。唯一GPU线程收集最多四个请求，80ms等待窗口后生成，所有Future按原请求路由。四个任务组目前顺序执行，共16条轨迹，不能说成16路GPU并行。结束必须`close()`并join线程。

`HFBackend.generate`左padding批量生成，温度0.7、top_p=1、top_k=0；每次最多192新token，整段采样上下文最多3072。截去EOS之后的padding，保留真正采样出的EOS。记录每批大小、前缀长度、生成长度、耗时。动态批次后半程可能不足4，本次检查至少确实出现过4路批次。

`pack_calls`用最后一次真实前缀和生成token构造完整序列，并验证前面每次采样前缀与输出都逐token一致。观察回执与system/user保持attention=1，但loss mask=0；只有实际助手采样token，包括实际EOS，mask=1。未采样的合成错误文本和模板收尾不作为策略目标。前缀不一致或空轨迹报错，不重新编码“差不多”的文本凑训练数据。

上下文预算耗尽单独记agent预算终止；网络、模型或生成线程异常记录为基础设施错误，整次更新中止，避免把服务器故障当成模型行为罚分。
