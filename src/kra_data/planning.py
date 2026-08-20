from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable, Iterator

from .config import ENDPOINTS
from .models import RequestUnit


def iter_months(start_year: int, end_year: int) -> Iterator[str]:
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            yield f"{year:04d}{month:02d}"


def iter_dates(month: str) -> Iterator[str]:
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
    units: list[RequestUnit] = []
    endpoint_names = tuple(endpoints)
    for name in endpoint_names:
        if name not in ENDPOINTS:
            raise ValueError(f"unknown endpoint: {name}")
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
