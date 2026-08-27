from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import KRAClient, Page
from .models import RequestUnit


EXPECTED_2025_BACKFILL_ROWS = {2: 1_562, 3: 2_304}
EXPECTED_RACES = set(range(1, 9))


def _as_int(value: Any) -> int:
    return int(str(value).strip())


def analyze_2025_gap(rows_by_meet_and_endpoint: dict[int, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    meets: dict[str, Any] = {}
    for meet, groups in sorted(rows_by_meet_and_endpoint.items()):
        group_reports: dict[str, Any] = {}
        observed_total = 0
        for name, rows in sorted(groups.items()):
            races = sorted({_as_int(row["rcNo"]) for row in rows})
            group_reports[name] = {
                "row_count": len(rows),
                "race_numbers": races,
                "all_eight_races_present": set(races) == EXPECTED_RACES,
            }
            observed_total += len(rows)
        expected_total = EXPECTED_2025_BACKFILL_ROWS[meet]
        meets[str(meet)] = {
            "groups": group_reports,
            "observed_total": observed_total,
            "expected_html_backfill_total": expected_total,
            "row_total_matches": observed_total == expected_total,
            "all_groups_cover_eight_races": all(
                report["all_eight_races_present"] for report in group_reports.values()
            ),
        }
        meets[str(meet)]["resolved"] = (
            meets[str(meet)]["row_total_matches"]
            and meets[str(meet)]["all_groups_cover_eight_races"]
        )
    return {
        "case": "2025-10-17 API28_1/API29_1 gap",
        "meets": meets,
        "resolved": all(report["resolved"] for report in meets.values()),
    }


def analyze_2023_placeholders(
    entry_rows: Iterable[dict[str, Any]],
    single_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    valid_chul_no: dict[int, set[int]] = defaultdict(set)
    for row in entry_rows:
        valid_chul_no[_as_int(row["rcNo"])].add(_as_int(row["chulNo"]))

    invalid: list[dict[str, Any]] = []
    for row in single_rows:
        race_no = _as_int(row["rcNo"])
        chul_no = _as_int(row["chulNo"])
        if chul_no not in valid_chul_no[race_no]:
            invalid.append(
                {
                    "rcNo": race_no,
                    "chulNo": chul_no,
                    "pool": row.get("pool"),
                    "odds": row.get("odds"),
                }
            )

    return {
        "case": "2023-03-17 API28_1 out-of-entry placeholders",
        "entry_races": sorted(valid_chul_no),
        "invalid_row_count": len(invalid),
        "invalid_rows": invalid,
        "resolved": len(invalid) == 0,
    }


def analyze_2019_dusu(entry_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    race_rows = [row for row in entry_rows if _as_int(row["rcNo"]) == 6]
    chul_nos = sorted({_as_int(row["chulNo"]) for row in race_rows})
    dusu_values = sorted({_as_int(row["dusu"]) for row in race_rows})
    resolved = len(race_rows) == 10 and len(chul_nos) == 10 and dusu_values == [10]
    return {
        "case": "2019-05-18 Jeju race 6 API26_2 dusu",
        "row_count": len(race_rows),
        "unique_chul_no_count": len(chul_nos),
        "chul_nos": chul_nos,
        "dusu_values": dusu_values,
        "resolved": resolved,
    }


class RecheckRunner:
    def __init__(self, client: KRAClient, output: Path) -> None:
        self.client = client
        self.output = output
        self.raw_dir = output / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.requests: list[dict[str, Any]] = []

    def fetch(
        self,
        endpoint: str,
        meet: int,
        race_date: str,
        *,
        pool: str | None = None,
    ) -> Page:
        unit = RequestUnit(endpoint, meet, race_date[:6], pool, race_date)
        page = self.client.fetch_page(unit, 1, 100_000)
        suffix = pool.lower() if pool else "all"
        filename = f"{race_date}-meet-{meet}-{endpoint}-{suffix}.json"
        path = self.raw_dir / filename
        path.write_bytes(page.raw_body)
        self.requests.append(
            {
                "endpoint": endpoint,
                "meet": meet,
                "race_date": race_date,
                "pool": pool,
                "total_count": page.total_count,
                "row_count": len(page.rows),
                "raw_bytes": len(page.raw_body),
                "sha256": hashlib.sha256(page.raw_body).hexdigest(),
                "raw_file": str(path.relative_to(self.output)),
                "complete": page.total_count == len(page.rows),
            }
        )
        if page.total_count != len(page.rows):
            raise RuntimeError(f"incomplete one-page response for {filename}")
        return page

    def run(self) -> dict[str, Any]:
        rows_2025: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for meet in (2, 3):
            rows_2025[meet] = {
                "single": self.fetch("single", meet, "20251017").rows,
                "double-qnl": self.fetch("double", meet, "20251017", pool="QNL").rows,
                "double-exa": self.fetch("double", meet, "20251017", pool="EXA").rows,
                "double-qpl": self.fetch("double", meet, "20251017", pool="QPL").rows,
            }

        entries_2023 = self.fetch("entries", 3, "20230317").rows
        single_2023 = self.fetch("single", 3, "20230317").rows
        entries_2019 = self.fetch("entries", 2, "20190518").rows

        cases = {
            "gap_2025_10_17": analyze_2025_gap(rows_2025),
            "placeholders_2023_03_17": analyze_2023_placeholders(entries_2023, single_2023),
            "dusu_2019_05_18": analyze_2019_dusu(entries_2019),
        }
        resolved_count = sum(bool(case["resolved"]) for case in cases.values())
        return {
            "schema_version": 1,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "request_count": len(self.requests),
            "requests": self.requests,
            "cases": cases,
            "resolved_count": resolved_count,
            "unresolved_count": len(cases) - resolved_count,
            "all_resolved": resolved_count == len(cases),
            "canonical_update_allowed": resolved_count > 0,
            "note": "Raw responses are evidence only; canonical data must not be overwritten automatically.",
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Recheck KRA provider corrections")
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--service-key-env", default="DATA_GO_KR_SERVICE_KEY")
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument("--max-attempts", type=int, default=5)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    service_key = os.environ.get(args.service_key_env, "")
    if not service_key:
        raise SystemExit(f"required secret is missing: {args.service_key_env}")
    args.output.mkdir(parents=True, exist_ok=True)
    runner = RecheckRunner(
        KRAClient(service_key, timeout=args.timeout, max_attempts=args.max_attempts),
        args.output,
    )
    summary = runner.run()
    summary_path = args.output / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
