from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BusinessKeyField:
    name: str
    kind: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class EndpointSpec:
    endpoint_id: str
    service: str
    operation: str
    collection_grain: str
    response_format: str
    success_codes: tuple[str, ...]
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    response_root: str
    pagination: str
    terminal_probe_total_count: str
    pool_param: str
    pools: tuple[str | None, ...]
    business_key_fields: tuple[BusinessKeyField, ...]

    @property
    def path(self) -> str:
        return f"{self.service}/{self.operation}"


def _load_registry() -> dict[str, EndpointSpec]:
    # JSON is valid YAML 1.2, so this remains a YAML-named frozen config while
    # keeping the runtime dependency-free and parser behavior deterministic.
    path = Path(__file__).resolve().parents[2] / "config" / "endpoints.yml"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "2":
        raise RuntimeError("unsupported endpoint registry schema")
    specs: dict[str, EndpointSpec] = {}
    for endpoint_id, item in payload["endpoints"].items():
        spec = EndpointSpec(
            endpoint_id=endpoint_id,
            service=item["service"],
            operation=item["operation"],
            collection_grain=item["collection_grain"],
            response_format=item["response_format"],
            success_codes=tuple(item["success_codes"]),
            required_params=tuple(item["required_params"]),
            optional_params=tuple(item["optional_params"]),
            response_root=item["response_root"],
            pagination=item["pagination"],
            terminal_probe_total_count=item["terminal_probe_total_count"],
            pool_param=item["pool_param"],
            pools=tuple(item["market_codes"]),
            business_key_fields=tuple(
                BusinessKeyField(
                    name=field["name"],
                    kind=field["kind"],
                    aliases=tuple(field["aliases"]),
                )
                for field in item["business_key_fields"]
            ),
        )
        if (
            spec.response_format != "json"
            or spec.terminal_probe_total_count
            not in {"echoed", "zero", "echoed_or_zero"}
            or spec.pool_param
            not in {
                "required",
                "optional",
                "prohibited",
            }
        ):
            raise RuntimeError(f"invalid endpoint registry entry: {endpoint_id}")
        specs[endpoint_id] = spec
    return specs


# docs/API_FINDINGS.md is the evidence of record. API29 is intentionally called
# without pool because the verified response multiplexes EXA/QNL/QPL. API30 is
# called once per TLA/TRI pool.
ENDPOINTS = _load_registry()
