from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .client import KRAClient
from .collector import collect_units
from .config import DEFAULT_ENDPOINTS, MEETS
from .ledger import Ledger
from .planning import build_units
from .preflight import _csv_ints, _csv_strings, check_budget


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


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    units = build_units(args.start_year, args.end_year, _csv_ints(args.meets), _csv_strings(args.endpoints))
    if args.max_units is not None and args.max_units < 1:
        raise SystemExit("max_units must be positive")
    completed = Ledger(args.output / "ledger.json").completed()
    pending = [unit for unit in units if unit.key not in completed]
    selected = pending[: args.max_units] if args.max_units is not None else pending
    used = json.loads(args.used_json)
    budgets = check_budget(selected, {str(k): int(v) for k, v in used.items()})
    if not all(item.allowed for item in budgets):
        raise SystemExit("preflight blocked collection: API budget exceeded")
    service_key = os.environ.get(args.service_key_env, "")
    if not service_key:
        raise SystemExit(f"required secret is missing: {args.service_key_env}")
    processed, skipped = collect_units(KRAClient(service_key), selected, args.output)
    print(json.dumps({"processed": processed, "skipped": skipped}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
