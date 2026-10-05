# test_grpo.py 中文说明

职责：无网络CPU回归验证奖励判定、token对齐、冻结参考与损失；另检查四路批量服务的路由和退出。

```text
输入：pytest；部分夹具读取服务器已有评测归档
读取：本目录代码、归档轨迹、CPU微型Qwen2配置
输出：测试通过/失败/明确skip
写入：pytest tmp_path内的测试日志说明；不改归档或SFT模型
不负责：付费API验证、5090峰值测量、完整RL效果评估
```

```text
配置与奖励：16轨迹关系、删除项、真实进度、错误finish、普通枚举与严重违规
过程安全：keep改坏后恢复仍门控；回执被篡改拒收
查询边界：T5证据停用、待审奖励null
分组：同任务四条、pending禁止更新、非有限奖励拒收
评审：三票严格布尔、损坏聚合缓存不复用
采样：原始token前缀一致、观察可见但不参与loss
批量服务：四个请求成批、Future正确对应、close后线程停止
模型数学：非策略指数溢出屏蔽；稀疏logits与全量相等
参考冻结：正优势使选定token概率上升，参考adapter指纹不变
产物说明：补JSONL中文md不改变原日志字节
```

运行：`/root/autodl-tmp/sft-venv/bin/python -m pytest training/10-5_grpo/test_grpo.py -q`。本文件共14项测试；依赖旧归档的测试在其他机器缺文件时明确skip。Tiny模型测试只在CPU计算，不代表真实1.5B的显存或训练效果。
