# config.json 中文说明

这是单次4×4冒烟的配置，不能用它直接启动完整500任务训练。模型、SFT adapter和数据都指向服务器已有文件；没有下载操作，也不覆盖SFT检查点。

| 字段 | 当前内容及含义 |
|---|---|
| base_model | `/root/autodl-tmp/models/Qwen2.5-1.5B-Instruct/hf`，冻结BF16基座 |
| sft_adapter | `/root/autodl-tmp/training_runs/10-5_sft/sft-main/selected_adapter`，复制成policy与固定参考 |
| sft_data | `/root/autodl-tmp/training_runs/10-5_sft/data`，读取训练Scenario并检查划分隔离 |
| output_root | `/root/autodl-tmp/training_runs/10-5_grpo`，每次运行创建独立时间戳子目录 |
| seed | 20261005，设置随机种子；线程调度仍可能影响分支随机数分配 |
| groups_per_update / num_generations | 4个任务，每个任务4条独立轨迹，共16条 |
| rollout_parallel | 4，同组四条环境并发，共享一个GPU生成线程 |
| micro_batch / accumulation | 2条轨迹一次反向，重复8次后只更新一次 |
| max_length / max_new_tokens | 完整采样上下文上限3072；每次助手生成上限192 |
| temperature | 0.7，生成与概率重算使用同一温度 |
| learning_rate / beta / epsilon | `1e-5 / 0.02 / 0.2`；AdamW、SFT参考KL、概率比裁剪 |
| judge_workers | 16个轨迹评审并发；每条轨迹内部串行三票 |
| smoke_categories | T2、T3、T4、T5；本次不含已较稳定的T1，正式小试应混合五类 |
| reward_version | `grpo-r2-20261005` |

奖励权重完整内容如下：

```text
success      3.0    C全部通过且语义评审认为完整、真实
progress     2.0    乘目标满足比例的终点减起点
evidence     0.5    乘首次取得的预定义证据覆盖比例
truth        0.5    诚实结尾，即使只完成一部分
error        0.25   每条result.ok=false的真实事件减分
false_finish 2.0    可规则判定的错误completed/refused减分
budget       0.5    轮数或上下文预算耗尽减分
unsafe      -5.0    严重过程违规时覆盖普通总分
```

无效调用、编造事实、调用成本三个独立奖励项已经删除。诚实结尾仍有正向奖励，但不另设“编造事实扣2分”。普通奖励裁剪到`[-4,6]`，严格安全门控为`-5`。当前配置SHA-256：`9c06d3b1dcd824e8aec211eee4b0901dd94d54af1098c7c4a23768065375cb27`。
