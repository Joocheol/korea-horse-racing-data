from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .client import KRAClient
from .collector import collect_units
from .config import DEFAULT_ENDPOINTS, MEETS
from .ledger import Ledger
from .planning import (
    build_monthly_units,
    build_result_units,
    discover_result_dates,
    race_record_coverage_complete,
)
from .preflight import BudgetResult, _csv_ints, _csv_strings, check_budget


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Collect KRA OpenAPI data")
    result.add_argument("--start-year", type=int, required=True)
    result.add_argument("--end-year", type=int, required=True)
    result.add_argument("--meets", default=",".join(map(str, MEETS)))
    result.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS))
    result.add_argument("--output", type=Path, default=Path("output"))
    result.add_argument("--max-units", type=int)
    result.add_argument("--used-json", default="{}")
    result.add_argument("--service-key-env", default="DATA_GO_KR_SERVICE_KEY")
    return result


def _selected_pending(
    units,
    completed: set[str],
    remaining: int | None,
):
    pending = [unit for unit in units if unit.key not in completed]
    return pending if remaining is None else pending[:remaining]


def _enforce_budget(selected, used: dict[str, int]) -> list[BudgetResult]:
    budgets = check_budget(selected, used)
    if not all(item.allowed for item in budgets):
        blocked = ", ".join(item.service for item in budgets if not item.allowed)
        raise SystemExit(f"preflight blocked collection: API budget exceeded ({blocked})")
    return budgets


def _budget_report(budgets: list[BudgetResult]) -> list[dict[str, int | bool | str]]:
    return [
        {
            "service": item.service,
            "estimated_calls": item.estimated_calls,
            "used_calls": item.used_calls,
            "safety_margin": item.safety_margin,
            "daily_limit": item.daily_limit,
            "allowed": item.allowed,
        }
        for item in budgets
    ]


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.max_units is not None and args.max_units < 1:
        raise SystemExit("max_units must be positive")

    meets = _csv_ints(args.meets)
    endpoints = _csv_strings(args.endpoints)
    used_raw = json.loads(args.used_json)
    if not isinstance(used_raw, dict):
        raise SystemExit("used_json must be an object")
    used = {str(k): int(v) for k, v in used_raw.items()}

    phase1_units = build_monthly_units(args.start_year, args.end_year, meets, endpoints)
    ledger = Ledger(args.output / "ledger.json")
    completed = ledger.completed()
    remaining = args.max_units
    phase1_selected = _selected_pending(phase1_units, completed, remaining)
    phase1_budgets = _enforce_budget(phase1_selected, used)

    client: KRAClient | None = None

    def get_client() -> KRAClient:
        nonlocal client
        if client is None:
            service_key = os.environ.get(args.service_key_env, "")
            if not service_key:
                raise SystemExit(f"required secret is missing: {args.service_key_env}")
            client = KRAClient(service_key)
        return client

    phase1_processed = phase1_skipped = 0
    if phase1_selected:
        phase1_processed, phase1_skipped = collect_units(
            get_client(), phase1_selected, args.output
        )
    if remaining is not None:
        remaining -= phase1_processed

    phase2_processed = phase2_skipped = 0
    result_dates: tuple[tuple[int, str], ...] = ()
    results_deferred = False
    phase2_budgets: list[BudgetResult] = []
    phase2_selected_count = 0

    if "results" in endpoints and (remaining is None or remaining > 0):
        if not race_record_coverage_complete(
            args.output, args.start_year, args.end_year, meets
        ):
            results_deferred = True
        else:
            result_dates = discover_result_dates(
                args.output, args.start_year, args.end_year, meets
            )
            result_units = build_result_units(
                args.start_year, args.end_year, meets, result_dates
            )
            completed = Ledger(args.output / "ledger.json").completed()
            phase2_selected = _selected_pending(result_units, completed, remaining)
            phase2_selected_count = len(phase2_selected)
            phase2_budgets = _enforce_budget(phase2_selected, used)
            if phase2_selected:
                phase2_processed, phase2_skipped = collect_units(
                    get_client(), phase2_selected, args.output
                )

    report = {
        "processed": phase1_processed + phase2_processed,
        "skipped": phase1_skipped + phase2_skipped,
        "phase1_processed": phase1_processed,
        "phase2_processed": phase2_processed,
        "phase1_budget": _budget_report(phase1_budgets),
        "phase2_budget": _budget_report(phase2_budgets),
        "phase2_selected_units": phase2_selected_count,
        "result_dates_discovered": len(result_dates),
        "results_deferred": results_deferred,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
