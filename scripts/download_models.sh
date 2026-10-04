#!/usr/bin/env bash
# ============================================================================
# download_models.sh
# 用途：从 ModelScope 并行下载三档 Qwen 小模型，每档两种格式
#   ① hf   整仓库（safetensors + tokenizer + config），供 SFT / GRPO 训练
#   ② gguf Q8_0 单文件，供 llama.cpp (llama-server) 推理评测
# 落地：/root/autodl-tmp/models/<模型名>/{hf,gguf}
# 日志：/root/autodl-tmp/models/_logs/<任务名>.log，pid 表在同目录 pids.txt
# 用法：bash scripts/download_models.sh            （前台阻塞）
#       nohup bash scripts/download_models.sh &    （后台）
# 依赖：/root/autodl-tmp/model-tools-venv 里的 modelscope CLI（1.40.1）
# ============================================================================
set -u

MS=/root/autodl-tmp/model-tools-venv/bin/ms      # modelscope CLI 可执行文件
MODELS=/root/autodl-tmp/models                   # 权重根目录（仓库外，不入 git）
CACHE=/root/autodl-tmp/.ms_cache                 # 缓存放数据盘，避免占用 30G 系统盘
LOGS=$MODELS/_logs                               # 每任务一份日志
mkdir -p "$LOGS" "$CACHE"

# 启动一个后台下载任务
# 参数：$1=仓库ID  $2=落地目录  $3=日志名  $4..=限定文件（不传=整仓库）
start_job() {
  local repo=$1 dir=$2 log=$3; shift 3
  mkdir -p "$dir"
  "$MS" download "$repo" "$@" \
      --local-dir "$dir" --cache-dir "$CACHE" --max-workers 8 \
      > "$LOGS/$log.log" 2>&1 &
  echo "$! $repo" >> "$LOGS/pids.txt"            # 记 pid，方便事后查
}

: > "$LOGS/pids.txt"                             # 清空上一轮的 pid 记录
echo "开始下载 $(date '+%F %T')"

# ---- 6 个任务同时起：3 个 hf 整仓库 + 3 个 gguf Q8_0 单文件 ----
start_job Qwen/Qwen3-0.6B                  "$MODELS/Qwen3-0.6B/hf"              qwen3-0.6b-hf
start_job Qwen/Qwen3-0.6B-GGUF             "$MODELS/Qwen3-0.6B/gguf"            qwen3-0.6b-gguf    Qwen3-0.6B-Q8_0.gguf
start_job Qwen/Qwen2.5-1.5B-Instruct       "$MODELS/Qwen2.5-1.5B-Instruct/hf"   qwen2.5-1.5b-hf
start_job Qwen/Qwen2.5-1.5B-Instruct-GGUF  "$MODELS/Qwen2.5-1.5B-Instruct/gguf" qwen2.5-1.5b-gguf  qwen2.5-1.5b-instruct-q8_0.gguf
start_job Qwen/Qwen3.5-2B                  "$MODELS/Qwen3.5-2B/hf"              qwen3.5-2b-hf
start_job unsloth/Qwen3.5-2B-GGUF          "$MODELS/Qwen3.5-2B/gguf"            qwen3.5-2b-gguf    Qwen3.5-2B-Q8_0.gguf

wait                                             # 等 6 个任务全部结束
echo "全部下载任务结束 $(date '+%F %T')"
