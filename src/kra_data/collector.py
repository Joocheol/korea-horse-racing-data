from __future__ import annotations

import os
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .client import KRAClient, Page
from .config import SCHEMA_VERSION
from .ledger import Ledger
from .models import RequestUnit
from .storage import atomic_write_bytes, canonical_json, write_immutable_json
from .validation import ValidationSummary, validate_pages


def _raw_payload(unit: RequestUnit, pages: list[Page]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request": {
            "endpoint": unit.endpoint,
            "meet": unit.meet,
            "month": unit.month,
            "pool": unit.pool,
        },
        "pages": [
            {"page_no": page.page_no, "total_count": page.total_count, "rows": page.rows}
            for page in pages
        ],
    }


def collect_one(
    client: KRAClient,
    unit: RequestUnit,
    output_dir: Path,
    ledger: Ledger,
    *,
    collector_sha: str,
    num_rows: int = 100_000,
) -> ValidationSummary:
    raw_path = output_dir / "raw" / unit.relative_path
    ledger.update(
        unit.key,
        "running",
        request={"endpoint": unit.endpoint, "meet": unit.meet, "month": unit.month, "pool": unit.pool},
        collector_sha=collector_sha,
        schema_version=SCHEMA_VERSION,
        raw_path=str(raw_path.relative_to(output_dir)),
    )
    captured_pages: list[Page] = []
    try:
        pages = client.collect_unit(unit, num_rows=num_rows, on_page=captured_pages.append)
        ledger.update(unit.key, "validating", page_count=len(pages))
        raw_sha256 = write_immutable_json(raw_path, _raw_payload(unit, pages))
        summary = validate_pages(pages)
        staged_path = output_dir / "staged" / unit.relative_path.replace(".json", ".jsonl")
        rows = [row for page in pages for row in page.rows]
        staged_bytes = b"".join(canonical_json(row) + b"\n" for row in rows)
        atomic_write_bytes(staged_path, staged_bytes)
        ledger.update(
            unit.key,
            "complete",
            raw_sha256=raw_sha256,
            staged_path=str(staged_path.relative_to(output_dir)),
            **asdict(summary),
        )
        return summary
    except Exception as exc:
        failure_path: str | None = None
        if captured_pages:
            run_id = os.environ.get("GITHUB_RUN_ID", "local")
            attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
            path = output_dir / "failures" / f"run-{run_id}-attempt-{attempt}" / unit.relative_path
            write_immutable_json(path, _raw_payload(unit, captured_pages))
            failure_path = str(path.relative_to(output_dir))
        ledger.update(
            unit.key,
            "failed",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            partial_raw_path=failure_path,
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
) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(output_dir / "ledger.json")
    completed = ledger.completed()
    collector_sha = collector_sha or os.environ.get("GITHUB_SHA", "local")
    processed = skipped = 0
    for unit in units:
        if unit.key in completed:
            skipped += 1
            continue
        if max_units is not None and processed >= max_units:
            break
        collect_one(client, unit, output_dir, ledger, collector_sha=collector_sha)
        processed += 1
    return processed, skipped
