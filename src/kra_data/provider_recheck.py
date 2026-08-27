from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import combinations, permutations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import KRAClient, Page
from .config import ENDPOINTS
from .models import RequestUnit


EXPECTED_2025_BACKFILL_ROWS = {2: 1_562, 3: 2_304}
EXPECTED_RACES = set(range(1, 9))
PRE_START_WITHDRAWAL_LABELS = {"출전제외", "출전취소"}
POOL_MAP = {
    "단승식": "WIN",
    "연승식": "PLC",
    "복승식": "QNL",
    "쌍승식": "EXA",
    "복연승식": "QPL",
}
GROUP_POOLS = {
    "single": {"WIN", "PLC"},
    "double-qnl": {"QNL"},
    "double-exa": {"EXA"},
    "double-qpl": {"QPL"},
}


def _as_int(value: Any) -> int:
    return int(str(value).strip())


def _odds_key(row: dict[str, Any]) -> tuple[int, str, int, int | None]:
    race_no = _as_int(row["rcNo"])
    pool_text = str(row["pool"]).strip()
    if pool_text not in POOL_MAP:
        raise ValueError(f"unknown pool label: {pool_text!r}")
    pool = POOL_MAP[pool_text]
    if pool in {"WIN", "PLC"}:
        return race_no, pool, _as_int(row["chulNo"]), None
    first = _as_int(row["chulNo1"])
    second = _as_int(row["chulNo2"])
    if pool in {"QNL", "QPL"}:
        first, second = sorted((first, second))
    return race_no, pool, first, second


def _expected_group_keys(
    group: str,
    entries_by_race: dict[int, set[int]],
) -> set[tuple[int, str, int, int | None]]:
    result: set[tuple[int, str, int, int | None]] = set()
    for race_no, horses in entries_by_race.items():
        ordered = sorted(horses)
        if group == "single":
            for pool in ("WIN", "PLC"):
                result.update((race_no, pool, horse, None) for horse in ordered)
        elif group in {"double-qnl", "double-qpl"}:
            pool = "QNL" if group == "double-qnl" else "QPL"
            result.update((race_no, pool, first, second) for first, second in combinations(ordered, 2))
        elif group == "double-exa":
            result.update(
                (race_no, "EXA", first, second)
                for first, second in permutations(ordered, 2)
            )
        else:
            raise ValueError(f"unknown provider group: {group!r}")
    return result


def analyze_2025_gap(
    rows_by_meet_and_endpoint: dict[int, dict[str, list[dict[str, Any]]]],
    entry_rows_by_meet: dict[int, list[dict[str, Any]]],
    result_rows_by_meet: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    meets: dict[str, Any] = {}
    for meet, groups in sorted(rows_by_meet_and_endpoint.items()):
        entry_rows = entry_rows_by_meet.get(meet, [])
        entry_keys = [(_as_int(row["rcNo"]), _as_int(row["chulNo"])) for row in entry_rows]
        entry_counts = Counter(entry_keys)
        duplicate_entry_keys = sum(count - 1 for count in entry_counts.values())
        withdrawn_keys = {
            (_as_int(row["rcNo"]), _as_int(row["chulNo"]))
            for row in result_rows_by_meet.get(meet, [])
            if str(row.get("differ", "")).strip() in PRE_START_WITHDRAWAL_LABELS
        }
        entry_key_set = set(entry_keys)
        withdrawn_not_in_entries = withdrawn_keys - entry_key_set
        entries_by_race: dict[int, set[int]] = {}
        for race_no, horse_no in entry_keys:
            if (race_no, horse_no) in withdrawn_keys:
                continue
            entries_by_race.setdefault(race_no, set()).add(horse_no)
        entry_races_complete = set(entries_by_race) == EXPECTED_RACES

        group_reports: dict[str, Any] = {}
        observed_total = 0
        for name, rows in sorted(groups.items()):
            if name not in GROUP_POOLS:
                raise ValueError(f"unknown provider group: {name!r}")
            races = sorted({_as_int(row["rcNo"]) for row in rows})
            observed_keys = [_odds_key(row) for row in rows]
            observed_counts = Counter(observed_keys)
            observed_key_set = set(observed_counts)
            expected_key_set = _expected_group_keys(name, entries_by_race)
            duplicate_keys = sum(count - 1 for count in observed_counts.values())
            missing_keys = expected_key_set - observed_key_set
            extra_keys = observed_key_set - expected_key_set
            observed_pools = sorted({key[1] for key in observed_key_set})
            group_reports[name] = {
                "row_count": len(rows),
                "race_numbers": races,
                "all_eight_races_present": set(races) == EXPECTED_RACES,
                "pool_codes": observed_pools,
                "expected_pool_codes": sorted(GROUP_POOLS[name]),
                "expected_key_count": len(expected_key_set),
                "unique_key_count": len(observed_key_set),
                "duplicate_key_count": duplicate_keys,
                "missing_key_count": len(missing_keys),
                "extra_key_count": len(extra_keys),
                "exact_key_set_matches": (
                    observed_pools == sorted(GROUP_POOLS[name])
                    and duplicate_keys == 0
                    and not missing_keys
                    and not extra_keys
                ),
            }
            observed_total += len(rows)
        expected_total = EXPECTED_2025_BACKFILL_ROWS[meet]
        expected_total_from_entries = sum(
            report["expected_key_count"] for report in group_reports.values()
        )
        meets[str(meet)] = {
            "entry_row_count": len(entry_rows),
            "entry_race_numbers": sorted(entries_by_race),
            "entry_duplicate_key_count": duplicate_entry_keys,
            "entry_races_complete": entry_races_complete,
            "pre_start_withdrawal_count": len(withdrawn_keys),
            "withdrawal_not_in_entries_count": len(withdrawn_not_in_entries),
            "groups": group_reports,
            "observed_total": observed_total,
            "expected_html_backfill_total": expected_total,
            "expected_total_from_entries": expected_total_from_entries,
            "row_total_matches": observed_total == expected_total,
            "entry_expected_total_matches": expected_total_from_entries == expected_total,
            "all_groups_cover_eight_races": all(
                report["all_eight_races_present"] for report in group_reports.values()
            ),
            "all_groups_match_exact_keys": all(
                report["exact_key_set_matches"] for report in group_reports.values()
            ),
        }
        meets[str(meet)]["resolved"] = (
            meets[str(meet)]["row_total_matches"]
            and meets[str(meet)]["entry_expected_total_matches"]
            and meets[str(meet)]["entry_races_complete"]
            and meets[str(meet)]["entry_duplicate_key_count"] == 0
            and meets[str(meet)]["withdrawal_not_in_entries_count"] == 0
            and meets[str(meet)]["all_groups_cover_eight_races"]
            and meets[str(meet)]["all_groups_match_exact_keys"]
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
    valid_chul_no: dict[int, set[int]] = {}
    for row in entry_rows:
        valid_chul_no.setdefault(_as_int(row["rcNo"]), set()).add(
            _as_int(row["chulNo"])
        )

    out_of_entry_by_race: Counter[int] = Counter()
    phantom_race_by_race: Counter[int] = Counter()
    single_races: set[int] = set()
    for row in single_rows:
        race_no = _as_int(row["rcNo"])
        chul_no = _as_int(row["chulNo"])
        single_races.add(race_no)
        if race_no not in valid_chul_no:
            phantom_race_by_race[race_no] += 1
        elif chul_no not in valid_chul_no[race_no]:
            out_of_entry_by_race[race_no] += 1

    out_of_entry_count = sum(out_of_entry_by_race.values())
    phantom_race_count = sum(phantom_race_by_race.values())
    invalid_count = out_of_entry_count + phantom_race_count

    return {
        "case": "2023-03-17 API28_1 out-of-entry placeholders",
        "entry_races": sorted(valid_chul_no),
        "single_response_races": sorted(single_races),
        "out_of_entry_on_actual_race_count": out_of_entry_count,
        "out_of_entry_by_race": dict(sorted(out_of_entry_by_race.items())),
        "phantom_race_row_count": phantom_race_count,
        "phantom_race_by_race": dict(sorted(phantom_race_by_race.items())),
        "invalid_row_count": invalid_count,
        "resolved": invalid_count == 0,
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


def build_recheck_summary(
    cases: dict[str, dict[str, Any]],
    requests: list[dict[str, Any]],
    *,
    exact_key_value_comparison_passed: bool = False,
) -> dict[str, Any]:
    resolved_count = sum(bool(case["resolved"]) for case in cases.values())
    provider_checks_all_resolved = resolved_count == len(cases)
    canonical_update_allowed = (
        provider_checks_all_resolved and exact_key_value_comparison_passed
    )
    return {
        "schema_version": 2,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "request_count": len(requests),
        "requests": requests,
        "cases": cases,
        "resolved_count": resolved_count,
        "unresolved_count": len(cases) - resolved_count,
        "all_resolved": provider_checks_all_resolved,
        "canonical_update_gate": {
            "provider_checks_all_resolved": provider_checks_all_resolved,
            "exact_key_value_comparison_passed": exact_key_value_comparison_passed,
        },
        "canonical_update_allowed": canonical_update_allowed,
        "note": (
            "Raw responses are evidence only. Canonical updates remain disallowed until a "
            "separate exact natural-key/value comparison passes."
        ),
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
        unit = RequestUnit(endpoint, meet, race_date[:6], pool)
        page = self.client.fetch_page(
            unit,
            1,
            100_000,
            query_overrides={"rc_month": None, "rc_date": race_date, "rc_no": None},
        )
        suffix = pool.lower() if pool else "all"
        extension = ENDPOINTS[endpoint].response_format
        filename = f"{race_date}-meet-{meet}-{endpoint}-{suffix}.{extension}"
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
        entries_2025: dict[int, list[dict[str, Any]]] = {}
        results_2025: dict[int, list[dict[str, Any]]] = {}
        for meet in (2, 3):
            entries_2025[meet] = self.fetch("entries", meet, "20251017").rows
            results_2025[meet] = self.fetch("results", meet, "20251017").rows
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
            "gap_2025_10_17": analyze_2025_gap(rows_2025, entries_2025, results_2025),
            "placeholders_2023_03_17": analyze_2023_placeholders(entries_2023, single_2023),
            "dusu_2019_05_18": analyze_2019_dusu(entries_2019),
        }
        return build_recheck_summary(cases, self.requests)


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
