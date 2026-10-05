# analyze_run.py 中文说明

职责：重算某个冻结step对应的实际训练量、奖励信号、分类采用量，以及固定200评测的配对变化与严格过程安全。

输入是training-run、checkpoint-step，可选evaluation-run及plot路径。输出为独立分析目录analysis.json/md及可选PNG，不调用模型或外部API，不改训练参数或原轨迹。

```text
lineage：按续跑来源读候选，拒绝循环引用
training_summary：step前缀 → 候选上限 → 实际committed采用组
  500唯一任务覆盖 ≠ 500唯一任务都进入梯度；旧失败更新不计步
evaluation_summary：原200结果 → 同sample_id配对 → C+D6与过程安全
  调用preprocess重放校验，不把T5规则F停用当作已证明真实
render_plot：实际reward/有差异组/KL/固定评测画成PNG
```

`classify`结构标记只含进度、取证、错误、F、budget、安全。分析额外核对C全通过标志是否变化；只有结构分项与C完成标志均不变的奖励差异，才标为pure_semantic_difference，不能把所有未标结构差异的组称为评审噪声。配对精确McNemar概率仅作探索性记录，不证明跨分布泛化。

主要产物包含每类候选/有差异/采用/唯一梯度任务数、恢复后的更新曲线、三个模型完整与严格安全成功数、改善/退步sample_id和失败工具序列，以及输入指纹。JSON与同名中文说明由runtime统一落盘。待审、候选缺失、采用数不一致或原轨迹变化直接抛错。

另存每组varying_terms，仅H真实性变化的组计truth_only_variation，采用有差异组的reward_range直方图用于判断小软差放大的风险；这些是真实分项差，不把组数直接当成梯度权重。

PNG有差异组图使用绝对组数，明确当前每更新8组，历史0.88均值来自每更新4组，不把两者误写成同分母占比。图由真实数据生成；当前图像查看工具不可用，未宣称人工视觉验收。
