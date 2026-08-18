from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .cli import month_range
from .client import KRAClient, KRAError, sha256_bytes
from .collect import canonical_json, write_atomic
from .registry import ENDPOINTS

OPERATING_CAPS = {"api179": 2_500}
DEFAULT_OPERATING_CAP = 8_333


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight a KRA collection run")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--meets", required=True)
    parser.add_argument("--endpoints", required=True)
    parser.add_argument("--page-size", type=int, default=100_000)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    months = month_range(args.start, args.end)
    meets = [int(value) for value in args.meets.split(",") if value]
    endpoint_ids = [value for value in args.endpoints.split(",") if value]
    unknown = [value for value in endpoint_ids if value not in ENDPOINTS]
    if unknown:
        raise SystemExit(f"unknown endpoints: {', '.join(unknown)}")

    budgets: dict[str, dict[str, int]] = {}
    for endpoint_id in endpoint_ids:
        logical = len(ENDPOINTS[endpoint_id].pools) * len(meets) * len(months)
        conservative = logical * 3
        cap = OPERATING_CAPS.get(endpoint_id, DEFAULT_OPERATING_CAP)
        budgets[endpoint_id] = {
            "logical_requests": logical,
            "conservative_requests": conservative,
            "operating_cap": cap,
        }
        if conservative > cap:
            raise SystemExit(
                f"preflight budget exceeds operating cap for {endpoint_id}: "
                f"{conservative}>{cap}"
            )

    secret = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not secret:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")

    probes: list[dict[str, object]] = []
    try:
        client = KRAClient(secret)
        for endpoint_id in endpoint_ids:
            spec = ENDPOINTS[endpoint_id]
            for pool in spec.pools:
                params: dict[str, object] = {
                    "meet": meets[0],
                    "rc_month": months[0].replace("-", ""),
                    "pageNo": 1,
                    "numOfRows": 1,
                    "_type": "json",
                }
                if pool is not None:
                    params["pool"] = pool
                content, _, envelope = client.get(spec.path, params)
                probes.append(
                    {
                        "endpoint_id": endpoint_id,
                        "pool": pool,
                        "result_code": envelope.result_code,
                        "response_format": envelope.response_format,
                        "total_count": envelope.total_count,
                        "raw_sha256": sha256_bytes(content),
                    }
                )
    except KRAError as exc:
        print(f"preflight_failed={type(exc).__name__}: {exc}")
        return 2

    report = {
        "status": "ready",
        "key_id": os.environ.get("DATA_GO_KR_KEY_ID", "data-go-kr-service-key"),
        "key_candidate": client.key_candidate,
        "range": {"start": args.start, "end": args.end},
        "meets": meets,
        "endpoints": endpoint_ids,
        "page_size": args.page_size,
        "budgets": budgets,
        "approval_probes": probes,
    }
    write_atomic(Path(args.output), canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
