from __future__ import annotations

from dataclasses import dataclass


BASE_URL = "https://apis.data.go.kr/B551015"


@dataclass(frozen=True)
class Endpoint:
    name: str
    service: str
    path: str
    pools: tuple[str | None, ...]
    response_format: str = "json"
    daily_limit: int = 3_000

    def __post_init__(self) -> None:
        if self.response_format not in {"json", "xml"}:
            raise ValueError(f"unsupported response format: {self.response_format}")


ENDPOINTS: dict[str, Endpoint] = {
    "single": Endpoint(
        "single", "API28_1", "API28_1/singlePredictionRateInfo_1", (None,)
    ),
    "double": Endpoint(
        "double", "API29_1", "API29_1/doublePredictionRateInfo_1", ("QNL", "EXA", "QPL")
    ),
    "triple": Endpoint(
        "triple", "API30_1", "API30_1/triplePredictionRateInfo_1", ("TLA", "TRI")
    ),
    "sales": Endpoint(
        "sales", "API179_1", "API179_1/salesAndDividendRate_1", (None,)
    ),
    "entries": Endpoint(
        "entries", "API26_2", "API26_2/entrySheet_2", (None,)
    ),
    "results": Endpoint(
        "results", "API227", "racedetailresult/getracedetailresult", (None,), response_format="xml"
    ),
    "race_record": Endpoint(
        "race_record", "API4_3", "API4_3/raceResult_3", (None,), response_format="xml"
    ),
    "quinella_crosscheck": Endpoint(
        "quinella_crosscheck", "API5", "API5/quinellaOddsInfo", (None,)
    ),
}

DEFAULT_ENDPOINTS = tuple(ENDPOINTS)
MEETS = (1, 2, 3)
SCHEMA_VERSION = 3
