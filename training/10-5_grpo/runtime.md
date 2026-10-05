# runtime.py 中文说明

2026-10-06：`train_full.py`配置独立检查500池预算和8组×G4=micro16×累计2，不再套用冒烟“一类一个任务”的数量限制；历史冒烟和100入口约束保留。候选预算必须足够覆盖全池，窗口必须容纳一次完整更新。

职责：复用现有SFT的结构化读写、指纹和中文产物说明，校验GRPO配置。通过独立模块名加载`10-5_sft/common.py`，不改SFT代码，也不混用两个实验的输出目录。

```text
输入：config.json、JSON/JSONL路径、待写入的结构化数据
读取：10-5_sft/common.py；调用方指定的文件
输出：配置字典、数据、SHA-256；校验失败抛ValueError
写入：调用方指定的JSON/JSONL及同名md
不负责：GPU加载、奖励计算、密钥读取、训练启动
```

`load_config`要求`groups_per_update × num_generations = micro_batch × accumulation`。当前等式为`4×4 = 2×8 = 16`。生成并行数不得超过组内轨迹数，且必须能整除组大小；冒烟类别数必须等于任务组数。温度、学习率、KL系数和裁剪参数检查有限性与范围。

`annotate_jsonl_tree(root)`为API客户端生成的JSONL补齐同名中文说明，只读取行数和字段、写md，不改原日志字节。JSON说明沿用`annotate_json_tree`。这些函数不自动删除旧产物。

仓库根路径由当前文件位置推导；模型与大批运行数据仍放在`/root/autodl-tmp/training_runs/10-5_grpo/`等仓库外目录。
