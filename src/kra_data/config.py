from __future__ import annotations

from dataclasses import dataclass


BASE_URL = "https://apis.data.go.kr/B551015"


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    pools: tuple[str | None, ...]
    daily_limit: int = 10_000


ENDPOINTS: dict[str, Endpoint] = {
    "single": Endpoint(
        "single", "API28_1/singlePredictionRateInfo_1", (None,)
    ),
    "double": Endpoint(
        "double", "API29_1/doublePredictionRateInfo_1", ("QNL", "EXA", "QPL")
    ),
    "triple": Endpoint(
        "triple", "API30_1/triplePredictionRateInfo_1", ("TLA", "TRI")
    ),
    "sales": Endpoint(
        "sales", "API179_1/salesAndDividendRate_1", (None,), daily_limit=3_000
    ),
    "entries": Endpoint("entries", "API26_2/entrySheet_2", (None,)),
    "results": Endpoint("results", "API214_1/RaceDetailResult_1", (None,)),
}

DEFAULT_ENDPOINTS = tuple(ENDPOINTS)
MEETS = (1, 2, 3)
SCHEMA_VERSION = 1
