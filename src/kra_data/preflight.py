from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .config import DEFAULT_ENDPOINTS, ENDPOINTS, MEETS
from .models import RequestUnit
from .planning import build_units


@dataclass(frozen=True)
class BudgetResult:
    service: str
    estimated_calls: int
    used_calls: int
    safety_margin: int
    daily_limit: int

    @property
    def allowed(self) -> bool:
        return self.estimated_calls + self.used_calls + self.safety_margin <= self.daily_limit


def estimate_calls(units: Iterable[RequestUnit]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for unit in units:
        endpoint = ENDPOINTS[unit.endpoint]
        # API30_1 TRI can exceed numOfRows=100,000 in a busy month.
        calls = 2 if endpoint.service == "API30_1" and unit.pool == "TRI" else 1
        counts[endpoint.service] += calls
    return counts


def check_budget(
    units: Iterable[RequestUnit], used: dict[str, int] | None = None, safety_rate: float = 0.10
) -> list[BudgetResult]:
    used = used or {}
    estimates = estimate_calls(units)
    limits = {endpoint.service: endpoint.daily_limit for endpoint in ENDPOINTS.values()}
    results: list[BudgetResult] = []
    for service, estimated in sorted(estimates.items()):
        margin = max(1, int(estimated * safety_rate + 0.9999))
        results.append(
            BudgetResult(service, estimated, int(used.get(service, 0)), margin, limits[service])
        )
    return results


def _csv_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in value.split(",") if item)


def _csv_strings(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split(",") if item)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Plan KRA collection and enforce API budgets")
    result.add_argument("--start-year", type=int, required=True)
    result.add_argument("--end-year", type=int, required=True)
    result.add_argument("--meets", default=",".join(map(str, MEETS)))
    result.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS))
    result.add_argument("--used-json", default="{}")
    result.add_argument("--max-units", type=int)
    return result


def make_plan(args: argparse.Namespace) -> tuple[list[RequestUnit], list[BudgetResult]]:
    units = build_units(
        args.start_year, args.end_year, _csv_ints(args.meets), _csv_strings(args.endpoints)
    )
    if args.max_units is not None:
        if args.max_units < 1:
            raise ValueError("max_units must be positive")
        units = units[: args.max_units]
    used = json.loads(args.used_json)
    if not isinstance(used, dict):
        raise ValueError("used_json must be an object")
    return units, check_budget(units, used={str(k): int(v) for k, v in used.items()})


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    units, budgets = make_plan(args)
    report = {
        "units": len(units),
        "first_unit": units[0].key if units else None,
        "last_unit": units[-1].key if units else None,
        "estimated_calls_total": sum(item.estimated_calls for item in budgets),
        "budgets": [
            {
                "service": item.service,
                "estimated_calls": item.estimated_calls,
                "used_calls": item.used_calls,
                "safety_margin": item.safety_margin,
                "daily_limit": item.daily_limit,
                "allowed": item.allowed,
            }
            for item in budgets
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.allowed for item in budgets) else 2


if __name__ == "__main__":
    raise SystemExit(main())
