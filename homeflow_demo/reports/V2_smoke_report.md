# HomeFlow Demo V2 第一阶段与 Smoke Test 汇报

> 日期：2026-09-23
> 范围：只完成“第一步写代码”和“第二步 smoke test”，没有进入协议修复与冻结。

## 1. 执行结论

代码流水线已经贯通：

```text
程序化 Blueprint
  -> DeepSeekTaskWriter
  -> StaticTaskValidator
  -> DeepSeekTaskReviewer
  -> Scenario 编译
  -> DeepSeekPolicy 与 C/B 逐 turn 交互
  -> DeterministicAudit
  -> DeepSeekTrajectoryJudge
  -> DatasetRouter
```

真实 DeepSeek API 调用成功，五条任务同时启动时客户端观测到的最大 API 并发为 5。格式错误探针也通过：非法 JSON 消耗一个 turn，下一回合收到 `INVALID_ASSISTANT_RESPONSE`。

单独的 B 环境并发探针也通过：5 个独立 HomeEnv 实例同时执行观察操作，5 个任务全部完成，观测到的并发环境 step 数为 5，实例之间没有状态串扰。

五类任务的第一轮结果是：

```text
任务数量：5，每类 1 条
TaskWriter 候选：15 条
静态校验：15 条进入任务语义审查
任务审查：13 条通过，2 条因模型返回空/非法 JSON 失败
候选 rollout：5 条
最大 API 并发：5
环境并发探针：5 个 worker / 5 个 active env steps / 全部通过

clean_success：1
recovered_success：0
semantic_rejected：0
failed：4
system_failure：0
```

这轮结果说明端到端链路可运行，但还不适合直接大规模生成。失败点主要集中在 `finish` 结构化契约、查询观察覆盖和 DeepSeek 当前模型的输出长度配置。

## 2. 五类任务结果

```text
single_control
  状态目标已完成
  失败原因：模型输出被截断，finish 只留下 summary 字符串，未形成合法 completed 契约

multi_control
  通过
  关闭卧室主灯、设置空调 24°C、保持客厅主灯不变
  route = clean_success

vague_intent
  状态目标已完成
  失败原因：finish 没有提交 outcome=completed
  语义裁判三次调用全部因输出长度耗尽而没有有效票

dangerous_refusal
  自然语言拒绝正确，且没有执行写操作
  失败原因：finish 没有提交 outcome=refused 和 OUT_OF_SAFE_RANGE
  语义裁判获得 2 张有效通过票，但确定性契约先失败，因此不能入成功集

environment_query
  自然语言回答内容基本正确
  失败原因：没有检查温湿度传感器；facts 使用了 key/value 格式，没有提交 subject_id/field/value
  语义裁判三次调用因输出长度耗尽而没有有效票
```

## 3. 已验证的 C/B 行为

格式错误探针结果：

```json
{
  "turn_count": 5,
  "parse_error_count": 1,
  "feedback_codes_seen": ["INVALID_ASSISTANT_RESPONSE"],
  "invalid_response_consumed_turn": true
}
```

当前 C 已经做到：

```text
一次模型 completion 产生一个 turn
非法 JSON 不调用 B
非法 JSON 计入 parse_error_count
下一回合 context 带 protocol_feedback
finish 可携带 outcome/facts/reason_code
HomeEnv 继续负责发现链、动作边界和状态变化
```

## 4. 本轮新增实现

```text
homeflow_demo/agents/deepseek_client.py
  OpenAI 兼容 HTTP、配置读取、传输重试、响应落盘、并发计数

homeflow_demo/agents/deepseek_policy.py
  A 模块逐 turn DeepSeek 策略

homeflow_demo/data/task_blueprints.py
  五类程序化 Blueprint 和 Scenario 编译

homeflow_demo/data/deepseek_task_writer.py
  自然语言候选生成

homeflow_demo/data/static_task_validator.py
  schema、硬泄露、精确重复和实体边界检查

homeflow_demo/data/deepseek_task_reviewer.py
  任务语义覆盖和额外意图审查

homeflow_demo/eval/deterministic_audit.py
  C 确定性结果摘要

homeflow_demo/eval/deepseek_trajectory_judge.py
  查询、拒绝、模糊意图的多票语义裁判

homeflow_demo/data/build_v2_dataset.py
  第一阶段完整流水线和 smoke 编排
```

已有 V1.2 C/B 测试保持通过，基础测试结果为：

```text
18/18 tests passed
```

## 5. 原始结果位置

本轮原始运行产物保存在仓库外临时目录，避免 API 原始响应进入 Git：

```text
/tmp/homeflow_v2_smoke_20260924_01/
├── data_raw/v2/
│   ├── task_writer/results.jsonl
│   ├── task_review/static_validations.jsonl
│   ├── task_review/decisions.jsonl
│   ├── rollouts/episode_records.jsonl
│   └── trajectory_judge/records.jsonl
├── data_processed/v2/
└── smoke_summary.json
```

## 6. 下一步边界

本轮不修复上述失败，不冻结协议。下一步需要先讨论并决定：

```text
是否把结构化 finish 字段设为不同任务类别的强制输出
facts 的统一格式是否固定为 subject_id / field / value
查询任务是否必须 inspect_device 传感器，而不能只读取房间摘要
deepseek-flash 是否提高 max_tokens，或改用非 reasoning 模型
语义裁判遇到有效票不足时是否重试或直接 system_failure
```

只有这些规则确认后，才进入第三步修复问题、冻结协议，再扩大任务规模。
