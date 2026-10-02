#!/usr/bin/env python3
"""Benchmark llama-server decode throughput at several concurrency levels."""

import argparse
import concurrent.futures
import json
import statistics
import threading
import time
import urllib.request


def request_once(url, model, request_id, max_tokens, barrier=None):
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "List practical precautions for reproducible scientific data "
                    f"processing. Request id: {request_id}."
                ),
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "ignore_eos": True,
        "seed": 1000 + request_id,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    if barrier is not None:
        barrier.wait()

    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as response:
        result = json.load(response)
    elapsed = time.perf_counter() - started

    timings = result["timings"]
    return {
        "elapsed_seconds": elapsed,
        "prompt_tokens": timings["prompt_n"],
        "generated_tokens": timings["predicted_n"],
        "prompt_tokens_per_second": timings["prompt_per_second"],
        "decode_tokens_per_second": timings["predicted_per_second"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8081/v1/chat/completions",
    )
    parser.add_argument("--model", default="qwen2.5-7b-instruct")
    parser.add_argument("--concurrency", default="1,2,4")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()

    concurrency_levels = [int(value) for value in args.concurrency.split(",")]

    # Warm up model graphs and the HTTP/chat-template path.
    request_once(args.url, args.model, 99999, 32)

    output = {
        "server_url": args.url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "repetitions": args.repetitions,
        "results": [],
    }

    for concurrency in concurrency_levels:
        runs = []
        for repetition in range(args.repetitions):
            barrier = threading.Barrier(concurrency)
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=concurrency
            ) as executor:
                futures = [
                    executor.submit(
                        request_once,
                        args.url,
                        args.model,
                        concurrency * 10000 + repetition * 100 + request_index,
                        args.max_tokens,
                        barrier,
                    )
                    for request_index in range(concurrency)
                ]
                requests = [future.result() for future in futures]
            wall_seconds = time.perf_counter() - started
            generated_tokens = sum(item["generated_tokens"] for item in requests)
            runs.append(
                {
                    "repetition": repetition + 1,
                    "wall_seconds": wall_seconds,
                    "generated_tokens": generated_tokens,
                    "aggregate_tokens_per_second": generated_tokens / wall_seconds,
                    "mean_request_decode_tokens_per_second": statistics.fmean(
                        item["decode_tokens_per_second"] for item in requests
                    ),
                    "requests": requests,
                }
            )

        output["results"].append(
            {
                "concurrency": concurrency,
                "aggregate_tokens_per_second_median": statistics.median(
                    run["aggregate_tokens_per_second"] for run in runs
                ),
                "request_decode_tokens_per_second_median": statistics.median(
                    run["mean_request_decode_tokens_per_second"] for run in runs
                ),
                "wall_seconds_median": statistics.median(
                    run["wall_seconds"] for run in runs
                ),
                "runs": runs,
            }
        )

    print(json.dumps(output, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
