from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

DATASET_PREFIXES = {
    "double-exa.jsonl": "double-exa",
    "double-qnl.jsonl": "double-qnl",
    "double-qpl.jsonl": "double-qpl",
    "entries-all.jsonl": "entries",
    "quinella_crosscheck-all.jsonl": "quinella_crosscheck",
    "race_record-all.jsonl": "race_record",
    "sales-all.jsonl": "sales",
    "single-all.jsonl": "single",
    "triple-tla.jsonl": "triple-tla",
    "triple-tri.jsonl": "triple-tri",
}


def dataset_name(path: str) -> str | None:
    if "/results-all/date-" in f"/{path}":
        return "results"
    name = path.rsplit("/", 1)[-1]
    return DATASET_PREFIXES.get(name)


def _is_staged(path: str) -> bool:
    normalized = path.lstrip("./")
    return normalized.startswith("staged/") or "/staged/" in normalized


def _iter_zip(path: Path) -> Iterable[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".jsonl") and _is_staged(name):
                yield name, archive.read(name)


def _iter_dir(path: Path) -> Iterable[tuple[str, bytes]]:
    roots = [path / "staged", path / "output" / "staged"]
    if path.name == "staged":
        roots.insert(0, path)
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for file in root.rglob("*.jsonl"):
            resolved = file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield str(file.relative_to(path) if path in file.parents else file), file.read_bytes()


def _qnl_key(row: dict[str, object]) -> tuple[str, str, int, int, int]:
    return (
        str(row["rcDate"]),
        str(row["meet"]),
        int(row["rcNo"]),
        int(row["chulNo1"]),
        int(row["chulNo2"]),
    )


def audit_normalized(path: Path) -> dict[str, object]:
    iterator = _iter_zip(path) if path.is_file() else _iter_dir(path)
    stats: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "files": 0,
            "empty_files": 0,
            "rows": 0,
            "duplicate_rows": 0,
            "schemas": set(),
        }
    )
    qnl: dict[tuple[str, str, int, int, int], object] = {}
    crosscheck: dict[tuple[str, str, int, int, int], object] = {}

    staged_files = 0
    for name, data in iterator:
        dataset = dataset_name(name)
        if dataset is None:
            continue
        staged_files += 1
        current = stats[dataset]
        current["files"] = int(current["files"]) + 1
        lines = [line for line in data.splitlines() if line.strip()]
        if not lines:
            current["empty_files"] = int(current["empty_files"]) + 1
            continue
        seen: set[bytes] = set()
        for line in lines:
            current["rows"] = int(current["rows"]) + 1
            digest = hashlib.sha256(line).digest()
            if digest in seen:
                current["duplicate_rows"] = int(current["duplicate_rows"]) + 1
            else:
                seen.add(digest)
            row = json.loads(line)
            schemas = current["schemas"]
            assert isinstance(schemas, set)
            schemas.add(tuple(sorted(row)))
            if dataset == "double-qnl":
                qnl[_qnl_key(row)] = row["odds"]
            elif dataset == "quinella_crosscheck":
                crosscheck[_qnl_key(row)] = row["odds"]

    by_dataset: dict[str, dict[str, int]] = {}
    for dataset in sorted(stats):
        current = stats[dataset]
        schemas = current.pop("schemas")
        assert isinstance(schemas, set)
        by_dataset[dataset] = {
            "files": int(current["files"]),
            "empty_files": int(current["empty_files"]),
            "rows": int(current["rows"]),
            "schema_variants": len(schemas),
            "duplicate_rows": int(current["duplicate_rows"]),
        }

    shared = qnl.keys() & crosscheck.keys()
    crosscheck_report: dict[str, object] = {
        "double_qnl_rows": len(qnl),
        "api5_rows": len(crosscheck),
        "missing_in_api5": len(qnl.keys() - crosscheck.keys()),
        "missing_in_double_qnl": len(crosscheck.keys() - qnl.keys()),
        "odds_mismatches": sum(qnl[key] != crosscheck[key] for key in shared),
    }
    crosscheck_report["status"] = (
        "pass"
        if (not qnl and not crosscheck)
        or (
            crosscheck_report["missing_in_api5"] == 0
            and crosscheck_report["missing_in_double_qnl"] == 0
            and crosscheck_report["odds_mismatches"] == 0
        )
        else "fail"
    )
    totals = {
        "staged_files": staged_files,
        "empty_files": sum(item["empty_files"] for item in by_dataset.values()),
        "rows": sum(item["rows"] for item in by_dataset.values()),
        "duplicate_rows": sum(item["duplicate_rows"] for item in by_dataset.values()),
    }
    status = (
        "pass"
        if totals["duplicate_rows"] == 0 and crosscheck_report["status"] == "pass"
        else "fail"
    )
    return {
        "artifact": str(path),
        "status": status,
        "totals": totals,
        "by_dataset": by_dataset,
        "quinella_crosscheck": crosscheck_report,
        "notes": [
            "schema_variants count source-field presence variants; normalized preserves source-native types and field names",
            "empty files are archival warnings, not failures",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit staged/normalized KRA JSONL files")
    parser.add_argument(
        "path", type=Path, help="collection artifact ZIP or extracted collection directory"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_normalized(args.path)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
