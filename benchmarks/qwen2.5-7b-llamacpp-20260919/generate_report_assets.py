#!/usr/bin/env python3
"""Create CSV summaries and charts from the raw benchmark JSON files."""

import csv
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
CONCURRENCY_JSON = ROOT / "concurrency_raw.json"
CONTEXT_JSON = ROOT / "context_depth_raw.json"
REQUEST_LATENCY_JSON = ROOT / "request_latency_raw.json"
CONCURRENCY_CSV = ROOT / "concurrency_summary.csv"
CONTEXT_CSV = ROOT / "context_depth_summary.csv"
REQUEST_LATENCY_CSV = ROOT / "request_latency_summary.csv"
CHART_PNG = ROOT / "qwen2.5-7b-llamacpp-throughput.png"
CHART_SVG = ROOT / "qwen2.5-7b-llamacpp-throughput.svg"


def sample_stddev(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def load_concurrency():
    with CONCURRENCY_JSON.open() as handle:
        raw = json.load(handle)

    rows = []
    for result in raw["results"]:
        aggregate = [run["aggregate_tokens_per_second"] for run in result["runs"]]
        per_request = [
            run["mean_request_decode_tokens_per_second"] for run in result["runs"]
        ]
        rows.append(
            {
                "concurrency": result["concurrency"],
                "per_request_decode_tps": statistics.median(per_request),
                "per_request_decode_tps_stddev": sample_stddev(per_request),
                "aggregate_tps": statistics.median(aggregate),
                "aggregate_tps_stddev": sample_stddev(aggregate),
                "wall_seconds": result["wall_seconds_median"],
                "generated_tokens_per_run": (
                    result["concurrency"] * raw["max_tokens"]
                ),
                "repetitions": raw["repetitions"],
            }
        )
    return rows


def load_context():
    with CONTEXT_JSON.open() as handle:
        raw = json.load(handle)

    by_depth = {}
    for result in raw:
        depth = result["n_depth"]
        row = by_depth.setdefault(
            depth,
            {
                "context_depth": depth,
                "repetitions": len(result["samples_ts"]),
            },
        )
        if result["n_prompt"]:
            row["prefill_512_tps"] = result["avg_ts"]
            row["prefill_512_tps_stddev"] = result["stddev_ts"]
        if result["n_gen"]:
            row["decode_128_tps"] = result["avg_ts"]
            row["decode_128_tps_stddev"] = result["stddev_ts"]

    return [by_depth[depth] for depth in sorted(by_depth)]


def load_request_latency():
    with REQUEST_LATENCY_JSON.open() as handle:
        raw = json.load(handle)

    rows = []
    for result in raw["results"]:
        ttft = [run["ttft_seconds"] for run in result["runs"]]
        total = [run["total_seconds"] for run in result["runs"]]
        decode = [
            run["server_decode_tokens_per_second"]
            for run in result["runs"]
        ]
        rows.append(
            {
                "prompt_tokens": result["prompt_tokens"],
                "ttft_ms": statistics.median(ttft) * 1000,
                "ttft_ms_stddev": sample_stddev(ttft) * 1000,
                "total_request_seconds": statistics.median(total),
                "total_request_seconds_stddev": sample_stddev(total),
                "decode_tokens_per_second": statistics.median(decode),
                "decode_tokens_per_second_stddev": sample_stddev(decode),
                "output_tokens": raw["output_tokens"],
                "repetitions": raw["repetitions"],
            }
        )
    return rows


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def annotate_bars(axis, bars, fmt="{:.1f}"):
    for bar in bars:
        axis.annotate(
            fmt.format(bar.get_height()),
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )


def make_chart(concurrency, request_latency):
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
        }
    )

    figure, (axis_concurrency, axis_ttft, axis_total) = plt.subplots(
        3,
        1,
        figsize=(12, 14),
    )

    concurrency_x = np.arange(len(concurrency))
    request_values = [row["per_request_decode_tps"] for row in concurrency]
    request_errors = [
        row["per_request_decode_tps_stddev"] for row in concurrency
    ]

    request_bars = axis_concurrency.bar(
        concurrency_x,
        request_values,
        yerr=request_errors,
        capsize=4,
        color="#2878B5",
    )
    axis_concurrency.set_title("Output decode speed per request")
    axis_concurrency.set_xlabel("Concurrent requests")
    axis_concurrency.set_ylabel("Decode token/s")
    axis_concurrency.set_xticks(
        concurrency_x,
        [str(row["concurrency"]) for row in concurrency],
    )
    axis_concurrency.set_ylim(0, max(request_values) * 1.25)
    annotate_bars(axis_concurrency, request_bars)

    context_x = np.arange(len(request_latency))
    context_labels = [
        f"{row['prompt_tokens'] // 1024}K"
        if row["prompt_tokens"] >= 1024
        else str(row["prompt_tokens"])
        for row in request_latency
    ]
    ttft_values = [row["ttft_ms"] for row in request_latency]
    ttft_errors = [row["ttft_ms_stddev"] for row in request_latency]
    total_values = [row["total_request_seconds"] for row in request_latency]
    total_errors = [
        row["total_request_seconds_stddev"] for row in request_latency
    ]

    axis_ttft.errorbar(
        context_x,
        ttft_values,
        yerr=ttft_errors,
        marker="o",
        markersize=7,
        linewidth=2.2,
        capsize=4,
        color="#C85A17",
    )
    axis_ttft.set_title("TTFT (time to first token)")
    axis_ttft.set_xlabel("Input context length (tokens)")
    axis_ttft.set_ylabel("TTFT (ms)")
    axis_ttft.set_xticks(context_x, context_labels)
    axis_ttft.set_ylim(0, max(ttft_values) * 1.22)
    for x, value in zip(context_x, ttft_values):
        axis_ttft.annotate(
            f"{value:.0f} ms",
            (x, value),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color="#9E4611",
        )

    axis_total.errorbar(
        context_x,
        total_values,
        yerr=total_errors,
        marker="s",
        markersize=7,
        linewidth=2.2,
        capsize=4,
        color="#2E8B57",
    )
    axis_total.set_title("Full request latency")
    axis_total.set_xlabel("Input context length (tokens)")
    axis_total.set_ylabel("Request time (s)")
    axis_total.set_xticks(context_x, context_labels)
    axis_total.set_ylim(0, max(total_values) * 1.22)
    for x, value in zip(context_x, total_values):
        axis_total.annotate(
            f"{value:.2f} s",
            (x, value),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color="#206A42",
        )

    figure.suptitle(
        "Measured llama.cpp request performance: RTX 4090 + Qwen2.5-7B-Instruct Q5_K_M",
        fontsize=15,
        fontweight="bold",
        y=0.995,
    )
    figure.text(
        0.5,
        0.012,
        "Three repetitions per point; 128 output tokens; single request for latency tests; full GPU offload; Flash Attention enabled.",
        ha="center",
        fontsize=9,
        color="#444444",
    )
    figure.subplots_adjust(
        left=0.09,
        right=0.96,
        bottom=0.08,
        top=0.93,
        hspace=0.52,
    )

    figure.savefig(CHART_PNG, dpi=200, bbox_inches="tight")
    figure.savefig(CHART_SVG, bbox_inches="tight")
    plt.close(figure)


def main():
    concurrency = load_concurrency()
    context = load_context()
    request_latency = load_request_latency()
    write_csv(CONCURRENCY_CSV, concurrency)
    write_csv(CONTEXT_CSV, context)
    write_csv(REQUEST_LATENCY_CSV, request_latency)
    make_chart(concurrency, request_latency)
    print(CONCURRENCY_CSV)
    print(CONTEXT_CSV)
    print(REQUEST_LATENCY_CSV)
    print(CHART_PNG)
    print(CHART_SVG)


if __name__ == "__main__":
    main()
