from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .client import KRAAuthenticationError, KRAClient, KRAError
from .collect import Collector
from .registry import ENDPOINTS


def month_range(start: str, end: str) -> list[str]:
    start_year, start_month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    if (start_year, start_month) > (end_year, end_month):
        raise ValueError("start month is after end month")
    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        if month < 1 or month > 12:
            raise ValueError("month must be between 01 and 12")
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect KRA OpenAPI data with manifests")
    parser.add_argument("--start", default="2020-01", help="first month, YYYY-MM")
    parser.add_argument("--end", default="2021-12", help="last month, YYYY-MM")
    parser.add_argument("--meets", default="1,2,3", help="comma-separated meet codes")
    parser.add_argument(
        "--endpoints",
        default="api28,api29,api30,api179",
        help="comma-separated registry IDs",
    )
    parser.add_argument("--output", default="data/pilot-2020-2021")
    parser.add_argument("--page-size", type=int, default=100_000)
    parser.add_argument("--snapshot-id", default=os.environ.get("GITHUB_RUN_ID"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    months = month_range(args.start, args.end)
    meets = [int(value) for value in args.meets.split(",") if value]
    endpoint_ids = [value for value in args.endpoints.split(",") if value]
    unknown = [value for value in endpoint_ids if value not in ENDPOINTS]
    if unknown:
        raise SystemExit(f"unknown endpoints: {', '.join(unknown)}")
    if any(meet not in {1, 2, 3} for meet in meets):
        raise SystemExit("pilot meet codes must be drawn from 1,2,3")

    logical_requests = sum(
        len(ENDPOINTS[endpoint_id].pools) * len(meets) * len(months)
        for endpoint_id in endpoint_ids
    )
    print(
        json.dumps(
            {
                "start": args.start,
                "end": args.end,
                "meets": meets,
                "endpoints": endpoint_ids,
                "logical_requests_before_pagination": logical_requests,
                "page_size": args.page_size,
            },
            ensure_ascii=False,
        )
    )
    if args.dry_run:
        return 0

    secret = os.environ.get("DATA_GO_KR_SERVICE_KEY") or os.environ.get("KRA_SERVICE_KEY")
    if not secret:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY (or KRA_SERVICE_KEY) is required")

    try:
        client = KRAClient(secret)
        print(f"service_key_input_form={client.input_key_form}; normalized_for_single_encoding=true")
        collector = Collector(
            client,
            Path(args.output),
            page_size=args.page_size,
            snapshot_id=args.snapshot_id,
        )
        completed = 0
        for month in months:
            for meet in meets:
                for endpoint_id in endpoint_ids:
                    spec = ENDPOINTS[endpoint_id]
                    for pool in spec.pools:
                        record = collector.collect_month(spec, meet, month, pool)
                        completed += 1
                        print(
                            json.dumps(
                                {
                                    "completed": completed,
                                    "endpoint": endpoint_id,
                                    "meet": meet,
                                    "month": month,
                                    "pool": pool,
                                    "totalCount": record.total_count,
                                    "stored_rows": record.stored_rows,
                                },
                                ensure_ascii=False,
                            )
                        )
    except (KRAAuthenticationError, KRAError) as exc:
        print(f"collection_failed={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
