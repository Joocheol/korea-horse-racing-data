from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, TextIO


POOL_MAP = {
    "단승식": "WIN",
    "연승식": "PLC",
    "복승식": "QNL",
    "쌍승식": "EXA",
    "복연승식": "QPL",
}
MEET_MAP = {"서울": 1, "제주": 2, "부경": 3, "부산경남": 3, "1": 1, "2": 2, "3": 3}
PROVIDER_FILES = (
    "20251017-meet-2-single-all.json",
    "20251017-meet-2-double-qnl.json",
    "20251017-meet-2-double-exa.json",
    "20251017-meet-2-double-qpl.json",
    "20251017-meet-3-single-all.json",
    "20251017-meet-3-double-qnl.json",
    "20251017-meet-3-double-exa.json",
    "20251017-meet-3-double-qpl.json",
)
UNCHANGED_FILES = ("races.jsonl.gz", "entries.jsonl.gz", "results.jsonl.gz", "sales.jsonl.gz")


def _as_int(value: Any) -> int:
    return int(str(value).strip())


def _meet(value: Any) -> int:
    text = str(value).strip()
    if text not in MEET_MAP:
        raise ValueError(f"unknown meet: {value!r}")
    return MEET_MAP[text]


def natural_key(row: dict[str, Any]) -> tuple[str, str, int, int | None, int | None]:
    pool = str(row["pool_code"])
    race_id = str(row["race_id"])
    if pool in {"WIN", "PLC"}:
        return race_id, pool, _as_int(row["chulNo"]), None, None
    if pool in {"QNL", "QPL"}:
        h1, h2 = sorted((_as_int(row["chulNo1"]), _as_int(row["chulNo2"])))
        return race_id, pool, h1, h2, None
    if pool == "EXA":
        return race_id, pool, _as_int(row["chulNo1"]), _as_int(row["chulNo2"]), None
    if pool in {"TLA", "TRI"}:
        horses = [_as_int(row["chulNo"]), _as_int(row["chulNo2"]), _as_int(row["chulNo3"])]
        if pool == "TLA":
            horses.sort()
        return race_id, pool, horses[0], horses[1], horses[2]
    raise ValueError(f"unknown pool_code: {pool!r}")


def key_horses(key: tuple[str, str, int, int | None, int | None]) -> tuple[int, ...]:
    return tuple(value for value in key[2:] if value is not None)


def open_deterministic_gzip_text(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    return io.TextIOWrapper(compressed, encoding="utf-8", newline="\n")


def emit(handle: TextIO, row: dict[str, Any]) -> None:
    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def read_jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_entries(path: Path) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for row in read_jsonl_gz(path):
        result[str(row["race_id"])].add(_as_int(row["chulNo"]))
    return result


def load_provider_rows(raw_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in PROVIDER_FILES:
        path = raw_dir / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        body = payload["response"]["body"]
        items = body["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        if _as_int(body["totalCount"]) != len(items):
            raise ValueError(f"incomplete provider response: {name}")
        for source in items:
            row = dict(source)
            row["meet"] = _meet(row["meet"])
            row["rcDate"] = _as_int(row["rcDate"])
            row["rcNo"] = _as_int(row["rcNo"])
            row["race_id"] = f"{row['rcDate']:08d}-{row['meet']}-{row['rcNo']:02d}"
            row["pool_code"] = POOL_MAP[str(row["pool"])]
            rows.append(row)
    return rows


def load_html_backfill(path: Path) -> dict[tuple[str, str, int, int | None, int | None], Decimal]:
    result: dict[tuple[str, str, int, int | None, int | None], Decimal] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["race_id"],
                row["pool_code"],
                _as_int(row["h1"]),
                _as_int(row["h2"]) if row["h2"] else None,
                _as_int(row["h3"]) if row["h3"] else None,
            )
            if key in result:
                raise ValueError(f"duplicate HTML natural key: {key}")
            result[key] = Decimal(row["odds"])
    return result


def compare_provider_to_html(
    provider_rows: Iterable[dict[str, Any]],
    html: dict[tuple[str, str, int, int | None, int | None], Decimal],
) -> dict[str, Any]:
    provider: dict[tuple[str, str, int, int | None, int | None], Decimal] = {}
    for row in provider_rows:
        key = natural_key(row)
        if key in provider:
            raise ValueError(f"duplicate provider natural key: {key}")
        provider[key] = Decimal(str(row["odds"]))
    html_keys, provider_keys = set(html), set(provider)
    mismatches = [key for key in html_keys & provider_keys if html[key] != provider[key]]
    by_meet_pool: Counter[tuple[str, str]] = Counter((key[0].split("-")[1], key[1]) for key in provider)
    report = {
        "html_rows": len(html),
        "provider_rows": len(provider),
        "common_keys": len(html_keys & provider_keys),
        "missing_from_provider": len(html_keys - provider_keys),
        "extra_in_provider": len(provider_keys - html_keys),
        "value_mismatches": len(mismatches),
        "by_meet_pool": {f"{meet}-{pool}": count for (meet, pool), count in sorted(by_meet_pool.items())},
    }
    report["exact_match"] = (
        report["html_rows"] == report["provider_rows"] == report["common_keys"] == 3_866
        and report["missing_from_provider"] == 0
        and report["extra_in_provider"] == 0
        and report["value_mismatches"] == 0
    )
    return report


def update_bundle(
    base: Path,
    provider_raw: Path,
    html_backfill: Path,
    output: Path,
    evidence: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)

    entries = load_entries(base / "entries.jsonl.gz")
    provider_rows = load_provider_rows(provider_raw)
    html = load_html_backfill(html_backfill)
    comparison = compare_provider_to_html(provider_rows, html)
    if not comparison["exact_match"]:
        raise ValueError(f"HTML/API comparison did not pass: {comparison}")

    provider_by_key = {natural_key(row): row for row in provider_rows}
    for key in provider_by_key:
        if not set(key_horses(key)).issubset(entries.get(key[0], set())):
            raise ValueError(f"provider key violates entry integrity: {key}")

    input_count = 0
    kept_count = 0
    rejected_count = 0
    rejected_by_race: Counter[str] = Counter()
    collisions = 0
    with open_deterministic_gzip_text(output / "odds.jsonl.gz") as handle:
        for row in read_jsonl_gz(base / "odds.jsonl.gz"):
            input_count += 1
            key = natural_key(row)
            if key in provider_by_key:
                collisions += 1
            if not set(key_horses(key)).issubset(entries.get(key[0], set())):
                rejected_count += 1
                rejected_by_race[key[0]] += 1
                continue
            emit(handle, row)
            kept_count += 1
        for key in sorted(provider_by_key):
            emit(handle, provider_by_key[key])

    if collisions:
        raise ValueError(f"provider keys already present in base bundle: {collisions}")
    if input_count != 29_192_211 or rejected_count != 72 or len(provider_rows) != 3_866:
        raise ValueError(
            f"unexpected migration counts: input={input_count}, rejected={rejected_count}, added={len(provider_rows)}"
        )

    target_race_pools: dict[str, set[str]] = defaultdict(set)
    for key in provider_by_key:
        target_race_pools[key[0]].add(key[1])
    coverage_count = 0
    updated_coverage_rows = 0
    with open_deterministic_gzip_text(output / "coverage.jsonl.gz") as handle:
        for row in read_jsonl_gz(base / "coverage.jsonl.gz"):
            coverage_count += 1
            pools = target_race_pools.get(str(row["race_id"]))
            if pools:
                for pool in pools:
                    row[f"odds_{pool.lower()}"] = True
                updated_coverage_rows += 1
            emit(handle, row)
    if coverage_count != 24_436 or updated_coverage_rows != 16:
        raise ValueError(
            f"unexpected coverage counts: rows={coverage_count}, updated={updated_coverage_rows}"
        )

    for name in UNCHANGED_FILES:
        shutil.copyfile(base / name, output / name)

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest["tables"]["odds_rows"] = kept_count + len(provider_rows)
    manifest["odds_source_policy"] = "KRA OpenAPI only; HTML backfill retired after exact natural-key/value match"
    manifest["provider_correction_migration"] = {
        "date": "2025-10-17",
        "base_odds_rows": input_count,
        "invalid_odds_rows_removed": rejected_count,
        "provider_rows_added": len(provider_rows),
        "html_rows_retained": 0,
        "canonical_odds_rows": kept_count + len(provider_rows),
        "comparison_exact_match": True,
        "provider_audit_run": 33028591323,
        "provider_audit_artifact": 9629358212,
        "html_backfill_sha256": sha256_file(html_backfill),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    checksum_names = (*UNCHANGED_FILES, "odds.jsonl.gz", "coverage.jsonl.gz", "manifest.json")
    checksum_lines = [f"{sha256_file(output / name)}  {name}" for name in checksum_names]
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "status": "success",
        "comparison": comparison,
        "base_odds_rows": input_count,
        "invalid_odds_rows_removed": rejected_count,
        "invalid_odds_by_race": dict(sorted(rejected_by_race.items())),
        "provider_rows_added": len(provider_rows),
        "canonical_odds_rows": kept_count + len(provider_rows),
        "coverage_rows": coverage_count,
        "coverage_rows_updated": updated_coverage_rows,
        "html_backfill_sha256": sha256_file(html_backfill),
        "output_sha256": {name: sha256_file(output / name) for name in (*checksum_names, "SHA256SUMS")},
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Replace verified HTML backfill with corrected KRA API rows")
    result.add_argument("--base", type=Path, required=True)
    result.add_argument("--provider-raw", type=Path, required=True)
    result.add_argument("--html-backfill", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--evidence", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = update_bundle(args.base, args.provider_raw, args.html_backfill, args.output, args.evidence)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
