# evaluate.py 中文说明

```text
职责：加载基础模型或任一epoch adapter，复用现行A消息流与C/B运行环境。
输入：config、集合名、adapter路径、输出目录、D6模式。
输出：真实环境轨迹、分类型C标签与完整成功/待审数量。
读取：冻结数据manifest和相应scenarios；已有本地权重。
写入：评测目录的trajectories.jsonl、summary.json及同名md。
不负责：参数训练、教师强制生成、自动替换模型、默认调用外部API。
```

`LocalGenerationClient`实现现行`DeepSeekPolicy`的客户端接口，在本地调用generate；因此用户话、工具回执、错误反馈和隐藏信息边界直接复用项目A。一次只生成当前助手JSON，greedy推理，不插入few-shot。输入超限报错，不删除早期历史。

默认集合为validation。最终test必须给`--confirm-final-test`。预测试只用train集合每类一条，既不更新参数，也不读取最终200条的模型成绩。

```text
semantic-judge=off（默认）
  -> 不发外部请求
  -> C全过的T3/T4/T5仍标final_success=null

semantic-judge=deepseek（显式选择）
  -> 复用D6三票复核，需已有密钥配置
  -> system_failure仍不能算完整成功
```

报告同时记录本地生成尝试、成功和异常数；不能把模型调用异常吞成普通任务失败后宣称接口预测试通过。基线和adapter应使用相同的集合、轮数、消息协议与语义复核设置。
