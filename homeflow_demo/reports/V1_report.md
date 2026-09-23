# HomeFlow Demo V1.1 验收报告

> 验收日期：2026-09-22
> 版本：V1.1
> 目标：在 V1 环境基础上完成模型 turn-level 决策步、工具事件审计和 V1.1 数据轨迹交付

## 1. 版本目标

```text
结构合法的场景能够进入 HomeEnv
动作和值域边界能够被统一校验
规则规划器能够生成可验证成功轨迹
train、val、eval 能够固定 seed 重建
Oracle 轨迹能够重新送入 HomeEnv 验证
一个 assistant turn 内的多个工具调用只产生一条策略 transition
不依赖 DeepSeek API
```

## 2. 实际交付

```text
环境层
  homeflow_demo/env/schema.py
  homeflow_demo/env/tool_schema.py
  homeflow_demo/env/home_env.py
  homeflow_demo/env/gym_adapter.py

数据层
  homeflow_demo/data/scenario_generator.py
  homeflow_demo/data/planner.py
  homeflow_demo/data/trajectory_format.py
  homeflow_demo/data/build_v1_dataset.py
  homeflow_demo/data/validate_v1_dataset.py

说明文档
  各 .py 文件对应的同名中文 .md 文件

测试
  tests/test_home_env.py
  tests/test_v1_data.py
  tests/test_home_env.md
  tests/test_v1_data.md

数据
  homeflow_demo/data_processed/v1/scenarios_train.jsonl
  homeflow_demo/data_processed/v1/scenarios_val.jsonl
  homeflow_demo/data_processed/v1/scenarios_eval.jsonl
  homeflow_demo/data_processed/v1/oracle_trajectories_train.jsonl
  homeflow_demo/data_processed/v1/oracle_trajectories_val.jsonl
  homeflow_demo/data_processed/v1/oracle_trajectories_eval.jsonl
  homeflow_demo/data_processed/v1/manifest.json
```

## 3. 关键设计结果

```text
HomeEpisodeEnv
  -> schema 校验
  -> tool_schema 动作校验
  -> StateEngine 状态转移
  -> predicates 完成度计算
  -> reward、terminated、truncated
  -> turn-level trajectory 记录
```

模型决策步和工具执行步分层：

```text
AssistantTurn
  -> Action_0, Action_1, ...
  -> ToolEvent_0, ToolEvent_1, ...
  -> 一条 RL transition
```

`Action` 仍保留为原子工具动作；`max_turns` 统计 assistant 输出次数；`max_tool_calls_per_turn` 单独限制一次输出包含的工具调用数。

V1 的 Gym 风格接口只作为适配层存在。核心训练和数据生成可以直接使用 `HomeEpisodeEnv`，后续传统 RL 工具或环境检查器可以通过 `GymHomeEnvAdapter` 接入。

HomeEnv 的目标谓词保留在环境内部，不进入 observation。Oracle、教师模型和训练器只能提交动作，最终成功状态由 HomeEnv 判断。

## 4. 数据统计

```text
固定 seed：20260921

train：80 个场景，67 个可行，13 个不可行，67 条 Oracle 成功轨迹
val：  20 个场景，17 个可行，3 个不可行，17 条 Oracle 成功轨迹
eval： 40 个场景，33 个可行，7 个不可行，33 条 Oracle 成功轨迹
总计：140 个场景
```

覆盖任务：

```text
single_control
multi_control
query_then_control
brightness_control
lock_control
impossible_temperature
```

跨 split 检查结果：

```text
scenario_id 总数：140
train/val/eval 重叠：0
```

## 5. 已验证事实

```text
33 项 unittest 全部通过
homeflow_demo 和 tests 的 compileall 检查通过
全部生成场景通过 schema 校验
可行场景 Oracle 轨迹全部成功
不可行场景没有被标记为成功
V1.1 JSONL 轨迹可以读写回放
V1 数据验收脚本按 turns 重放并返回 valid=true
多工具 turn 已验证为 1 条 transition 和多个 tool_events
验收过程没有调用 DeepSeek API
```

执行命令：

```bash
python -m unittest discover -v
python -m compileall -q homeflow_demo tests
python -m homeflow_demo.data.build_v1_dataset \
  --output-dir homeflow_demo/data_processed/v1 \
  --seed 20260921
python -m homeflow_demo.data.validate_v1_dataset \
  --root homeflow_demo/data_processed/v1
```

## 6. 未完成事项

```text
尚未调用 DeepSeek API
尚未生成自然语言改写和候选教师轨迹
尚未构建 SFT 对话格式数据
尚未接入 Qwen2.5-1.5B 训练
尚未实现在线 rollout 和 LoRA-GRPO
```

## 7. 残余风险

```text
设备类型和状态字段仍是 V1 的固定小集合
规划器是有限规则规划器，不代表真实模型的自然语言推理能力
当前场景规模用于 Demo 和科研入门，不代表正式 benchmark 规模
V1 的不可行任务主要通过越界目标表达，澄清和拒答任务将在后续版本扩展
```

## 8. 进入下一版本判断

```text
V1：完成
V1.1：完成，模型 turn 与 HomeEnv transition 已对齐
V2：可以进入，调用 DeepSeek 生成候选 assistant turn 并由 HomeEnv 筛选
V1.1 交付：AssistantTurn、ToolEvent、TurnResult、max_turns 和 turn-level 轨迹
```
