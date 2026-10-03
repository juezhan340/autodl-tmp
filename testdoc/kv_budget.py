"""按 Qwen2.5-1.5B 架构估算本机 RTX 3080 Ti 上 vLLM 的 KV 池与并发上下文。"""

from __future__ import annotations

# 本机显存按 nvidia-smi 的 12288 MiB 计，不按 12e9 字节。
CARD_MIB = 12288
# Qwen2.5-1.5B-Instruct：28 层、GQA 2 组 KV、head_dim=128、BF16。
N_LAYERS = 28
N_KV_HEADS = 2
HEAD_DIM = 128
BYTES_BF16 = 2
# 官方权重约 2.95GB；vLLM 加载后再加引擎工作区。
WEIGHTS_GB = 3.0
# 模型位置编码上限，单条序列不能超过这个数。
MODEL_MAX_LEN = 32768


def kv_bytes_per_token(kv_bytes: int = BYTES_BF16) -> int:
    """一层 K 和 V 各一份，乘层数和 KV 头。"""
    return N_LAYERS * 2 * N_KV_HEADS * HEAD_DIM * kv_bytes


def kv_pool_tokens(util: float, overhead_gb: float, kv_bytes: int = BYTES_BF16) -> tuple[float, float, int]:
    """vLLM 预占 util*卡容量，扣掉权重和开销后剩下的全是 KV 页。"""
    vllm_gb = util * (CARD_MIB / 1024)
    kv_gb = vllm_gb - WEIGHTS_GB - overhead_gb
    if kv_gb <= 0:
        return vllm_gb, kv_gb, 0
    tokens = int(kv_gb * (1024**3) / kv_bytes_per_token(kv_bytes))
    return vllm_gb, kv_gb, tokens


def per_seq_cap(pool_tokens: int, concurrent: int) -> int:
    """五路同时顶满时，每路能摊到的上下文；再和模型上限取小。"""
    if concurrent <= 0:
        return 0
    return min(MODEL_MAX_LEN, pool_tokens // concurrent)


def fits(pool_tokens: int, concurrent: int, max_model_len: int) -> bool:
    """ concurrent 路、每路 max_model_len，同时顶满是否装得下。"""
    return concurrent * max_model_len <= pool_tokens


def print_report() -> None:
    """打印本机推荐表，给 testdoc 引用。"""
    per = kv_bytes_per_token()
    print(f"卡容量          {CARD_MIB} MiB")
    print(f"KV / token BF16 {per} bytes ({per / 1024:.1f} KiB)")
    print(f"权重估算        {WEIGHTS_GB} GB")
    print(f"模型上限        {MODEL_MAX_LEN}")
    print()
    profiles = [
        ("独占卡  util=0.85  overhead=1.2GB", 0.85, 1.2),
        ("留余量  util=0.70  overhead=1.0GB", 0.70, 1.0),
        ("和别的进程分卡  util=0.45  overhead=0.8GB", 0.45, 0.8),
    ]
    conc_list = (1, 4, 5, 8, 16, 32)
    lens = (4096, 8192, 16384, 32768)
    for title, util, overhead in profiles:
        vllm_gb, kv_gb, pool = kv_pool_tokens(util, overhead)
        print("=" * 64)
        print(title)
        print(f"vLLM 预占 {vllm_gb:.2f} GB，KV 池 {kv_gb:.2f} GB，合计 {pool} tokens")
        print("并发    每路上限(被 32768 截断)")
        for n in conc_list:
            print(f"{n:>4}    {per_seq_cap(pool, n)}")
        print("同时顶满是否装得下：")
        header = "并发\\上下文  " + "  ".join(f"{n:>6}" for n in lens)
        print(header)
        for n in conc_list:
            cells = []
            for length in lens:
                cells.append("  OK  " if fits(pool, n, length) else "  超  ")
            print(f"{n:>6}        " + "  ".join(cells))
        print()
    print("HomeFlow 实测量级：末轮提示词约 2k–4k tokens，生成不足 200。")
    print("评测五路并发用 max_model_len=8192 即可，32K 是余量不是刚需。")


if __name__ == "__main__":
    print_report()
