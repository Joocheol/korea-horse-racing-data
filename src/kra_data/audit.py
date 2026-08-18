from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .client import Page
from .storage import atomic_write_bytes, canonical_json, sha256_bytes
from .validation import validate_pages


def audit_output(output: Path) -> dict[str, Any]:
    ledger_path = output / "ledger.json"
    if not ledger_path.exists():
        raise FileNotFoundError("ledger.json is missing")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    units = ledger.get("units")
    if not isinstance(units, dict):
        raise ValueError("ledger units are invalid")

    state_counts = Counter(str(value.get("state", "missing")) for value in units.values())
    errors: list[str] = []
    audited = 0
    for key, record in sorted(units.items()):
        if record.get("state") != "complete":
            errors.append(f"{key}: state={record.get('state')}")
            continue
        raw_path = output / str(record.get("raw_path", ""))
        if not raw_path.is_file():
            errors.append(f"{key}: raw file missing")
            continue
        raw_bytes = raw_path.read_bytes()
        if sha256_bytes(raw_bytes) != record.get("raw_sha256"):
            errors.append(f"{key}: raw checksum mismatch")
            continue
        payload = json.loads(raw_bytes)
        try:
            pages = [
                Page(int(page["page_no"]), int(page["total_count"]), list(page["rows"]))
                for page in payload["pages"]
            ]
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
        expected_staged = b"".join(
            canonical_json(row) + b"\n" for page in pages for row in page.rows
        )
        if staged_path.read_bytes() != expected_staged:
            errors.append(f"{key}: staged content mismatch")
            continue
        audited += 1

    report = {
        "ledger_units": len(units),
        "audited_complete_units": audited,
        "state_counts": dict(sorted(state_counts.items())),
        "errors": errors,
        "passed": not errors,
    }
    report_path = output / "quality" / "technical-audit.json"
    atomic_write_bytes(report_path, canonical_json(report) + b"\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit KRA raw files against the ledger")
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    report = audit_output(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
