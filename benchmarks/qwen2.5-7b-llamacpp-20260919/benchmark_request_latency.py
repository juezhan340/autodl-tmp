#!/usr/bin/env python3
"""Measure TTFT and full streamed request latency at fixed prompt lengths."""

import argparse
import json
import statistics
import time
import urllib.request


def post_json(url, body, timeout=300):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def get_token_id(base_url):
    with post_json(
        f"{base_url}/tokenize",
        {"content": " data", "add_special": False},
    ) as response:
        tokens = json.load(response)["tokens"]
    if not tokens:
        raise RuntimeError("The tokenizer returned no tokens")
    return tokens[0]


def stream_once(base_url, token_id, prompt_tokens, output_tokens, seed):
    body = {
        "prompt": [token_id] * prompt_tokens,
        "stream": True,
        "return_tokens": True,
        "return_progress": True,
        "cache_prompt": False,
        "temperature": 0,
        "n_predict": output_tokens,
        "ignore_eos": True,
        "seed": seed,
    }

    started = time.perf_counter()
    first_token_at = None
    observed_generated_tokens = 0
    final_event = None

    with post_json(f"{base_url}/completion", body) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue

            event = json.loads(payload)
            tokens = event.get("tokens") or []
            is_generated_token = (
                "prompt_progress" not in event
                and event.get("tokens_predicted", 0) > 0
                and bool(tokens)
            )
            if is_generated_token:
                now = time.perf_counter()
                if first_token_at is None:
                    first_token_at = now
                observed_generated_tokens += len(tokens)
            if event.get("stop"):
                final_event = event

    completed = time.perf_counter()
    if first_token_at is None:
        raise RuntimeError("No generated token was observed in the SSE stream")

    generated_tokens = (final_event or {}).get(
        "tokens_predicted", observed_generated_tokens
    )
    decode_window = completed - first_token_at
    server_timings = (final_event or {}).get("timings") or {}
    return {
        "prompt_tokens": prompt_tokens,
        "requested_output_tokens": output_tokens,
        "generated_tokens": generated_tokens,
        "ttft_seconds": first_token_at - started,
        "total_seconds": completed - started,
        "stream_decode_tokens_per_second": (
            max(generated_tokens - 1, 0) / decode_window if decode_window > 0 else 0
        ),
        "server_decode_tokens_per_second": server_timings.get(
            "predicted_per_second"
        ),
        "server_timings": server_timings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--prompt-lengths", default="512,2048,8192,16384,32768")
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()

    prompt_lengths = [int(value) for value in args.prompt_lengths.split(",")]
    token_id = get_token_id(args.base_url)

    # Warm up model graphs, streaming, and the HTTP path.
    stream_once(args.base_url, token_id, 128, 16, seed=99999)

    runs_by_length = {length: [] for length in prompt_lengths}
    for repetition in range(args.repetitions):
        order = prompt_lengths if repetition % 2 == 0 else list(reversed(prompt_lengths))
        for prompt_tokens in order:
            run = stream_once(
                args.base_url,
                token_id,
                prompt_tokens,
                args.output_tokens,
                seed=1000 + repetition,
            )
            run["repetition"] = repetition + 1
            runs_by_length[prompt_tokens].append(run)

    results = []
    for prompt_tokens in prompt_lengths:
        runs = runs_by_length[prompt_tokens]
        results.append(
            {
                "prompt_tokens": prompt_tokens,
                "ttft_seconds_median": statistics.median(
                    run["ttft_seconds"] for run in runs
                ),
                "total_seconds_median": statistics.median(
                    run["total_seconds"] for run in runs
                ),
                "stream_decode_tokens_per_second_median": statistics.median(
                    run["stream_decode_tokens_per_second"] for run in runs
                ),
                "runs": runs,
            }
        )

    print(
        json.dumps(
            {
                "base_url": args.base_url,
                "prompt_token_id": token_id,
                "output_tokens": args.output_tokens,
                "repetitions": args.repetitions,
                "results": results,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
