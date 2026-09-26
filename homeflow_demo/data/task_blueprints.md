# `homeflow_demo/data/task_blueprints.py` 说明

## 职责

程序化生成 V2 Demo 的五类任务蓝图。蓝图先确定家庭状态、隐藏目标、观察要求和安全边界，再交给 DeepSeek 改写用户语言。

```text
程序生成 Blueprint
  -> DeepSeekTaskWriter 只看到 writer_view
  -> 审查通过的 user_request
  -> compile_scenario()
  -> C/B 执行和隐藏评测
```

五类任务：

```text
single_control       单设备控制
multi_control        多设备控制
vague_intent         模糊意图理解
dangerous_refusal    危险动作拒绝
environment_query    环境基础查询
```

## 输入输出

```text
generate_task_blueprints(count_per_category, split, seed)
  输入：每类数量、数据 split、随机种子
  输出：TaskBlueprint 列表

TaskBlueprint.compile_scenario(user_request)
  输入：审查通过的自然语言请求
  输出：通过 HomeEnv schema 校验的 Scenario 字典
```

`writer_view` 不包含内部设备 ID、动作名和隐藏 reason code；`hidden_truth` 只写入 Scenario 的 C 评测部分，不进入模型 observation。
