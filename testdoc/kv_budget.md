# kv_budget.py

职责：
  按 Qwen2.5-1.5B-Instruct 的层数和 GQA，估算本机 RTX 3080 Ti（12288 MiB）上 vLLM 的 KV 池大小，以及「并发 × 每路上下文」能否同时顶满。

输入：
  无命令行参数。常量写在文件顶部：卡容量、层数、KV 头、head_dim、权重估算、引擎开销。

输出：
  三档 gpu_memory_utilization 的 KV 池 token 数、每路被 32768 截断后的上限、4/8/16/32K 能否同时顶满。

读取：
  不读磁盘。架构数字来自 HuggingFace `Qwen/Qwen2.5-1.5B-Instruct` 的 config.json。

写入：
  只打印到 stdout。

不负责：
  不启动 vLLM，不加载权重，不测 tok/s。引擎开销是估算，上机后以 vLLM 日志里的 KV cache 页数为准。

对应文件：
  testdoc/kv_budget.py
