from __future__ import annotations

import os
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .client import KRAClient, Page
from .config import ENDPOINTS, SCHEMA_VERSION
from .errors import TransientAPIError, ValidationError
from .ledger import Ledger
from .models import RequestUnit
from .storage import atomic_write_bytes, canonical_json, write_immutable_bytes
from .validation import ValidationSummary, unique_rows, validate_pages


def _write_raw_pages(
    output_dir: Path,
    unit: RequestUnit,
    pages: list[Page],
    prefix: str,
    *,
    preserve_conflicts: bool = False,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    expected_format = ENDPOINTS[unit.endpoint].response_format
    for page in pages:
        if not page.raw_body:
            raise ValueError("raw response bytes are required")
        if page.response_format != expected_format:
            raise ValueError(f"unexpected response format: {page.response_format}")
        relative = f"{prefix}/{unit.raw_page_relative_path(page.page_no)}"
        conflict_with: str | None = None
        try:
            digest = write_immutable_bytes(output_dir / relative, page.raw_body)
        except FileExistsError:
            if not preserve_conflicts:
                raise
            conflict_with = relative
            run_id = os.environ.get("GITHUB_RUN_ID", "local")
            attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
            relative = (
                f"raw-revisions/run-{run_id}-attempt-{attempt}/"
                f"{unit.raw_page_relative_path(page.page_no)}"
            )
            digest = write_immutable_bytes(output_dir / relative, page.raw_body)
        record: dict[str, object] = {
            "page_no": page.page_no,
            "path": relative,
            "sha256": digest,
            "format": page.response_format,
            "bytes": len(page.raw_body),
        }
        if conflict_with is not None:
            record["conflict_with"] = conflict_with
        records.append(record)
    return records


def collect_one(
    client: KRAClient,
    unit: RequestUnit,
    output_dir: Path,
    ledger: Ledger,
    *,
    collector_sha: str,
    num_rows: int | None = None,
) -> ValidationSummary:
    endpoint = ENDPOINTS[unit.endpoint]
    num_rows = endpoint.num_rows if num_rows is None else num_rows
    ledger.update(
        unit.key,
        "running",
        request={
            "endpoint": unit.endpoint,
            "service": endpoint.service,
            "format": endpoint.response_format,
            "meet": unit.meet,
            "month": unit.month,
            "race_date": unit.race_date,
            "pool": unit.pool,
        },
        collector_sha=collector_sha,
        schema_version=SCHEMA_VERSION,
    )
    captured_pages: list[Page] = []
    try:
        pages = client.collect_unit(unit, num_rows=num_rows, on_page=captured_pages.append)
        ledger.update(unit.key, "validating", page_count=len(pages))
        raw_files = _write_raw_pages(
            output_dir, unit, pages, "raw", preserve_conflicts=True
        )
        allow_exact_duplicates = unit.endpoint == "results"
        summary = validate_pages(
            pages, allow_exact_duplicates=allow_exact_duplicates
        )
        staged_relative = f"staged/{unit.staged_relative_path}"
        rows = unique_rows(pages) if allow_exact_duplicates else [
            row for page in pages for row in page.rows
        ]
        staged_bytes = b"".join(canonical_json(row) + b"\n" for row in rows)
        atomic_write_bytes(output_dir / staged_relative, staged_bytes)
        ledger.update(
            unit.key,
            "complete",
            raw_files=raw_files,
            staged_path=staged_relative,
            **asdict(summary),
        )
        return summary
    except Exception as exc:
        partial_raw_paths: list[dict[str, object]] = []
        if captured_pages:
            run_id = os.environ.get("GITHUB_RUN_ID", "local")
            attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
            prefix = f"failures/run-{run_id}-attempt-{attempt}"
            partial_raw_paths = _write_raw_pages(output_dir, unit, captured_pages, prefix)
        ledger.update(
            unit.key,
            "failed",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            partial_raw_paths=partial_raw_paths,
            partial_page_count=len(captured_pages),
        )
        raise


def collect_units(
    client: KRAClient,
    units: Iterable[RequestUnit],
    output_dir: Path,
    *,
    max_units: int | None = None,
    collector_sha: str | None = None,
    continue_on_transient_error: bool = False,
    continue_on_unit_error: bool = False,
) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(output_dir / "ledger.json")
    completed = ledger.completed()
    collector_sha = collector_sha or os.environ.get("GITHUB_SHA", "local")
    processed = skipped = attempted = 0
    for unit in units:
        if unit.key in completed:
            skipped += 1
            continue
        if max_units is not None and attempted >= max_units:
            break
        attempted += 1
        try:
            collect_one(client, unit, output_dir, ledger, collector_sha=collector_sha)
        except TransientAPIError:
            if not (continue_on_transient_error or continue_on_unit_error):
                raise
        except (ValidationError, FileExistsError):
            if not continue_on_unit_error:
                raise
        else:
            processed += 1
    return processed, skipped
