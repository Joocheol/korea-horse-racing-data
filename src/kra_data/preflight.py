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
    endpoint: str
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
        # TRI months can exceed 100,000 rows. Conservatively reserve two pages.
        calls = 2 if unit.endpoint == "triple" and unit.pool == "TRI" else 1
        counts[unit.endpoint] += calls
    return counts


def check_budget(
    units: Iterable[RequestUnit], used: dict[str, int] | None = None, safety_rate: float = 0.10
) -> list[BudgetResult]:
    used = used or {}
    estimates = estimate_calls(units)
    results: list[BudgetResult] = []
    for name, estimated in sorted(estimates.items()):
        margin = max(1, int(estimated * safety_rate + 0.9999))
        results.append(
            BudgetResult(name, estimated, int(used.get(name, 0)), margin, ENDPOINTS[name].daily_limit)
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
        args.start_year,
        args.end_year,
        _csv_ints(args.meets),
        _csv_strings(args.endpoints),
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
        "budgets": [
            {
                "endpoint": item.endpoint,
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
