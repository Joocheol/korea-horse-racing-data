from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from .client import KRAClient
from .config import ENDPOINTS
from .models import RequestUnit


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Probe exactly one KRA OpenAPI page")
    result.add_argument("--endpoint", choices=tuple(ENDPOINTS), required=True)
    result.add_argument("--meet", type=int, required=True)
    result.add_argument("--month", required=True)
    result.add_argument("--race-date")
    result.add_argument("--race-no", type=int)
    result.add_argument("--pool")
    result.add_argument("--page-no", type=int, default=1)
    result.add_argument("--num-rows", type=int, default=10)
    result.add_argument("--timeout", type=float, default=20.0)
    result.add_argument("--max-attempts", type=int, default=2)
    result.add_argument("--service-key-env", default="DATA_GO_KR_SERVICE_KEY")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.page_no < 1:
        raise SystemExit("page_no must be positive")
    if args.num_rows < 1:
        raise SystemExit("num_rows must be positive")
    if args.timeout <= 0:
        raise SystemExit("timeout must be positive")
    if args.race_date is not None:
        if len(args.race_date) != 8 or not args.race_date.isdigit():
            raise SystemExit("race_date must be YYYYMMDD")
        if not args.race_date.startswith(args.month):
            raise SystemExit("race_date must belong to month")
    if args.race_no is not None and args.race_no < 1:
        raise SystemExit("race_no must be positive")
    if args.race_no is not None and args.race_date is None:
        raise SystemExit("race_no requires race_date")

    endpoint = ENDPOINTS[args.endpoint]
    pool = args.pool
    if pool is None and None not in endpoint.pools:
        pool = endpoint.pools[0]
    unit = RequestUnit(args.endpoint, args.meet, args.month, pool)

    service_key = os.environ.get(args.service_key_env, "")
    if not service_key:
        raise SystemExit(f"required secret is missing: {args.service_key_env}")

    request_info = {
        "endpoint": unit.endpoint,
        "service": endpoint.service,
        "meet": unit.meet,
        "month": unit.month,
        "race_date": args.race_date,
        "race_no": args.race_no,
        "pool": unit.pool,
        "page_no": args.page_no,
        "num_rows": args.num_rows,
        "timeout": args.timeout,
        "max_attempts": args.max_attempts,
    }
    query_overrides: dict[str, str | int | None] | None = None
    if args.race_date is not None:
        query_overrides = {
            "rc_month": None,
            "rc_date": args.race_date,
            "rc_no": args.race_no,
        }
    try:
        page = KRAClient(
            service_key,
            timeout=args.timeout,
            max_attempts=args.max_attempts,
        ).fetch_page(
            unit,
            args.page_no,
            args.num_rows,
            query_overrides=query_overrides,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "request": request_info,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": "success",
                "request": request_info,
                "response": {
                    "response_format": page.response_format,
                    "total_count": page.total_count,
                    "row_count": len(page.rows),
                    "bytes": len(page.raw_body),
                    "sha256": hashlib.sha256(page.raw_body).hexdigest(),
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
