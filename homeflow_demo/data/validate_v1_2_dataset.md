# `homeflow_demo/data/validate_v1_2_dataset.py` 说明

## 职责

对 V1.2 数据做全量验收，不抽样。

```text
场景：schema、split、数量、八类任务覆盖、scenario_id 隔离
轨迹：format_version、scenario_id、统一 evaluation
重放：所有成功和失败轨迹都从初始 Scenario 重放
确定性：Oracle 再运行一次，evaluation 和 final_state 必须一致
门禁：可行任务成功且 accepted；不可行任务失败且 rejected
```

## 输入输出

```text
输入：--root，默认 homeflow_demo/data_processed/v1.2
输出：JSON 验证报告
退出码：valid=true 为 0，否则为 1
```

## 运行

```bash
cd /root/autodl-tmp
python -m homeflow_demo.data.validate_v1_2_dataset
```
