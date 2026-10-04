# verify_models.py 说明

> 配套脚本：`scripts/verify_models.py`
> 版本：2026-10-04 首版，配合 `download_models.sh` 使用

## 1 它是干什么的

`download_models.sh` 只管把六个仓库拉下来，拉完必须对账，否则「下完了」只是下载工具的自我报告。这个脚本做三件事：

```text
输入                         校验                        输出
models/Qwen3-0.6B/gguf/  →  SHA-256 对登记值        →  控制台报告
models/Qwen2.5-1.5B...   →                         →  scripts/model_manifest.json
models/Qwen3.5-2B/hf/    →  关键文件齐全性          →  scripts/model_manifest.md
（共 6 个目录）               (safetensors/config/tokenizer)
```

## 2 两种格式的校验口径不同

```text
GGUF（3 个文件）
  有外部参照：source.md §3 登记了 Windows 端同名文件的 SHA-256
  Qwen3-0.6B-Q8_0.gguf            9465e63a...bb031
  qwen2.5-1.5b-instruct-q8_0.gguf d7efb072...a63c8
  Qwen3.5-2B-Q8_0.gguf            1b04acba...1f2c1
  哈希对上 = 与旧评测（newdoc/05、12）跑的是同一份文件

HF 仓库（3 个目录）
  没有外部哈希可对（source.md 只登记了 GGUF）
  退而求其次：关键文件必须齐全，且完整登记文件清单
  Qwen3.5-2B 的 safetensors 是单文件命名 model.safetensors-00001-of-00001.safetensors
  （多模态仓库自带的索引式命名），检查项与另两个不同
```

## 3 退出码与结果怎么看

```text
exit 0  六个目标全部通过
exit 1  有缺文件或哈希不符 —— 看报告里 FAIL 那一行，重新下载对应仓库即可
        （modelscope 的 .incomplete 文件支持断点续传，重跑 download_models.sh 会接着下）
```

## 4 产出文件的关系

```text
model_manifest.json   机器可读：后续训练/评测脚本从这里读权重路径，不要散写硬编码
model_manifest.md     人类可读：由同一份数据渲染，含每个 HF 仓库的完整文件清单
                      两者都由脚本生成，不要手改；重跑校验会覆盖
```

`model_manifest.md` 生成后，`source.md` §3 的「服务器侧」一节应补上这次六个权重的条目（来源、路径、哈希），保持两边口径一致。
