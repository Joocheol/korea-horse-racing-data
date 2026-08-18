from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .client import KRAClient, KRAResponseError, sha256_bytes
from .registry import EndpointSpec


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
    with temporary.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gz:
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
    collected_at_utc: str
    collector_commit: str
    status: str


class Collector:
    def __init__(
        self,
        client: KRAClient,
        output_dir: Path,
        *,
        page_size: int = 100_000,
        snapshot_id: str | None = None,
    ) -> None:
        self.client = client
        self.output_dir = output_dir
        self.page_size = page_size
        self.snapshot_id = snapshot_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.manifest_path = output_dir / "manifests" / f"manifest-{self.snapshot_id}.jsonl"
        self.collector_commit = os.environ.get("GITHUB_SHA", "local")

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
        base_params: dict[str, Any] = {
            "meet": meet,
            "rc_month": year_month.replace("-", ""),
            "numOfRows": self.page_size,
            "_type": "json",
        }
        if pool is not None:
            base_params["pool"] = pool

        logical_id = request_id(spec.endpoint_id, base_params)
        pages: list[PageRecord] = []
        rows: list[dict[str, Any]] = []
        expected_total: int | None = None
        page_no = 1

        while True:
            page_params = {**base_params, "pageNo": page_no}
            content, content_type, envelope = self.client.get(spec.path, page_params)
            if expected_total is None:
                expected_total = envelope.total_count
            elif envelope.total_count != expected_total:
                raise KRAResponseError(
                    f"totalCount changed for {spec.endpoint_id} meet={meet} month={year_month} "
                    f"pool={pool}: {expected_total} -> {envelope.total_count}"
                )

            pool_part = pool or "ALL"
            raw_relative = Path("raw") / spec.endpoint_id / str(meet) / year_month / pool_part / f"page-{page_no:05d}.{envelope.response_format}"
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
            rows.extend(envelope.rows)

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

        normalized_relative = Path("normalized") / spec.endpoint_id / str(meet) / year_month / f"{pool or 'ALL'}.jsonl.gz"
        normalized_hash = write_deterministic_jsonl_gz(self.output_dir / normalized_relative, rows)
        record = ManifestRecord(
            schema_version="1",
            snapshot_id=self.snapshot_id,
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
            collected_at_utc=datetime.now(UTC).isoformat(),
            collector_commit=self.collector_commit,
            status="complete",
        )
        self._append_manifest(record)
        return record

