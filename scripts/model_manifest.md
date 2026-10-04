# model_manifest — 服务器模型权重登记

> 生成时间：2026-10-04 22:06:46　生成脚本：`scripts/verify_models.py`
> 校验结果：全部通过 ✅

## 1 总览

| 模型 | 格式 | 来源 (ModelScope) | 大小 | 校验 |
|---|---|---|---|---|
| Qwen3-0.6B | gguf | Qwen/Qwen3-0.6B-GGUF | 0.64 GB | ✅ |
| Qwen2.5-1.5B-Instruct | gguf | Qwen/Qwen2.5-1.5B-Instruct-GGUF | 1.89 GB | ✅ |
| Qwen3.5-2B | gguf | unsloth/Qwen3.5-2B-GGUF | 2.01 GB | ✅ |
| Qwen3-0.6B | hf | Qwen/Qwen3-0.6B | 1.52 GB | ✅ |
| Qwen2.5-1.5B-Instruct | hf | Qwen/Qwen2.5-1.5B-Instruct | 3.10 GB | ✅ |
| Qwen3.5-2B | hf | Qwen/Qwen3.5-2B | 4.57 GB | ✅ |

## 2 GGUF 哈希对账（对 source.md §3 的 Windows 端登记值）

| 文件 | SHA-256 | 对上登记值 |
|---|---|---|
| Qwen3-0.6B-Q8_0.gguf | `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031` | 是 |
| qwen2.5-1.5b-instruct-q8_0.gguf | `d7efb072e7724d25048a4fda0a3e10b04bdef5d06b1403a1c93bd9f1240a63c8` | 是 |
| Qwen3.5-2B-Q8_0.gguf | `1b04acba824817554f4ce23639bc8495ff70453b8fcb047900c731521021f2c1` | 是 |

## 3 HF 仓库文件清单

### Qwen3-0.6B（Qwen/Qwen3-0.6B，1.52 GB）

```text
       0.0 MB  .gitattributes
       0.0 MB  LICENSE
       0.0 MB  README.md
       0.0 MB  config.json
       0.0 MB  configuration.json
       0.0 MB  generation_config.json
       1.7 MB  merges.txt
    1503.3 MB  model.safetensors
      11.4 MB  tokenizer.json
       0.0 MB  tokenizer_config.json
       2.8 MB  vocab.json
```

### Qwen2.5-1.5B-Instruct（Qwen/Qwen2.5-1.5B-Instruct，3.10 GB）

```text
       0.0 MB  .gitattributes
       0.0 MB  LICENSE
       0.0 MB  README.md
       0.0 MB  config.json
       0.0 MB  configuration.json
       0.0 MB  generation_config.json
       1.7 MB  merges.txt
    3087.5 MB  model.safetensors
       7.0 MB  tokenizer.json
       0.0 MB  tokenizer_config.json
       2.8 MB  vocab.json
```

### Qwen3.5-2B（Qwen/Qwen3.5-2B，4.57 GB）

```text
       0.0 MB  .gitattributes
       0.0 MB  LICENSE
       0.1 MB  README.md
       0.0 MB  chat_template.jinja
       0.0 MB  config.json
       0.0 MB  configuration.json
       3.4 MB  merges.txt
    4548.2 MB  model.safetensors-00001-of-00001.safetensors
       0.1 MB  model.safetensors.index.json
       0.0 MB  preprocessor_config.json
      12.8 MB  tokenizer.json
       0.0 MB  tokenizer_config.json
       0.0 MB  video_preprocessor_config.json
       6.7 MB  vocab.json
```

