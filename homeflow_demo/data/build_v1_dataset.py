"""阻止旧 V1 构建命令覆盖已经归档的历史数据。"""

from __future__ import annotations


def build_v1_dataset(*args: object, **kwargs: object) -> None:
    """拒绝重建 V1，并指向独立的 V1.2 构建入口。"""
    del args, kwargs
    raise RuntimeError(
        "data_processed/v1 is read-only historical data; "
        "use python -m homeflow_demo.data.build_v1_2_dataset"
    )


def main() -> None:
    """从命令行明确报告旧入口已经冻结。"""
    build_v1_dataset()


if __name__ == "__main__":
    main()
