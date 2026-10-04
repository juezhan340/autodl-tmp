# download_models.sh 说明

> 配套脚本：`scripts/download_models.sh`
> 落地日期：2026-10-04
> 目的：给 autodl 服务器（RTX 5090 / `/root/autodl-tmp` 50G 数据盘）备齐三档 Qwen 小模型的两种格式

## 1 为什么要下这两套

```text
评测/推理要 GGUF
  本机 Windows 的 200 条评测全走 llama-server + GGUF（newdoc/12）
  服务器要复现同一对照，必须拿同一来源、同一量化等级的文件（Q8_0）

SFT/GRPO 要 HF safetensors
  训练框架（doc/07 选的 ms-swift + PEFT）直接吃 HuggingFace 格式仓库
  GGUF 不能训练，反过来 HF 格式用 llama.cpp 跑评测也不方便
```

## 2 下载清单（六仓库，全部来自 ModelScope）

```text
仓库                                   取什么              落地目录                        大小
Qwen/Qwen3-0.6B                        整仓库              models/Qwen3-0.6B/hf            1.52 GB
Qwen/Qwen3-0.6B-GGUF                   Q8_0 单文件         models/Qwen3-0.6B/gguf          0.64 GB
Qwen/Qwen2.5-1.5B-Instruct             整仓库              models/Qwen2.5-1.5B-Instruct/hf 3.10 GB
Qwen/Qwen2.5-1.5B-Instruct-GGUF        q8_0 单文件         models/Qwen2.5-1.5B-Instruct/gguf 1.89 GB
Qwen/Qwen3.5-2B                        整仓库(多模态)      models/Qwen3.5-2B/hf            4.57 GB
unsloth/Qwen3.5-2B-GGUF                Q8_0 单文件         models/Qwen3.5-2B/gguf          2.01 GB
                                                                                  合计 ≈ 13.7 GB
```

型号选择依据：对齐 `source.md` §3 里 Windows 端 `D:\D_program\models` 的登记——0.6B 是早期 SFT/GRPO 基座，1.5B 对应 newdoc/05 的评测基线，2B 对应 newdoc/12 里 112/200 的 Qwen3.5-2B。GGUF 只取 Q8_0 单文件，跟旧评测文件同源同量化，换了量化等级就没有对照意义。

不选 HF 直连的原因：服务器 `huggingface.co` 直连超时（实测），ModelScope 上六个仓库都有（含 unsloth 镜像），国内 CDN 速度也稳。

## 3 脚本怎么跑

```text
输入
  /root/autodl-tmp/model-tools-venv/bin/ms   modelscope CLI 1.40.1（已装好）
输出
  /root/autodl-tmp/models/<模型名>/{hf,gguf}/  权重文件
  /root/autodl-tmp/models/_logs/<任务名>.log   每任务日志
  /root/autodl-tmp/models/_logs/pids.txt       六个后台进程的 pid 表
  /root/autodl-tmp/.ms_cache/                  modelscope 下载缓存（放数据盘）
```

启动方式（后台，六个任务同时起）：

```bash
nohup bash scripts/download_models.sh > /root/autodl-tmp/models/_logs/all.log 2>&1 &
```

进度查看：

```bash
cat /root/autodl-tmp/models/_logs/pids.txt              # 看进程存活
du -sb /root/autodl-tmp/models/*/hf /root/autodl-tmp/models/*/gguf   # 看落了多大
tail -n 3 /root/autodl-tmp/models/_logs/qwen3.5-2b-hf.log            # 看单任务进度条
```

## 4 关键设计点

缓存目录显式指到数据盘（`--cache-dir /root/autodl-tmp/.ms_cache`）：系统盘只 30G，默认缓存路径在 `~/.cache/modelscope`，13.7G 的下载会把系统盘吃紧，数据盘还剩 50G。

六个进程并行而不再拆分单文件分片：ModelScope CDN 单连接速度实测后再决定是否加多连接；`--max-workers 8` 负责仓库内多文件并行，六个进程之间本来就并行。

GGUF 任务显式只传文件名参数（如 `Qwen3.5-2B-Q8_0.gguf`）：unsloth 那个仓库全量 34.6G（22 个量化档 + 3 个 mmproj），整仓拉是浪费；只取与 Windows 评测同源的 Q8_0。

## 5 下载完成后的校验（已完成：2026-10-04 22:06 全部通过）

```text
本批实测
  开始 21:42:59 → 结束 22:06:35，共 13.73 GB，全程合计约 17 MB/s
  六项校验全绿（exit 0），3 个 GGUF 的 SHA-256 与 source.md §3 登记值逐一相等：
    Qwen3-0.6B-Q8_0.gguf            9465e63a...bb031 ✓
    qwen2.5-1.5b-instruct-q8_0.gguf d7efb072...a63c8 ✓
    Qwen3.5-2B-Q8_0.gguf            1b04acba...1f2c1 ✓
  产出 scripts/model_manifest.json 与 model_manifest.md，source.md §3 已补登记

关于速度（本次实测结论）
  单条流约 3 MB/s，六进程合计 17 MB/s；再开 8 路并发总吞吐不升反降（各流跌到 0.6 MB/s），
  hf-mirror 另起一路也不叠加 —— 瓶颈是 AutoDL 实例公网出口（约 20 MB/s），
  加连接只会互相抢；以后重复本脚本不必再调并发数，6 进程即已吃满
```
