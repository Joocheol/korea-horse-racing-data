from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

from .config import ENDPOINTS
from .ledger import Ledger
from .models import RequestUnit


def iter_months(start_year: int, end_year: int) -> Iterator[str]:
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            yield f"{year:04d}{month:02d}"


def _validate_endpoints(endpoints: Iterable[str]) -> tuple[str, ...]:
    endpoint_names = tuple(endpoints)
    unknown = [name for name in endpoint_names if name not in ENDPOINTS]
    if unknown:
        raise ValueError(f"unknown endpoint: {unknown[0]}")
    return endpoint_names


def iter_dates(month: str) -> Iterator[str]:
    """Legacy calendar expansion retained only for pilot reproducibility tests."""
    if len(month) != 6 or not month.isdigit():
        raise ValueError(f"month must be YYYYMM: {month}")
    year = int(month[:4])
    month_number = int(month[4:])
    for day in range(1, monthrange(year, month_number)[1] + 1):
        yield f"{month}{day:02d}"


def build_units(
    start_year: int,
    end_year: int,
    meets: Iterable[int],
    endpoints: Iterable[str],
) -> list[RequestUnit]:
    """Reproduce the completed 2020-2021 all-calendar-date pilot plan.

    Production code must use ``build_monthly_units`` followed by
    ``discover_result_dates`` and ``build_result_units``. This legacy function
    remains only so the completed pilot's historical request count can be
    reproduced from tests and Git history.
    """
    endpoint_names = _validate_endpoints(endpoints)
    units: list[RequestUnit] = []
    for month in iter_months(start_year, end_year):
        for meet in meets:
            for name in endpoint_names:
                for pool in ENDPOINTS[name].pools:
                    if name == "results":
                        units.extend(
                            RequestUnit(name, meet, month, pool, race_date)
                            for race_date in iter_dates(month)
                        )
                    else:
                        units.append(RequestUnit(name, meet, month, pool))
    return units


def build_monthly_units(
    start_year: int,
    end_year: int,
    meets: Iterable[int],
    endpoints: Iterable[str],
) -> list[RequestUnit]:
    """Build production phase-1 units, excluding date-only API227 requests."""
    endpoint_names = tuple(
        name for name in _validate_endpoints(endpoints) if name != "results"
    )
    units: list[RequestUnit] = []
    for month in iter_months(start_year, end_year):
        for meet in meets:
            for name in endpoint_names:
                units.extend(
                    RequestUnit(name, meet, month, pool)
                    for pool in ENDPOINTS[name].pools
                )
    return units


def _normalize_race_date(value: object) -> str:
    race_date = str(value or "").strip().replace("-", "")
    if len(race_date) != 8 or not race_date.isdigit():
        raise ValueError(f"invalid rcDate in race_record staged data: {value!r}")
    try:
        date.fromisoformat(f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:]}")
    except ValueError as exc:
        raise ValueError(f"invalid rcDate in race_record staged data: {value!r}") from exc
    return race_date


def _expected_race_record_units(
    start_year: int,
    end_year: int,
    meets: Iterable[int],
) -> list[RequestUnit]:
    return build_monthly_units(start_year, end_year, tuple(meets), ("race_record",))


def race_record_coverage_complete(
    output_dir: Path,
    start_year: int,
    end_year: int,
    meets: Iterable[int],
) -> bool:
    """Return True only after every requested API4_3 meet-month is complete."""
    expected = _expected_race_record_units(start_year, end_year, tuple(meets))
    completed = Ledger(output_dir / "ledger.json").completed()
    return all(unit.key in completed for unit in expected)


def discover_result_dates(
    output_dir: Path,
    start_year: int,
    end_year: int,
    meets: Iterable[int],
) -> tuple[tuple[int, str], ...]:
    """Discover actual API227 target dates from complete API4_3 staged data.

    The returned keys are unique ``(meet, YYYYMMDD)`` pairs. API4_3 is already
    collected monthly, so this discovery step consumes no additional API calls.
    """
    meet_values = tuple(meets)
    expected = _expected_race_record_units(start_year, end_year, meet_values)
    completed = Ledger(output_dir / "ledger.json").completed()
    missing = [unit.key for unit in expected if unit.key not in completed]
    if missing:
        raise ValueError(
            "race_record coverage is incomplete; cannot safely plan API227 "
            f"({len(missing)} meet-month units missing)"
        )

    discovered: set[tuple[int, str]] = set()
    for unit in expected:
        staged_path = output_dir / "staged" / unit.staged_relative_path
        if not staged_path.exists():
            raise FileNotFoundError(f"completed race_record staged file is missing: {staged_path}")
        with staged_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid JSONL in {staged_path} at line {line_number}"
                    ) from exc
                if not isinstance(row, dict):
                    raise ValueError(
                        f"non-object JSONL row in {staged_path} at line {line_number}"
                    )
                race_date = _normalize_race_date(row.get("rcDate"))
                if race_date[:6] != unit.month:
                    raise ValueError(
                        f"rcDate {race_date} does not belong to staged month {unit.month}"
                    )
                discovered.add((unit.meet, race_date))
    return tuple(sorted(discovered, key=lambda item: (item[1], item[0])))


def build_result_units(
    start_year: int,
    end_year: int,
    meets: Iterable[int],
    result_dates: Iterable[tuple[int, str]],
) -> list[RequestUnit]:
    """Build API227 units only for discovered actual meet-date pairs."""
    meet_values = set(meets)
    normalized: set[tuple[int, str]] = set()
    for meet, raw_date in result_dates:
        race_date = _normalize_race_date(raw_date)
        year = int(race_date[:4])
        if meet not in meet_values or not (start_year <= year <= end_year):
            continue
        normalized.add((int(meet), race_date))

    units: list[RequestUnit] = []
    for meet, race_date in sorted(normalized, key=lambda item: (item[1], item[0])):
        units.extend(
            RequestUnit("results", meet, race_date[:6], pool, race_date)
            for pool in ENDPOINTS["results"].pools
        )
    return units
