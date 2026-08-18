from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import KRAClient, KRAResponseError, parse_envelope, sha256_bytes
from .registry import EndpointSpec

COLLECTOR_SCHEMA_VERSION = "2"
MAX_CALLS_PER_LOGICAL_REQUEST = 3


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def request_id(endpoint_id: str, params_without_key: dict[str, Any]) -> str:
    payload = {"endpoint_id": endpoint_id, "params": params_without_key}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _normalize_key_value(value: Any, kind: str) -> str:
    text = str(value).strip()
    if kind == "integer":
        try:
            return str(int(text))
        except ValueError as exc:
            raise KRAResponseError(
                f"business key integer is invalid: {text!r}"
            ) from exc
    if kind == "date":
        digits = text.replace("-", "")
        if len(digits) != 8 or not digits.isdigit():
            raise KRAResponseError(f"business key date is invalid: {text!r}")
        return digits
    if kind == "text":
        if not text:
            raise KRAResponseError("business key text is empty")
        return text.upper()
    raise KRAResponseError(f"unknown business key normalization: {kind}")


def business_key_observation(
    spec: EndpointSpec, row: dict[str, Any]
) -> tuple[str, dict[str, list[str]]]:
    key: dict[str, str] = {}
    observed_aliases: dict[str, list[str]] = {}
    for field in spec.business_key_fields:
        present = [alias for alias in field.aliases if alias in row]
        if not present:
            raise KRAResponseError(
                f"business key field {field.name} missing for {spec.endpoint_id}"
            )
        values = {_normalize_key_value(row[alias], field.kind) for alias in present}
        if len(values) != 1:
            raise KRAResponseError(
                f"business key aliases conflict for {spec.endpoint_id}:{field.name}"
            )
        key[field.name] = values.pop()
        observed_aliases[field.name] = present
    return sha256_bytes(canonical_json(key)), observed_aliases


def business_key_hash(spec: EndpointSpec, row: dict[str, Any]) -> str:
    return business_key_observation(spec, row)[0]


def _normalize_pool(value: Any) -> str:
    text = str(value).strip().upper()
    aliases = {
        "삼복": "TLA",
        "삼복승": "TLA",
        "삼쌍": "TRI",
        "삼쌍승": "TRI",
        "복식": "QNL",
        "복승": "QNL",
        "쌍식": "EXA",
        "쌍승": "EXA",
        "복연": "QPL",
        "복연승": "QPL",
    }
    return aliases.get(text, text)


def assert_row_matches_requested_partition(
    spec: EndpointSpec, row: dict[str, Any], params: dict[str, Any]
) -> None:
    race_date_field = next(
        field for field in spec.business_key_fields if field.name == "race_date"
    )
    present_dates = [alias for alias in race_date_field.aliases if alias in row]
    if not present_dates:
        raise KRAResponseError(
            f"row partition race date is missing for {spec.endpoint_id}"
        )
    dates = {
        _normalize_key_value(row[alias], race_date_field.kind)
        for alias in present_dates
    }
    requested_month = str(params.get("rc_month", ""))
    if (
        len(dates) != 1
        or not requested_month
        or not dates.pop().startswith(requested_month)
    ):
        raise KRAResponseError(
            f"row race date differs from requested month for {spec.endpoint_id}"
        )
    requested_meet = int(params["meet"])
    present_meets = [alias for alias in ("meet", "meetCode") if alias in row]
    if not present_meets:
        raise KRAResponseError(f"row meet is missing for {spec.endpoint_id}")
    try:
        meets = {int(str(row[alias]).strip()) for alias in present_meets}
    except ValueError as exc:
        raise KRAResponseError(f"row meet is invalid for {spec.endpoint_id}") from exc
    if meets != {requested_meet}:
        raise KRAResponseError(
            f"row meet differs from requested meet for {spec.endpoint_id}"
        )
    if "pool" in params:
        market_field = next(
            field for field in spec.business_key_fields if field.name == "market"
        )
        present_pools = [alias for alias in market_field.aliases if alias in row]
        if not present_pools:
            raise KRAResponseError(
                f"row pool is missing for requested pool on {spec.endpoint_id}"
            )
        row_pools = {_normalize_pool(row[alias]) for alias in present_pools}
        if row_pools != {_normalize_pool(params["pool"])}:
            raise KRAResponseError(
                f"row pool differs from requested pool for {spec.endpoint_id}"
            )


def terminal_probe_total_count_is_valid(
    spec: EndpointSpec, observed: int, expected: int
) -> bool:
    policy = spec.terminal_probe_total_count
    if policy == "echoed":
        return observed == expected
    if policy == "zero":
        return observed == 0
    return observed in {0, expected}


def collector_contract_hash(spec: EndpointSpec) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "collector_schema_version": COLLECTOR_SCHEMA_VERSION,
                "endpoint_spec": asdict(spec),
                "enforced_gates": ENFORCED_GATES,
            }
        )
    )


def required_calls_for_total(total_count: int, page_size: int) -> int:
    if total_count < 0 or page_size <= 0:
        raise KRAResponseError("invalid pagination geometry")
    return max(1, math.ceil(total_count / page_size)) + 1


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def write_deterministic_jsonl_gz(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    digest = hashlib.sha256()
    with (
        temporary.open("wb") as raw_handle,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gz,
    ):
        for row in rows:
            line = canonical_json(row) + b"\n"
            digest.update(line)
            gz.write(line)
    os.replace(temporary, path)
    return digest.hexdigest()


@dataclass
class PageRecord:
    page_no: int
    returned_rows: int
    raw_path: str
    raw_sha256: str
    content_type: str
    response_format: str


@dataclass
class PageLedgerEntry:
    schema_version: str
    snapshot_id: str
    endpoint_id: str
    request_id: str
    canonical_params_without_service_key: dict[str, Any]
    collector_commit: str
    collector_contract_sha256: str
    total_count: int
    kind: str
    page: dict[str, Any]
    recorded_at_utc: str


@dataclass
class ManifestRecord:
    schema_version: str
    snapshot_id: str
    key_id: str
    endpoint_id: str
    service: str
    operation: str
    meet: int
    year_month: str
    pool: str | None
    canonical_params_without_service_key: dict[str, Any]
    request_id: str
    total_count: int
    stored_rows: int
    page_count: int
    normalized_path: str
    normalized_content_sha256: str
    pages: list[dict[str, Any]]
    terminal_probe: dict[str, Any] | None
    verification_gates: dict[str, list[str]]
    collected_at_utc: str
    collector_commit: str
    collector_contract_sha256: str
    status: str
    resumed: bool = False


ENFORCED_GATES = [
    "all_pages_total_count_constant",
    "rows_match_requested_partition",
    "business_key_unique_across_pages",
    "business_key_union_equals_total_count",
    "terminal_page_empty",
    "raw_sha256_verified",
    "normalized_content_sha256_verified",
]

UNRUN_PILOT_GATES = [
    "api26_independent_starter_count",
    "api5_api29_quinella_cell_agreement",
    "overround_vs_verified_takeout",
    "turnover_ticket_interval_check",
    "turnover_and_finish_order_race_classification",
    "seven_pool_completeness",
    "quarantine_table_preservation",
]


def completed_record_files_are_valid(
    root: Path, record: ManifestRecord, spec: EndpointSpec
) -> bool:
    """Return true only when a completed record satisfies the verifier's file gates."""
    try:
        total_count = int(record.total_count)
        if (
            record.schema_version != COLLECTOR_SCHEMA_VERSION
            or record.collector_contract_sha256 != collector_contract_hash(spec)
            or int(record.stored_rows) != total_count
        ):
            return False
        page_size = int(record.canonical_params_without_service_key["numOfRows"])
        if page_size <= 0:
            return False
        expected_page_count = max(1, math.ceil(total_count / page_size))
        if record.page_count != expected_page_count:
            return False
        page_numbers = [int(page["page_no"]) for page in record.pages]
        if page_numbers != list(range(1, expected_page_count + 1)):
            return False

        raw_row_hashes: set[str] = set()
        business_keys: set[str] = set()
        for page in record.pages:
            page_no = int(page["page_no"])
            raw_path = root / page["raw_path"]
            if not raw_path.exists():
                return False
            content = raw_path.read_bytes()
            if sha256_bytes(content) != page["raw_sha256"]:
                return False
            envelope = parse_envelope(
                content, page.get("content_type", ""), spec.response_format
            )
            expected_rows = (
                page_size
                if page_no < expected_page_count
                else max(0, total_count - page_size * (expected_page_count - 1))
            )
            if (
                envelope.total_count != total_count
                or len(envelope.rows) != expected_rows
                or int(page["returned_rows"]) != expected_rows
            ):
                return False
            for row in envelope.rows:
                assert_row_matches_requested_partition(
                    spec, row, record.canonical_params_without_service_key
                )
                row_hash = sha256_bytes(canonical_json(row))
                row_key = business_key_hash(spec, row)
                if row_key in business_keys:
                    return False
                business_keys.add(row_key)
                raw_row_hashes.add(row_hash)
        if len(business_keys) != total_count:
            return False

        probe = record.terminal_probe
        if probe is None or int(probe["page_no"]) != expected_page_count + 1:
            return False
        probe_path = root / probe["raw_path"]
        if not probe_path.exists():
            return False
        probe_content = probe_path.read_bytes()
        if sha256_bytes(probe_content) != probe["raw_sha256"]:
            return False
        probe_envelope = parse_envelope(
            probe_content, probe.get("content_type", ""), spec.response_format
        )
        if probe_envelope.rows or not terminal_probe_total_count_is_valid(
            spec, probe_envelope.total_count, total_count
        ):
            return False

        normalized_path = root / record.normalized_path
        if not normalized_path.exists():
            return False
        normalized_content = gzip.decompress(normalized_path.read_bytes())
        if sha256_bytes(normalized_content) != record.normalized_content_sha256:
            return False
        normalized_rows = [
            json.loads(line)
            for line in normalized_content.decode("utf-8").splitlines()
            if line
        ]
        if len(normalized_rows) != total_count:
            return False
        normalized_hashes = {
            sha256_bytes(canonical_json(row)) for row in normalized_rows
        }
        return normalized_hashes == raw_row_hashes
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        EOFError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False
    except KRAResponseError:
        return False


class Collector:
    def __init__(
        self,
        client: KRAClient,
        output_dir: Path,
        *,
        page_size: int = 100_000,
        snapshot_id: str | None = None,
        key_id: str = "data-go-kr-service-key",
    ) -> None:
        self.client = client
        self.output_dir = output_dir
        self.page_size = page_size
        self.snapshot_id = snapshot_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.key_id = key_id
        self.manifest_path = (
            output_dir / "manifests" / f"manifest-{self.snapshot_id}.jsonl"
        )
        self.page_ledger_path = (
            output_dir / "ledgers" / f"pages-{self.snapshot_id}.jsonl"
        )
        self.request_state_path = (
            output_dir / "ledgers" / f"requests-{self.snapshot_id}.jsonl"
        )
        self.collector_commit = os.environ.get("GITHUB_SHA", "local")
        self._completed = self._load_completed_records()

    def record_request_state(
        self,
        spec: EndpointSpec,
        meet: int,
        year_month: str,
        pool: str | None,
        state: str,
        error_type: str | None = None,
    ) -> None:
        if state not in {"success", "retryable", "unresolved_transport"}:
            raise ValueError(f"invalid request state: {state}")
        params: dict[str, Any] = {
            "meet": meet,
            "rc_month": year_month.replace("-", ""),
            "numOfRows": self.page_size,
            "_type": spec.response_format,
        }
        if pool is not None:
            params["pool"] = pool
        entry = {
            "schema_version": COLLECTOR_SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "endpoint_id": spec.endpoint_id,
            "meet": meet,
            "year_month": year_month,
            "pool": pool,
            "request_id": request_id(spec.endpoint_id, params),
            "canonical_params_without_service_key": params,
            "state": state,
            "error_type": error_type,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
        self.request_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.request_state_path.open("ab") as handle:
            handle.write(canonical_json(entry) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _record_key(
        endpoint_id: str, meet: int, year_month: str, pool: str | None
    ) -> tuple[str, int, str, str | None]:
        return endpoint_id, meet, year_month, pool

    def _load_completed_records(
        self,
    ) -> dict[tuple[str, int, str, str | None], ManifestRecord]:
        completed: dict[tuple[str, int, str, str | None], ManifestRecord] = {}
        if not self.manifest_path.exists():
            return completed
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            data.setdefault("key_id", "unknown")
            data.setdefault("terminal_probe", None)
            data.setdefault("verification_gates", {"enforced": [], "unrun": []})
            data.setdefault("resumed", False)
            data.setdefault("collector_contract_sha256", "missing")
            record = ManifestRecord(**data)
            if record.status == "complete":
                completed[
                    self._record_key(
                        record.endpoint_id, record.meet, record.year_month, record.pool
                    )
                ] = record
        return completed

    def _append_manifest(self, record: ManifestRecord) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("ab") as handle:
            handle.write(canonical_json(asdict(record)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _append_page_ledger(
        self,
        *,
        spec: EndpointSpec,
        logical_id: str,
        base_params: dict[str, Any],
        expected_total: int,
        kind: str,
        page: PageRecord,
    ) -> None:
        entry = PageLedgerEntry(
            schema_version=COLLECTOR_SCHEMA_VERSION,
            snapshot_id=self.snapshot_id,
            endpoint_id=spec.endpoint_id,
            request_id=logical_id,
            canonical_params_without_service_key=base_params,
            collector_commit=self.collector_commit,
            collector_contract_sha256=collector_contract_hash(spec),
            total_count=expected_total,
            kind=kind,
            page=asdict(page),
            recorded_at_utc=datetime.now(UTC).isoformat(),
        )
        self.page_ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.page_ledger_path.open("ab") as handle:
            handle.write(canonical_json(asdict(entry)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _restore_partial_pages(
        self,
        spec: EndpointSpec,
        logical_id: str,
        base_params: dict[str, Any],
    ) -> tuple[
        list[PageRecord],
        list[dict[str, Any]],
        set[str],
        set[str],
        int | None,
        PageRecord | None,
    ]:
        if not self.page_ledger_path.exists():
            return [], [], set(), set(), None, None
        data_entries: dict[int, PageLedgerEntry] = {}
        probe_entries: dict[int, PageLedgerEntry] = {}
        for line in self.page_ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = PageLedgerEntry(**json.loads(line))
            if entry.request_id != logical_id:
                continue
            if (
                entry.schema_version != COLLECTOR_SCHEMA_VERSION
                or entry.snapshot_id != self.snapshot_id
                or entry.endpoint_id != spec.endpoint_id
                or entry.canonical_params_without_service_key != base_params
                or entry.collector_contract_sha256 != collector_contract_hash(spec)
            ):
                raise KRAResponseError(
                    "partial page ledger identity differs from the current request; "
                    "use a new snapshot_id"
                )
            page_no = int(entry.page["page_no"])
            target = data_entries if entry.kind == "data" else probe_entries
            target[page_no] = entry

        if not data_entries:
            return [], [], set(), set(), None, None
        page_numbers = sorted(data_entries)
        if page_numbers != list(range(1, max(page_numbers) + 1)):
            raise KRAResponseError("partial page ledger is not contiguous")

        pages: list[PageRecord] = []
        rows: list[dict[str, Any]] = []
        seen_rows: set[str] = set()
        seen_business_keys: set[str] = set()
        expected_total: int | None = None
        for page_no in page_numbers:
            entry = data_entries[page_no]
            page = PageRecord(**entry.page)
            raw_path = self.output_dir / page.raw_path
            if not raw_path.exists():
                raise KRAResponseError(f"partial raw page is missing: {page_no}")
            content = raw_path.read_bytes()
            if sha256_bytes(content) != page.raw_sha256:
                raise KRAResponseError(f"partial raw page hash differs: {page_no}")
            envelope = parse_envelope(content, page.content_type, spec.response_format)
            if envelope.result_code not in spec.success_codes:
                raise KRAResponseError("partial page result code violates registry")
            if expected_total is None:
                expected_total = entry.total_count
            if (
                entry.total_count != expected_total
                or envelope.total_count != expected_total
                or len(envelope.rows) != page.returned_rows
            ):
                raise KRAResponseError("partial page count metadata differs")
            for row in envelope.rows:
                assert_row_matches_requested_partition(spec, row, base_params)
                row_hash = sha256_bytes(canonical_json(row))
                row_key = business_key_hash(spec, row)
                if row_key in seen_business_keys:
                    raise KRAResponseError(
                        "partial pages contain a duplicate business key"
                    )
                seen_business_keys.add(row_key)
                seen_rows.add(row_hash)
                rows.append(row)
            pages.append(page)

        if expected_total is None or len(rows) > expected_total:
            raise KRAResponseError("partial page ledger exceeds totalCount")
        if len(rows) < expected_total and pages[-1].returned_rows == 0:
            raise KRAResponseError("partial page ledger ends empty before totalCount")

        terminal_probe: PageRecord | None = None
        expected_probe_page = len(pages) + 1
        if expected_probe_page in probe_entries:
            entry = probe_entries[expected_probe_page]
            page = PageRecord(**entry.page)
            probe_path = self.output_dir / page.raw_path
            if not probe_path.exists():
                raise KRAResponseError("partial terminal probe is missing")
            content = probe_path.read_bytes()
            if sha256_bytes(content) != page.raw_sha256:
                raise KRAResponseError("partial terminal probe hash differs")
            envelope = parse_envelope(content, page.content_type, spec.response_format)
            if envelope.rows or not terminal_probe_total_count_is_valid(
                spec, envelope.total_count, expected_total
            ):
                raise KRAResponseError("partial terminal probe is not empty")
            if len(rows) != expected_total:
                raise KRAResponseError(
                    "partial terminal probe precedes complete data pages"
                )
            terminal_probe = page
        return (
            pages,
            rows,
            seen_rows,
            seen_business_keys,
            expected_total,
            terminal_probe,
        )

    def collect_month(
        self,
        spec: EndpointSpec,
        meet: int,
        year_month: str,
        pool: str | None,
    ) -> ManifestRecord:
        if spec.pool_param == "required" and pool is None:
            raise KRAResponseError(f"pool is required for {spec.endpoint_id}")
        if spec.pool_param == "prohibited" and pool is not None:
            raise KRAResponseError(f"pool is prohibited for {spec.endpoint_id}")
        base_params: dict[str, Any] = {
            "meet": meet,
            "rc_month": year_month.replace("-", ""),
            "numOfRows": self.page_size,
            "_type": "json",
        }
        if pool is not None:
            base_params["pool"] = pool

        logical_id = request_id(spec.endpoint_id, base_params)
        record_key = self._record_key(spec.endpoint_id, meet, year_month, pool)
        previous = self._completed.get(record_key)
        if previous is not None:
            if (
                previous.request_id != logical_id
                or previous.schema_version != COLLECTOR_SCHEMA_VERSION
                or previous.collector_contract_sha256 != collector_contract_hash(spec)
            ):
                raise KRAResponseError(
                    "resume identity differs from the current request or collector; "
                    "use a new snapshot_id"
                )
            if completed_record_files_are_valid(self.output_dir, previous, spec):
                return replace(previous, resumed=True)
        (
            pages,
            rows,
            seen_rows,
            seen_business_keys,
            expected_total,
            terminal_probe,
        ) = self._restore_partial_pages(spec, logical_id, base_params)
        resumed_partial = bool(pages or terminal_probe)
        page_no = len(pages) + 1

        while expected_total is None or len(rows) < expected_total:
            page_params = {**base_params, "pageNo": page_no}
            if not set(spec.required_params) <= set(page_params):
                raise KRAResponseError(
                    f"required params missing for {spec.endpoint_id}"
                )
            content, content_type, envelope = self.client.get(spec.path, page_params)
            if (
                envelope.response_format != spec.response_format
                or envelope.result_code not in spec.success_codes
            ):
                raise KRAResponseError(
                    f"response violates endpoint registry for {spec.endpoint_id}"
                )
            if expected_total is None:
                expected_total = envelope.total_count
                required_calls = required_calls_for_total(
                    expected_total, self.page_size
                )
                if required_calls > MAX_CALLS_PER_LOGICAL_REQUEST:
                    raise KRAResponseError(
                        "logical request exceeds the approved per-request call budget: "
                        f"{required_calls}>{MAX_CALLS_PER_LOGICAL_REQUEST}"
                    )
                if (
                    0 < len(envelope.rows) < expected_total
                    and len(envelope.rows) < self.page_size
                ):
                    raise KRAResponseError(
                        "observed server page cap differs from requested numOfRows "
                        f"for {spec.endpoint_id}; rerun preflight before collection"
                    )
            elif envelope.total_count != expected_total:
                raise KRAResponseError(
                    f"totalCount changed for {spec.endpoint_id} meet={meet} month={year_month} "
                    f"pool={pool}: {expected_total} -> {envelope.total_count}"
                )

            pool_part = pool or "ALL"
            raw_relative = (
                Path("raw")
                / spec.endpoint_id
                / str(meet)
                / year_month
                / pool_part
                / f"page-{page_no:05d}.{envelope.response_format}"
            )
            write_atomic(self.output_dir / raw_relative, content)
            page_record = PageRecord(
                page_no=page_no,
                returned_rows=len(envelope.rows),
                raw_path=raw_relative.as_posix(),
                raw_sha256=sha256_bytes(content),
                content_type=content_type,
                response_format=envelope.response_format,
            )
            for row in envelope.rows:
                assert_row_matches_requested_partition(spec, row, base_params)
                row_hash = sha256_bytes(canonical_json(row))
                row_key = business_key_hash(spec, row)
                if row_key in seen_business_keys:
                    raise KRAResponseError(
                        f"duplicate business key across pages for {spec.endpoint_id} meet={meet} "
                        f"month={year_month} pool={pool} page={page_no}"
                    )
                seen_business_keys.add(row_key)
                seen_rows.add(row_hash)
                rows.append(row)

            pages.append(page_record)
            self._append_page_ledger(
                spec=spec,
                logical_id=logical_id,
                base_params=base_params,
                expected_total=expected_total,
                kind="data",
                page=page_record,
            )

            if len(rows) >= expected_total:
                break
            if not envelope.rows:
                raise KRAResponseError(
                    f"empty page before totalCount for {spec.endpoint_id}: {len(rows)}/{expected_total}"
                )
            page_no += 1

        if len(rows) != expected_total:
            raise KRAResponseError(
                f"stored row count differs from totalCount for {spec.endpoint_id}: "
                f"{len(rows)} != {expected_total}"
            )

        if terminal_probe is None:
            probe_page_no = len(pages) + 1
            probe_params = {**base_params, "pageNo": probe_page_no}
            probe_content, probe_content_type, probe_envelope = self.client.get(
                spec.path, probe_params
            )
            if (
                probe_envelope.response_format != spec.response_format
                or probe_envelope.result_code not in spec.success_codes
            ):
                raise KRAResponseError(
                    f"terminal response violates endpoint registry for {spec.endpoint_id}"
                )
            if not terminal_probe_total_count_is_valid(
                spec, probe_envelope.total_count, expected_total
            ):
                raise KRAResponseError(
                    f"terminal probe totalCount changed for {spec.endpoint_id}: "
                    f"{expected_total} -> {probe_envelope.total_count}"
                )
            if probe_envelope.rows:
                raise KRAResponseError(
                    f"terminal page is not empty for {spec.endpoint_id} "
                    f"meet={meet} month={year_month} pool={pool}"
                )
            pool_part = pool or "ALL"
            probe_relative = (
                Path("raw")
                / spec.endpoint_id
                / str(meet)
                / year_month
                / pool_part
                / f"probe-page-{probe_page_no:05d}.{probe_envelope.response_format}"
            )
            write_atomic(self.output_dir / probe_relative, probe_content)
            terminal_probe = PageRecord(
                page_no=probe_page_no,
                returned_rows=0,
                raw_path=probe_relative.as_posix(),
                raw_sha256=sha256_bytes(probe_content),
                content_type=probe_content_type,
                response_format=probe_envelope.response_format,
            )
            self._append_page_ledger(
                spec=spec,
                logical_id=logical_id,
                base_params=base_params,
                expected_total=expected_total,
                kind="probe",
                page=terminal_probe,
            )

        normalized_relative = (
            Path("normalized")
            / spec.endpoint_id
            / str(meet)
            / year_month
            / f"{pool or 'ALL'}.jsonl.gz"
        )
        normalized_hash = write_deterministic_jsonl_gz(
            self.output_dir / normalized_relative, rows
        )
        record = ManifestRecord(
            schema_version=COLLECTOR_SCHEMA_VERSION,
            snapshot_id=self.snapshot_id,
            key_id=self.key_id,
            endpoint_id=spec.endpoint_id,
            service=spec.service,
            operation=spec.operation,
            meet=meet,
            year_month=year_month,
            pool=pool,
            canonical_params_without_service_key=base_params,
            request_id=logical_id,
            total_count=expected_total,
            stored_rows=len(rows),
            page_count=len(pages),
            normalized_path=normalized_relative.as_posix(),
            normalized_content_sha256=normalized_hash,
            pages=[asdict(page) for page in pages],
            terminal_probe=asdict(terminal_probe),
            verification_gates={
                "enforced": ENFORCED_GATES,
                "unrun": UNRUN_PILOT_GATES,
            },
            collected_at_utc=datetime.now(UTC).isoformat(),
            collector_commit=self.collector_commit,
            collector_contract_sha256=collector_contract_hash(spec),
            status="complete",
            resumed=resumed_partial,
        )
        self._append_manifest(record)
        self._completed[record_key] = record
        return record
