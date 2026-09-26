# `homeflow_demo/data/build_v1_dataset.py` 说明

## 职责

这是历史入口保护器。`data_processed/v1/` 已冻结为 V1/V1.1 验收产物，旧命令不再生成或覆盖数据。

```text
调用 build_v1_dataset()
  -> RuntimeError
  -> 提示使用 homeflow_demo.data.build_v1_2_dataset
```

V1.2 的正式命令：

```bash
cd /root/autodl-tmp
python -m homeflow_demo.data.build_v1_2_dataset
```
