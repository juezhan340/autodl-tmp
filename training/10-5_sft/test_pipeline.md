# test_pipeline.py 中文说明

自动测试数据筛选、分组改写隔离、确定性配额、全部助手段与EOS、超长拒绝、模板字符串一致性、数据改动检测、完整训练确认、检查点元数据、恢复数据版本隔离、smoke模式入口、D6缺失判定和最终测试保护。

```text
输入：真实只读千条数据、本地tokenizer、pytest临时目录。
输出：pytest通过/失败结果。
写入：仅pytest临时产物；不改原始轨迹或正式配置。
不负责：GPU反向传播和真实adapter重载，这些由preflight的gpu-smoke完成。
```

测试不包含完整训练。真实五类教师数据用于覆盖协议；缺文件、篡改文件、助手mask错误或遗漏EOS都应使测试失败。

正式训练参数额外核对micro-batch=4、累计2、逐epoch完整保存、无限保留和每step日志。实时页面及独立启动的回归见test_monitor.py，不新增GPU训练验证。
