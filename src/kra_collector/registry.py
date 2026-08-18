from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointSpec:
    endpoint_id: str
    service: str
    operation: str
    collection_grain: str
    pools: tuple[str | None, ...] = (None,)

    @property
    def path(self) -> str:
        return f"{self.service}/{self.operation}"


# docs/API_FINDINGS.md is the evidence of record. API29 is intentionally called
# without pool because the verified response multiplexes EXA/QNL/QPL. API30 is
# called once per TLA/TRI pool.
ENDPOINTS: dict[str, EndpointSpec] = {
    "api28": EndpointSpec(
        endpoint_id="api28",
        service="API28_1",
        operation="singlePredictionRateInfo_1",
        collection_grain="month",
    ),
    "api29": EndpointSpec(
        endpoint_id="api29",
        service="API29_1",
        operation="doublePredictionRateInfo_1",
        collection_grain="month",
    ),
    "api30": EndpointSpec(
        endpoint_id="api30",
        service="API30_1",
        operation="triplePredictionRateInfo_1",
        collection_grain="month",
        pools=("TLA", "TRI"),
    ),
    "api179": EndpointSpec(
        endpoint_id="api179",
        service="API179_1",
        operation="salesAndDividendRate_1",
        collection_grain="month",
    ),
}
