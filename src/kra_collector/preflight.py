from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .cli import month_range
from .client import KRAClient, KRAError, sha256_bytes
from .collect import (
    MAX_CALLS_PER_LOGICAL_REQUEST,
    business_key_observation,
    canonical_json,
    write_atomic,
)
from .registry import ENDPOINTS

OFFICIAL_DEVELOPMENT_DAILY_CAP = 3_000
DEFAULT_OPERATING_CAP = 2_500


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight a KRA collection run")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--meets", required=True)
    parser.add_argument("--endpoints", required=True)
    parser.add_argument("--page-size", type=int, default=100_000)
    parser.add_argument("--output", required=True)
    return parser


def _usage_today(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    today = datetime.now(UTC).date().isoformat()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("utc_date") == today:
            counts[str(record["endpoint_id"])] += 1
    return counts


def _operating_cap(endpoint_id: str) -> int:
    return int(
        os.environ.get(
            f"DATA_GO_KR_OPERATING_CAP_{endpoint_id.upper()}",
            DEFAULT_OPERATING_CAP,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    months = month_range(args.start, args.end)
    meets = [int(value) for value in args.meets.split(",") if value]
    endpoint_ids = [value for value in args.endpoints.split(",") if value]
    unknown = [value for value in endpoint_ids if value not in ENDPOINTS]
    if unknown:
        raise SystemExit(f"unknown endpoints: {', '.join(unknown)}")

    ledger_path = Path(os.environ.get("KRA_QUOTA_LEDGER", "quota/usage-current.jsonl"))
    used_before = _usage_today(ledger_path)
    budgets: dict[str, dict[str, int | str]] = {}
    for endpoint_id in endpoint_ids:
        logical = len(ENDPOINTS[endpoint_id].pools) * len(meets) * len(months)
        approval_probes = len(ENDPOINTS[endpoint_id].pools)
        conservative = logical * MAX_CALLS_PER_LOGICAL_REQUEST + approval_probes
        cap = _operating_cap(endpoint_id)
        used = used_before[endpoint_id]
        budgets[endpoint_id] = {
            "account_tier": os.environ.get("DATA_GO_KR_ACCOUNT_TIER", "development"),
            "production_approval_status": os.environ.get(
                "DATA_GO_KR_PRODUCTION_APPROVAL_STATUS", "unverified"
            ),
            "production_review_lead_time": os.environ.get(
                "DATA_GO_KR_PRODUCTION_REVIEW_LEAD_TIME", "unverified"
            ),
            "official_daily_cap": int(
                os.environ.get(
                    f"DATA_GO_KR_DAILY_CAP_{endpoint_id.upper()}",
                    OFFICIAL_DEVELOPMENT_DAILY_CAP,
                )
            ),
            "logical_requests": logical,
            "approval_probe_requests": approval_probes,
            "conservative_requests": conservative,
            "operating_cap": cap,
            "used_today_before_preflight": used,
            "estimated_operating_days": max(1, math.ceil(conservative / cap)),
            "approval_status": "probe_pending",
        }
        if used + conservative > cap:
            raise SystemExit(
                f"preflight budget exceeds operating cap for {endpoint_id}: "
                f"used={used}+planned={conservative}>{cap}"
            )

    api5_cap = _operating_cap("api5")
    api5_planned = 4
    budgets["api5"] = {
        "account_tier": os.environ.get("DATA_GO_KR_ACCOUNT_TIER", "development"),
        "production_approval_status": os.environ.get(
            "DATA_GO_KR_PRODUCTION_APPROVAL_STATUS", "unverified"
        ),
        "production_review_lead_time": os.environ.get(
            "DATA_GO_KR_PRODUCTION_REVIEW_LEAD_TIME", "unverified"
        ),
        "official_daily_cap": int(
            os.environ.get("DATA_GO_KR_DAILY_CAP_API5", OFFICIAL_DEVELOPMENT_DAILY_CAP)
        ),
        "logical_requests": 0,
        "approval_probe_requests": api5_planned,
        "conservative_requests": api5_planned,
        "operating_cap": api5_cap,
        "used_today_before_preflight": used_before["api5"],
        "estimated_operating_days": 1,
        "approval_status": "credential_probe_pending",
    }
    if used_before["api5"] + api5_planned > api5_cap:
        raise SystemExit("preflight budget exceeds operating cap for api5")

    secret = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not secret:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")

    probes: list[dict[str, object]] = []
    probe_keys: dict[str, dict[str, str]] = {}
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
                if envelope.total_count <= 0 or not envelope.rows:
                    raise KRAError(
                        f"business key preflight has no sample row for "
                        f"{endpoint_id}:{pool}"
                    )
                key_hash, observed_aliases = business_key_observation(
                    spec, envelope.rows[0]
                )
                pool_label = str(pool)
                endpoint_keys = probe_keys.setdefault(endpoint_id, {})
                if key_hash in endpoint_keys.values():
                    prior_pool = next(
                        name
                        for name, value in endpoint_keys.items()
                        if value == key_hash
                    )
                    raise KRAError(
                        f"business key preflight collision for {endpoint_id}: "
                        f"pools {prior_pool} and {pool_label}"
                    )
                endpoint_keys[pool_label] = key_hash
                probes.append(
                    {
                        "endpoint_id": endpoint_id,
                        "pool": pool,
                        "result_code": envelope.result_code,
                        "response_format": envelope.response_format,
                        "total_count": envelope.total_count,
                        "raw_sha256": sha256_bytes(content),
                        "business_key_sha256": key_hash,
                        "observed_business_key_aliases": observed_aliases,
                    }
                )
            budgets[endpoint_id]["approval_status"] = "probe_success"
    except KRAError as exc:
        print(f"preflight_failed={type(exc).__name__}: {exc}")
        return 2

    used_after = _usage_today(ledger_path)
    for endpoint_id, budget in budgets.items():
        budget["used_today_after_preflight"] = used_after[endpoint_id]
        budget["remaining_operating_calls"] = (
            int(budget["operating_cap"]) - used_after[endpoint_id]
        )
    budgets["api5"]["approval_status"] = "credential_probe_success"

    report = {
        "status": "ready",
        "key_id": os.environ.get("DATA_GO_KR_KEY_ID", "data-go-kr-service-key"),
        "key_candidate": client.key_candidate,
        "range": {"start": args.start, "end": args.end},
        "meets": meets,
        "endpoints": endpoint_ids,
        "page_size": args.page_size,
        "quota_ledger": ledger_path.as_posix(),
        "budget_policy": "development official cap 3000; operating cap defaults to 2500 (5/6)",
        "budgets": budgets,
        "approval_probes": probes,
    }
    write_atomic(Path(args.output), canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
