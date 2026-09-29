"""命令行入口。默认停在 D4；--continue-from-d5 才跑轨迹。"""

from __future__ import annotations

import argparse
from pathlib import Path

from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.PIPE_pipeline import continue_from_d5, generate_until_d4


def main() -> None:
    """解析参数并调用编排。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--categories", default="", help="逗号分隔，如 T1 或 T1,T2；空则五类都跑")
    parser.add_argument("--continue-from-d5", action="store_true")
    args = parser.parse_args()
    raw_dir = Path(args.output_dir) / "data_raw" / "api"
    client = DeepSeekClient(raw_dir=raw_dir)
    selected = tuple(item.strip() for item in args.categories.split(",") if item.strip()) or None
    if args.continue_from_d5:
        result = continue_from_d5(args.output_dir, client)
    else:
        result = generate_until_d4(
            count_per_category=args.per_category,
            seed=args.seed,
            output_dir=args.output_dir,
            client=client,
            categories=selected,
        )
    print(result)


if __name__ == "__main__":
    main()
