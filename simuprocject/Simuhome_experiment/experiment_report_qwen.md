# SimuHome Benchmark 双模型实验报告

> 生成时间：2026-05-24  
> 数据来源：`data/benchmark/`（600 条测试用例）  
> 策略：`ReAct` (temperature=0, max_steps=20)

---

## 一、实验配置

| 配置项 | DeepSeek 实验 | Qwen 实验 |
|---|---|---|
| 被测模型 | deepseek-v4-flash | Qwen/Qwen3.6-35B-A3B |
| API 提供商 | https://api.deepseek.com | https://api.siliconflow.cn/v1 |
| 裁判模型 | deepseek-v4-flash | deepseek-ai/DeepSeek-V4-Flash |
| 结果目录 | `experiments/*_full/` | `experiments/*_qwen/` |

---

## 二、总览

| 指标 | DeepSeek | Qwen | 差距 |
|---|---:|---:|---:|
| 总正确数 | 283 | 258 | -25 (↓8.8%) |
| 有效评估 | 545 | 592 | +47 |
| 基础设施错误 | 55 | 8 | -47 (↓85%) |
| 整体准确率 | **51.93%** | **43.58%** | -8.35pp |
| Feasible 准确率 | **60.89%** (165/271) | **51.19%** (150/293) | -9.70pp |
| Infeasible 准确率 | **43.07%** (118/274) | **36.12%** (108/299) | -6.95pp |

---

## 三、逐组对比

| 实验组 | DeepSeek 准确率 | Qwen 准确率 | 差距 | 获胜 |
|---|---:|---:|---:|:---:|
| QT1 Feasible | 85.71% (42/49) | **92.00%** (46/50) | +6.29pp | 🟢 Qwen |
| QT1 Infeasible | 62.00% (31/50) | **78.00%** (39/50) | +16.00pp | 🟢 Qwen |
| QT2 Feasible | 51.16% (22/43) | 50.00% (23/46) | -1.16pp | ≈ 持平 |
| QT2 Infeasible | **46.51%** (20/43) | 14.00% (7/50) | -32.51pp | 🟠 DeepSeek |
| QT3 Feasible | **82.93%** (34/41) | 75.00% (36/48) | -7.93pp | 🟠 DeepSeek |
| QT3 Infeasible | 72.92% (35/48) | **88.00%** (44/50) | +15.08pp | 🟢 Qwen |
| QT4-1 Feasible | 32.61% (15/46) | 32.00% (16/50) | -0.61pp | ≈ 持平 |
| QT4-1 Infeasible | 22.45% (11/49) | **34.00%** (17/50) | +11.55pp | 🟢 Qwen |
| QT4-2 Feasible | **48.98%** (24/49) | 42.00% (21/50) | -6.98pp | 🟠 DeepSeek |
| QT4-2 Infeasible | **36.96%** (17/46) | 0.00% (0/50) | -36.96pp | 🟠 DeepSeek |
| QT4-3 Feasible | **65.12%** (28/43) | 16.33% (8/49) | -48.79pp | 🟠 DeepSeek |
| QT4-3 Infeasible | **10.53%** (4/38) | 2.04% (1/49) | -8.49pp | 🟠 DeepSeek |

> 总计：🟢 Qwen 胜 4 组 | 🟠 DeepSeek 胜 6 组 | ≈ 持平 2 组

---

## 四、按查询类型汇总

| 查询类型 | DeepSeek Feasible | Qwen Feasible | DeepSeek Infeasible | Qwen Infeasible |
|---|---|---|---|---|
| **QT1** | 85.71% | **92.00%** | 62.00% | **78.00%** |
| **QT2** | **51.16%** | 50.00% | **46.51%** | 14.00% |
| **QT3** | **82.93%** | 75.00% | 72.92% | **88.00%** |
| **QT4-1** | 32.61% | 32.00% | 22.45% | **34.00%** |
| **QT4-2** | **48.98%** | 42.00% | **36.96%** | 0.00% |
| **QT4-3** | **65.12%** | 16.33% | **10.53%** | 2.04% |

> **综合准确率**：DeepSeek **51.93%** | Qwen **43.58%**

---

## 五、耗时对比（平均每条）

| 实验组 | DeepSeek | Qwen | 倍数 |
|---|---:|---:|---:|
| QT1 Feasible | 7.73s | 50.24s | ×6.5 |
| QT1 Infeasible | 9.98s | 33.96s | ×3.4 |
| QT2 Feasible | 17.84s | 159.06s | ×8.9 |
| QT2 Infeasible | 16.91s | 203.36s | ×12.0 |
| QT3 Feasible | 17.17s | 248.70s | ×14.5 |
| QT3 Infeasible | 13.60s | 38.95s | ×2.9 |
| QT4-1 Feasible | 31.86s | 139.12s | ×4.4 |
| QT4-1 Infeasible | 14.97s | 93.26s | ×6.2 |
| QT4-2 Feasible | 28.53s | 175.15s | ×6.1 |
| QT4-2 Infeasible | 38.04s | 200.68s | ×5.3 |
| QT4-3 Feasible | 30.80s | 337.01s | ×10.9 |
| QT4-3 Infeasible | 36.72s | 642.83s | ×17.5 |

> Qwen 通过 SiliconFlow 中转，平均慢 **8.3 倍**。

---

## 六、基础设施错误对比

| 实验组 | DeepSeek | Qwen |
|---|---:|---:|
| QT1 Feasible | 1 | 0 |
| QT1 Infeasible | 0 | 0 |
| QT2 Feasible | 7 | 4 |
| QT2 Infeasible | 7 | 0 |
| QT3 Feasible | 9 | 2 |
| QT3 Infeasible | 2 | 0 |
| QT4-1 Feasible | 4 | 0 |
| QT4-1 Infeasible | 1 | 0 |
| QT4-2 Feasible | 1 | 0 |
| QT4-2 Infeasible | 4 | 0 |
| QT4-3 Feasible | 7 | 1 |
| QT4-3 Infeasible | 12 | 1 |
| **合计** | **55 (9.2%)** | **8 (1.3%)** |

> Qwen 跑在 SiliconFlow 上反而基础设施更稳定。

---

## 七、关键结论

### DeepSeek 优势
- **整体更强**：51.93% vs 43.58%，领先 8.35pp
- **复杂推理遥遥领先**：QT4-3 Feasible（65% vs 16%）、QT4-2 Infeasible（37% vs 0%）、QT2 Infeasible（47% vs 14%）
- **速度极快**：平均快 8 倍，直连 DeepSeek 官服延迟极低

### Qwen 优势
- **简单信息查询最强**：QT1 Feasible 92%、Infeasible 78%，都超过了 DeepSeek
- **QT3 Infeasible 亮眼**：88% 准确率，说明 Qwen 善于识别"设备不存在/属性不可查"这类不可行任务
- **QT4-1 Infeasible 也有进步**：34% vs 22%，小胜 DeepSeek
- **基础设施稳定**：仅 8 条错误（1.3%），远优于 DeepSeek 的 55 条

### 综合评价
DeepSeek-V4-Flash 在复杂度高的场景（QT3 Feasible、QT4 Feasible、QT2/QT4 Infeasible）显著优于 Qwen3.6-35B-A3B，但在简单检索类任务上（QT1）反而略逊一筹。两者各有所长，但 DeepSeek 整体更均衡。Qwen 的致命短板在 QT4-2 Infeasible（0%）和 QT4-3 Feasible（16%），说明环境冲突推理是其明显弱项。
