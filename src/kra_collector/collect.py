from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import KRAClient, KRAResponseError, sha256_bytes
from .registry import EndpointSpec


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def request_id(endpoint_id: str, params_without_key: dict[str, Any]) -> str:
    payload = {"endpoint_id": endpoint_id, "params": params_without_key}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


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
    status: str
    resumed: bool = False


ENFORCED_GATES = [
    "all_pages_total_count_constant",
    "page_row_intersection_empty",
    "deduplicated_union_equals_total_count",
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
        self.collector_commit = os.environ.get("GITHUB_SHA", "local")
        self._completed = self._load_completed_records()

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
            record = ManifestRecord(**data)
            if record.status == "complete":
                completed[
                    self._record_key(
                        record.endpoint_id, record.meet, record.year_month, record.pool
                    )
                ] = record
        return completed

    def _record_files_are_valid(self, record: ManifestRecord) -> bool:
        if record.total_count != record.stored_rows:
            return False
        for page in record.pages:
            raw_path = self.output_dir / page["raw_path"]
            if (
                not raw_path.exists()
                or sha256_bytes(raw_path.read_bytes()) != page["raw_sha256"]
            ):
                return False
        if record.terminal_probe is not None:
            probe_path = self.output_dir / record.terminal_probe["raw_path"]
            if (
                not probe_path.exists()
                or sha256_bytes(probe_path.read_bytes())
                != record.terminal_probe["raw_sha256"]
            ):
                return False
        normalized_path = self.output_dir / record.normalized_path
        if not normalized_path.exists():
            return False
        try:
            normalized_content = gzip.decompress(normalized_path.read_bytes())
        except (OSError, EOFError):
            return False
        return sha256_bytes(normalized_content) == record.normalized_content_sha256

    def _append_manifest(self, record: ManifestRecord) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("ab") as handle:
            handle.write(canonical_json(asdict(record)) + b"\n")

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
                or previous.schema_version != "1"
                or previous.collector_commit != self.collector_commit
            ):
                raise KRAResponseError(
                    "resume identity differs from the current request or collector; "
                    "use a new snapshot_id"
                )
            if self._record_files_are_valid(previous):
                return replace(previous, resumed=True)
        pages: list[PageRecord] = []
        rows: list[dict[str, Any]] = []
        seen_rows: set[str] = set()
        expected_total: int | None = None
        page_no = 1

        while True:
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
            pages.append(
                PageRecord(
                    page_no=page_no,
                    returned_rows=len(envelope.rows),
                    raw_path=raw_relative.as_posix(),
                    raw_sha256=sha256_bytes(content),
                    content_type=content_type,
                    response_format=envelope.response_format,
                )
            )
            for row in envelope.rows:
                row_hash = sha256_bytes(canonical_json(row))
                if row_hash in seen_rows:
                    raise KRAResponseError(
                        f"duplicate row across pages for {spec.endpoint_id} meet={meet} "
                        f"month={year_month} pool={pool} page={page_no}"
                    )
                seen_rows.add(row_hash)
                rows.append(row)

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

        probe_page_no = page_no + 1
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
        if probe_envelope.total_count != expected_total:
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
            schema_version="1",
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
            status="complete",
        )
        self._append_manifest(record)
        self._completed[record_key] = record
        return record
