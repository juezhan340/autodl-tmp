#!/usr/bin/env python3
"""Verify llama-server prompt-cache reuse with real streamed requests.

Four phases, each isolating one mechanism:

  same_slot  default KV prefix reuse inside one slot (cache_prompt on vs off)
  switch     host-RAM prompt cache (--cache-ram) when the slot is taken over by
             a different prefix: the evicted prefix is saved, then restored
  reuse      --cache-reuse N KV shifting: a matching chunk that does NOT start
             at position 0 is moved into place instead of being recomputed
  verify     greedy output equality between a reused/shifted KV and a recompute

Phases `same_slot` and `switch` need a stock server. Phases `reuse` and `verify`
additionally need `--cache-reuse 256` on the server command line.

Reported per run:
  cache_n    tokens reused from the cache (server-side counter)
  prompt_n   tokens actually prefilled
  prompt_ms  prefill compute time for those tokens
  ttft_s     client wall clock to the first generated token
"""

import argparse
import json
import time
import urllib.request

PREFIX_TOKENS = 8192
HEADER_TOKENS = 512
DOCUMENT_TOKENS = 7168
OUTPUT_TOKENS = 32

BASE_TEXT = (
    "你是一名科研助理。请严格按下列要求处理输入数据：逐条阅读，保持术语一致，"
    "不要引入原文没有的事实，输出必须是单个 JSON 对象，字段名使用英文小写，"
    "数值保留四位有效数字，缺失值写 null，不要输出解释性文字。"
    "This instruction block is intentionally verbose so that it produces a long, "
    "stable prefix that can be reused across independent requests."
)

TAIL_TEXT = (
    "请处理第 {index} 条记录，并按要求返回结果。"
)


def post_json(url, body, timeout=600):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def tokenize(base_url, content):
    with post_json(f"{base_url}/tokenize", {"content": content, "add_special": False}) as response:
        return json.load(response)["tokens"]


def tile(base_url, text, length):
    """Repeat a real tokenized text until it reaches the requested length."""
    ids = tokenize(base_url, text)
    if not ids:
        raise RuntimeError("tokenizer returned no tokens")
    while len(ids) < length:
        ids = ids + ids
    return ids[:length]


def build_tail(base_url, index):
    """A tail whose first token is unique, so the prefix match length is exact."""
    marker = tokenize(base_url, f" 记录{index}")[0]
    body = tokenize(base_url, TAIL_TEXT.format(index=index))
    return [marker] + body


def stream_once(base_url, prompt_tokens, cache_prompt, output_tokens=OUTPUT_TOKENS, seed=7):
    body = {
        "prompt": prompt_tokens,
        "stream": True,
        "return_tokens": True,
        "return_progress": True,
        "cache_prompt": cache_prompt,
        "temperature": 0,
        "n_predict": output_tokens,
        "ignore_eos": True,
        "seed": seed,
    }

    started = time.perf_counter()
    first_token_at = None
    final_event = None
    generated_tokens = []

    with post_json(f"{base_url}/completion", body) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            event = json.loads(payload)
            # generated tokens arrive in the deltas; the final stop event only
            # carries the timing summary, so accumulate as we go
            if "prompt_progress" not in event and event.get("tokens_predicted", 0) > 0:
                generated_tokens.extend(event.get("tokens") or [])
                if first_token_at is None:
                    first_token_at = time.perf_counter()
            if event.get("stop"):
                final_event = event

    completed = time.perf_counter()
    timings = (final_event or {}).get("timings") or {}
    return {
        "prompt_tokens": len(prompt_tokens),
        "cache_prompt": cache_prompt,
        "generated_tokens": generated_tokens,
        "cache_n": timings.get("cache_n"),
        "prompt_n": timings.get("prompt_n"),
        "prompt_ms": timings.get("prompt_ms"),
        "prompt_per_second": timings.get("prompt_per_second"),
        "decode_tokens_per_second": timings.get("predicted_per_second"),
        "ttft_seconds": (first_token_at - started) if first_token_at else None,
        "total_seconds": completed - started,
        "id_slot": (final_event or {}).get("id_slot"),
    }


def run(base_url, prompt_tokens, label, cache_prompt=True, runs=None):
    result = stream_once(base_url, prompt_tokens, cache_prompt)
    result["label"] = label
    runs.append(result)
    print(
        "  {:<28} cache_n={:>6} prompt_n={:>6} prompt_ms={:>8} ttft_s={:.3f}".format(
            label,
            result["cache_n"] if result["cache_n"] is not None else -1,
            result["prompt_n"] if result["prompt_n"] is not None else -1,
            round(result["prompt_ms"], 2) if result["prompt_ms"] else -1,
            result["ttft_seconds"] or -1,
        ),
        flush=True,
    )
    return result


def phase_same_slot(base_url, runs):
    print("[1] same slot, default prompt cache", flush=True)
    prefix = tile(base_url, BASE_TEXT, PREFIX_TOKENS)
    tail_a = build_tail(base_url, 1)

    first = run(base_url, prefix + tail_a, "cold (cache on)", True, runs)
    run(base_url, prefix + build_tail(base_url, 2), "warm, same prefix (on)", True, runs)
    run(base_url, prefix + build_tail(base_url, 3), "same prefix (cache off)", False, runs)
    run(base_url, prefix + build_tail(base_url, 4), "same prefix (on again)", True, runs)
    return first["prompt_ms"]


def phase_switch(base_url, runs):
    print("[2] host-RAM prompt cache across a prefix switch", flush=True)
    prefix_a = tile(base_url, BASE_TEXT, PREFIX_TOKENS)
    prefix_b = tile(base_url, BASE_TEXT[::-1], PREFIX_TOKENS + 128)[:PREFIX_TOKENS]

    run(base_url, prefix_b + build_tail(base_url, 5), "new prefix B (evicts A)", True, runs)
    run(base_url, prefix_a + build_tail(base_url, 6), "back to A (RAM cache)", True, runs)


def phase_reuse(base_url, runs):
    """Same document, but the second prompt drops the header in front of it.

    The document therefore moves to an earlier position. The leading common prefix
    is still zero (the first tokens differ), so only --cache-reuse can recover the
    document, by shifting its KV entries from the old offset to the new one.
    """
    print("[3] --cache-reuse: document moved earlier by dropping the header", flush=True)
    header = tile(base_url, "第一份任务说明，用于测试缓存复用。" * 4, HEADER_TOKENS)
    document = tile(base_url, BASE_TEXT, DOCUMENT_TOKENS)

    prompt_old = header + document + build_tail(base_url, 7)
    prompt_new = document + build_tail(base_url, 8)

    first = run(base_url, prompt_old, "header + doc (cold)", True, runs)
    second = run(base_url, prompt_new, "doc alone (moved earlier)", True, runs)
    print(
        "  expected: cache_n ~= 0 without --cache-reuse, ~= {} with --cache-reuse 256."
        " The two prompts must not share a leading token.".format(DOCUMENT_TOKENS),
        flush=True,
    )
    return first["prompt_ms"], second["cache_n"]


def phase_verify(base_url, runs, samples):
    """Check that reused KV produces the same output as a full recompute.

    Greedy decoding is deterministic, so identical token ids mean the cached
    (and, for the shifted case, the KV-shifted) state is numerically equivalent
    to recomputing the prompt from scratch.
    """
    print(f"[4] output equivalence: cache off vs cache on, {samples} samples", flush=True)
    prefix = tile(base_url, BASE_TEXT, PREFIX_TOKENS)
    header = tile(base_url, "第一份任务说明，用于测试缓存复用。" * 4, HEADER_TOKENS)
    document = tile(base_url, BASE_TEXT, DOCUMENT_TOKENS)

    def divergence(left, right):
        # never let an empty token list pass as "identical"
        if not left["generated_tokens"] or not right["generated_tokens"]:
            raise RuntimeError("no generated tokens captured - comparison would be vacuous")
        if left["generated_tokens"] == right["generated_tokens"]:
            return None
        return next(
            i for i, (x, y) in enumerate(zip(left["generated_tokens"], right["generated_tokens"]))
            if x != y
        )

    exact_ok = 0
    exact_stable = 0
    shift_ok = 0
    shift_stable = 0
    for index in range(samples):
        prompt = prefix + build_tail(base_url, 40 + index)
        off = run(base_url, prompt, f"exact prefix #{index} (off)", False, runs)
        on = run(base_url, prompt, f"exact prefix #{index} (on)", True, runs)
        on_again = run(base_url, prompt, f"exact prefix #{index} (on again)", True, runs)
        exact_ok += divergence(off, on) is None
        exact_stable += on["generated_tokens"] == on_again["generated_tokens"]

        old = header + document + build_tail(base_url, 60 + index)
        new = document + build_tail(base_url, 80 + index)
        run(base_url, old, f"moved #{index} baseline (off)", False, runs)
        moved_off = run(base_url, new, f"moved #{index} (off)", False, runs)
        run(base_url, old, f"moved #{index} baseline again (off)", False, runs)
        moved_on = run(base_url, new, f"moved #{index} (on)", True, runs)
        moved_again = run(base_url, new, f"moved #{index} (on again)", True, runs)
        shift_ok += divergence(moved_off, moved_on) is None
        shift_stable += moved_on["generated_tokens"] == moved_again["generated_tokens"]

    print(
        f"  vs full recompute  - prefix reuse: {exact_ok}/{samples}, moved chunk: {shift_ok}/{samples}\n"
        f"  vs itself (2x reuse) - prefix reuse: {exact_stable}/{samples}, moved chunk: {shift_stable}/{samples}",
        flush=True,
    )
    return {
        "exact_prefix_identical_to_recompute": exact_ok,
        "exact_prefix_reuse_repeatable": exact_stable,
        "moved_chunk_identical_to_recompute": shift_ok,
        "moved_chunk_reuse_repeatable": shift_stable,
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--phases", default="same_slot,switch")
    parser.add_argument("--verify-samples", type=int, default=3)
    parser.add_argument("--output", default="cache_reuse_raw.json")
    args = parser.parse_args()

    phases = [value.strip() for value in args.phases.split(",") if value.strip()]
    runs = []
    summary = {}

    for phase in phases:
        if phase == "same_slot":
            summary["cold_prompt_ms"] = phase_same_slot(args.base_url, runs)
        elif phase == "switch":
            phase_switch(args.base_url, runs)
        elif phase == "reuse":
            cold, warm = phase_reuse(args.base_url, runs)
            summary["reuse_cold_prompt_ms"] = cold
            summary["reuse_cache_n"] = warm
        elif phase == "verify":
            summary.update(phase_verify(args.base_url, runs, args.verify_samples))
        else:
            raise SystemExit(f"unknown phase: {phase}")

    payload = {"base_url": args.base_url, "phases": phases, "runs": runs, "summary": summary}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
    print(f"\nraw runs written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
