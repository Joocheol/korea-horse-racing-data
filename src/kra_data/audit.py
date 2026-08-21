from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .client import parse_response
from .storage import atomic_write_bytes, canonical_json, sha256_bytes
from .validation import validate_pages


def audit_output(output: Path, endpoints: set[str] | None = None) -> dict[str, Any]:
    ledger_path = output / "ledger.json"
    if not ledger_path.exists():
        raise FileNotFoundError("ledger.json is missing")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    units = ledger.get("units")
    if not isinstance(units, dict):
        raise ValueError("ledger units are invalid")

    selected_units = {
        key: record
        for key, record in units.items()
        if endpoints is None
        or str(record.get("request", {}).get("endpoint", "")) in endpoints
    }
    state_counts = Counter(
        str(value.get("state", "missing")) for value in selected_units.values()
    )
    errors: list[str] = []
    audited = 0
    for key, record in sorted(selected_units.items()):
        if record.get("state") != "complete":
            errors.append(f"{key}: state={record.get('state')}")
            continue
        raw_files = record.get("raw_files")
        if not isinstance(raw_files, list) or not raw_files:
            errors.append(f"{key}: raw file manifest missing")
            continue
        pages = []
        try:
            for raw_file in sorted(raw_files, key=lambda item: int(item["page_no"])):
                raw_path = output / str(raw_file["path"])
                raw_bytes = raw_path.read_bytes()
                if sha256_bytes(raw_bytes) != raw_file.get("sha256"):
                    raise ValueError(f"raw checksum mismatch: {raw_file['path']}")
                pages.append(parse_response(raw_bytes, str(raw_file["format"]), int(raw_file["page_no"])))
            summary = validate_pages(pages)
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
            continue
        if summary.raw_rows != record.get("raw_rows"):
            errors.append(f"{key}: ledger row count mismatch")
            continue
        staged_path = output / str(record.get("staged_path", ""))
        if not staged_path.is_file():
            errors.append(f"{key}: staged file missing")
            continue
        expected_staged = b"".join(canonical_json(row) + b"\n" for page in pages for row in page.rows)
        if staged_path.read_bytes() != expected_staged:
            errors.append(f"{key}: staged content mismatch")
            continue
        audited += 1

    report = {
        "ledger_units": len(selected_units),
        "total_ledger_units": len(units),
        "endpoint_filter": sorted(endpoints) if endpoints is not None else None,
        "audited_complete_units": audited,
        "state_counts": dict(sorted(state_counts.items())),
        "errors": errors,
        "passed": not errors,
    }
    atomic_write_bytes(output / "quality" / "technical-audit.json", canonical_json(report) + b"\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit KRA raw files against the ledger")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument(
        "--endpoints",
        help="comma-separated endpoint names to audit; default audits the full ledger",
    )
    args = parser.parse_args(argv)
    endpoints = (
        {item for item in args.endpoints.split(",") if item}
        if args.endpoints is not None
        else None
    )
    report = audit_output(args.output, endpoints=endpoints)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
