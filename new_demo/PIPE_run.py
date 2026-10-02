"""命令行入口。默认停在 D4；--full 一次跑到数据集；--quota 每类凑满成功条数；--continue-from-d5 只跑后半段。"""

from __future__ import annotations

import argparse
from pathlib import Path

from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.PIPE_pipeline import continue_from_d5, generate_until_d4, run_full_pipeline, run_quota_pipeline


def main() -> None:
    """解析参数并调用编排。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--categories", default="", help="逗号分隔，如 T1 或 T1,T2；空则五类都跑")
    parser.add_argument("--workers", type=int, default=1, help="并发条数，D2–D4 与 D5–D6 两段都用")
    parser.add_argument("--full", action="store_true", help="D4 之后立刻 D5→D6，不停闸")
    parser.add_argument("--continue-from-d5", action="store_true")
    parser.add_argument("--quota", action="store_true", help="每类凑满成功轨迹，默认每类最多 100 次、目标 50 条")
    parser.add_argument("--target-success", type=int, default=50, help="配额模式：每类成功条数")
    parser.add_argument("--max-attempts", type=int, default=100, help="配额模式：每类最多尝试次数")
    parser.add_argument(
        "--workers-per-category",
        type=int,
        default=0,
        help="配额模式每类并发；0 则用 10，或 workers/类数",
    )
    args = parser.parse_args()
    raw_dir = Path(args.output_dir) / "data_raw" / "api"
    client = DeepSeekClient(raw_dir=raw_dir)
    selected = tuple(item.strip() for item in args.categories.split(",") if item.strip()) or None
    if args.quota and args.continue_from_d5:
        raise SystemExit("cannot combine --quota with --continue-from-d5")
    if args.quota:
        n_cat = len(selected) if selected else 5
        if args.workers_per_category > 0:
            workers_per_category = args.workers_per_category
        elif args.workers > 1:
            workers_per_category = max(1, args.workers // n_cat)
        else:
            workers_per_category = 10
        result = run_quota_pipeline(
            target_success=args.target_success,
            max_attempts=args.max_attempts,
            seed=args.seed,
            output_dir=args.output_dir,
            client=client,
            categories=selected,
            workers_per_category=workers_per_category,
        )
    elif args.continue_from_d5:
        result = continue_from_d5(args.output_dir, client, workers=args.workers)
    elif args.full:
        result = run_full_pipeline(
            count_per_category=args.per_category,
            seed=args.seed,
            output_dir=args.output_dir,
            client=client,
            categories=selected,
            workers=args.workers,
        )
    else:
        result = generate_until_d4(
            count_per_category=args.per_category,
            seed=args.seed,
            output_dir=args.output_dir,
            client=client,
            categories=selected,
            workers=args.workers,
        )
    print(result)


if __name__ == "__main__":
    main()
