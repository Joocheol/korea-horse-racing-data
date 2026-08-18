from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
from typing import Any

from .cli import month_range
from .client import KRAResponseError, parse_envelope, sha256_bytes
from .collect import ENFORCED_GATES, UNRUN_PILOT_GATES, canonical_json, write_atomic
from .registry import ENDPOINTS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a stored KRA snapshot")
    parser.add_argument("--root", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--meets", required=True)
    parser.add_argument("--endpoints", required=True)
    return parser


def _key(record: dict[str, Any]) -> tuple[str, int, str, str | None]:
    return (
        str(record["endpoint_id"]),
        int(record["meet"]),
        str(record["year_month"]),
        record.get("pool"),
    )


def _expected_keys(
    start: str, end: str, meets: list[int], endpoint_ids: list[str]
) -> set[tuple[str, int, str, str | None]]:
    return {
        (endpoint_id, meet, month, pool)
        for month in month_range(start, end)
        for meet in meets
        for endpoint_id in endpoint_ids
        for pool in ENDPOINTS[endpoint_id].pools
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    manifest_path = root / "manifests" / f"manifest-{args.snapshot_id}.jsonl"
    errors: list[str] = []
    records: dict[tuple[str, int, str, str | None], dict[str, Any]] = {}
    if not manifest_path.exists():
        errors.append("manifest_missing")
    else:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get("status") == "complete":
                    records[_key(record)] = record

    meets = [int(value) for value in args.meets.split(",") if value]
    endpoint_ids = [value for value in args.endpoints.split(",") if value]
    expected = _expected_keys(args.start, args.end, meets, endpoint_ids)
    missing = sorted(expected - set(records), key=str)
    if missing:
        errors.append(f"missing_logical_requests={len(missing)}")

    verified_rows = 0
    zero_row_logical_requests = 0
    for key, record in records.items():
        if key not in expected:
            continue
        total_count = int(record["total_count"])
        if total_count == 0:
            zero_row_logical_requests += 1
        if int(record["stored_rows"]) != total_count:
            errors.append(f"stored_rows_mismatch:{key}")
            continue

        raw_row_hashes: set[str] = set()
        pages = record.get("pages", [])
        page_size = int(
            record.get("canonical_params_without_service_key", {}).get("numOfRows", 0)
        )
        expected_page_count = (
            max(1, math.ceil(total_count / page_size)) if page_size > 0 else 0
        )
        page_numbers = [int(page.get("page_no", 0)) for page in pages]
        if page_size <= 0:
            errors.append(f"invalid_page_size:{key}")
        if page_numbers != list(range(1, expected_page_count + 1)):
            errors.append(f"page_sequence_mismatch:{key}")
        if int(record.get("page_count", -1)) != expected_page_count:
            errors.append(f"page_count_mismatch:{key}")
        for page in pages:
            path = root / page["raw_path"]
            if not path.exists():
                errors.append(f"raw_missing:{key}:{page['page_no']}")
                continue
            content = path.read_bytes()
            if sha256_bytes(content) != page["raw_sha256"]:
                errors.append(f"raw_hash_mismatch:{key}:{page['page_no']}")
                continue
            try:
                envelope = parse_envelope(content, page.get("content_type", ""), "json")
            except KRAResponseError:
                errors.append(f"raw_envelope_invalid:{key}:{page['page_no']}")
                continue
            if envelope.total_count != total_count:
                errors.append(f"page_total_count_mismatch:{key}:{page['page_no']}")
            page_no = int(page["page_no"])
            expected_rows = (
                page_size
                if page_no < expected_page_count
                else max(0, total_count - page_size * (expected_page_count - 1))
            )
            if (
                len(envelope.rows) != expected_rows
                or int(page.get("returned_rows", -1)) != expected_rows
            ):
                errors.append(f"page_row_count_mismatch:{key}:{page_no}")
            for row in envelope.rows:
                row_hash = sha256_bytes(canonical_json(row))
                if row_hash in raw_row_hashes:
                    errors.append(f"duplicate_row:{key}:{page['page_no']}")
                raw_row_hashes.add(row_hash)

        if len(raw_row_hashes) != total_count:
            errors.append(f"deduplicated_count_mismatch:{key}")

        probe = record.get("terminal_probe")
        if not probe:
            errors.append(f"terminal_probe_missing:{key}")
        else:
            expected_probe_page = expected_page_count + 1
            if int(probe.get("page_no", 0)) != expected_probe_page:
                errors.append(f"terminal_probe_page_mismatch:{key}")
            probe_path = root / probe["raw_path"]
            if not probe_path.exists():
                errors.append(f"terminal_probe_raw_missing:{key}")
            else:
                probe_content = probe_path.read_bytes()
                if sha256_bytes(probe_content) != probe["raw_sha256"]:
                    errors.append(f"terminal_probe_hash_mismatch:{key}")
                try:
                    probe_envelope = parse_envelope(
                        probe_content, probe.get("content_type", ""), "json"
                    )
                except KRAResponseError:
                    errors.append(f"terminal_probe_envelope_invalid:{key}")
                    continue
                if probe_envelope.rows or probe_envelope.total_count != total_count:
                    errors.append(f"terminal_probe_not_empty:{key}")

        normalized_path = root / record["normalized_path"]
        if not normalized_path.exists():
            errors.append(f"normalized_missing:{key}")
            continue
        try:
            normalized_content = gzip.decompress(normalized_path.read_bytes())
        except (OSError, EOFError):
            errors.append(f"normalized_invalid_gzip:{key}")
            continue
        if sha256_bytes(normalized_content) != record["normalized_content_sha256"]:
            errors.append(f"normalized_hash_mismatch:{key}")
        normalized_hashes = {
            sha256_bytes(canonical_json(json.loads(line)))
            for line in normalized_content.decode("utf-8").splitlines()
            if line
        }
        if normalized_hashes != raw_row_hashes:
            errors.append(f"normalized_raw_set_mismatch:{key}")
        verified_rows += len(normalized_hashes)

    if expected and verified_rows == 0:
        errors.append("all_zero_snapshot_has_no_positive_row_evidence")

    report = {
        "schema_version": "1",
        "snapshot_id": args.snapshot_id,
        "status": "failed" if errors else "core_transport_verified",
        "expected_logical_requests": len(expected),
        "complete_logical_requests": len(set(records) & expected),
        "verified_rows": verified_rows,
        "zero_row_logical_requests": zero_row_logical_requests,
        "enforced_gates": ENFORCED_GATES,
        "unrun_pilot_gates": UNRUN_PILOT_GATES,
        "pilot_promotion_ready": False,
        "errors": errors,
    }
    report_path = root / "reports" / f"quality-{args.snapshot_id}.json"
    write_atomic(report_path, canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
