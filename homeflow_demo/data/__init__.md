# `homeflow_demo/data/__init__.py` 说明

集中导出 V1.2 场景生成、V2 Blueprint/DeepSeek 数据流水线、Oracle 规划、JSONL 读写和稳定指纹接口。外部脚本无需依赖各文件内部实现。

## 功能

集中导出 V1 阶段最常用的场景生成器、规则规划器和 Oracle 执行函数。

## 输入输出

```text
输入：data 子模块
输出：ScenarioGenerator、TaskBlueprint、DeepSeekTaskWriter、DeepSeekTaskReviewer、PlanResult、plan_scenario、run_oracle_episode
```
