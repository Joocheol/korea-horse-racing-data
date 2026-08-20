from __future__ import annotations

from collections.abc import Iterable, Iterator

from .config import ENDPOINTS
from .models import RequestUnit


def iter_months(start_year: int, end_year: int) -> Iterator[str]:
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            yield f"{year:04d}{month:02d}"


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
                    units.append(RequestUnit(name, meet, month, pool))
    return units
