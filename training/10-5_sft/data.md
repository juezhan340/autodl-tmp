# data.py 中文说明

```text
职责：筛选无错误成功示范、语义分组、500/100/200划分、消息恢复、监督mask。
输入：config；原始D_dataset JSONL。
输出：train/validation/test/reserve消息文件、配套scenarios、manifest及中文md。
读取：公开A提示词、工具schema、本地官方tokenizer、原始轨迹。
写入：output_root/data/，默认仓库外。
不负责：模型更新、环境推理评测、D6收费请求。
```

同一家庭和隐藏目标的用户话改写归同组。先在每类选覆盖动作/设备/算子的训练代表，再按固定种子补齐配额；验证、测试、备用都与训练组隔离。输入行顺序不影响结果。

```text
真实轨迹1000
  -> 四标签/D6合格且每轮无错误：994
  -> 训练500 / 验证100 / 测试200 / 备用194
  -> messages只含system、原话、助手JSON和user observation
  -> 用官方generation区域构造labels
       用户/观察/角色头：-100
       每段助手JSON及im_end：真实token id
```

训练模板必须与原始模板渲染字符串完全一致；每个助手段解码须等于原JSON，且含结束token。超过3072时报错，不裁掉finish。写盘后保存输入、模板、配置和所有产物的SHA-256；读取时检查版本及文件是否被改动。

消息文件中的category/id仅用于追溯，编码时只读取messages。`*_scenarios.jsonl`包含隐藏目标，专供评测，不是训练消息。
