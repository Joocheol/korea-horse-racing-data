from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

MEET_MAP = {"서울": 1, "제주": 2, "부경": 3, "부산경남": 3, "1": 1, "2": 2, "3": 3, 1: 1, 2: 2, 3: 3}
POOL_MAP = {
    "단승식": "WIN", "단식": "WIN", "연승식": "PLC", "연식": "PLC",
    "복승식": "QNL", "복식": "QNL", "쌍승식": "EXA", "쌍식": "EXA",
    "복연승식": "QPL", "복연": "QPL", "삼복승식": "TLA", "삼복": "TLA",
    "삼쌍승식": "TRI", "삼쌍": "TRI",
}
ODDS_FILES = (
    "single-all.jsonl", "double-qnl.jsonl", "double-exa.jsonl", "double-qpl.jsonl",
    "triple-tla.jsonl", "triple-tri.jsonl",
)
ALL_POOLS = ("WIN", "PLC", "QNL", "EXA", "QPL", "TLA", "TRI")


def normalize_meet(value: object) -> int:
    if value in MEET_MAP:
        return MEET_MAP[value]
    return MEET_MAP[str(value)]


def make_race_id(row: dict) -> str:
    return f"{row['rcDate']}-{normalize_meet(row['meet'])}-{int(row['rcNo']):02d}"


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def iter_paths(roots: list[Path], pattern: str) -> Iterable[Path]:
    for root in roots:
        yield from root.rglob(pattern)


def writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return gzip.open(path, "wt", encoding="utf-8", newline="\n")


def emit(handle, row: dict) -> None:
    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def build(staged_roots: list[Path], output: Path) -> dict:
    races: dict[str, dict] = {}
    race_record_rows = defaultdict(int)

    for path in iter_paths(staged_roots, "race_record-all.jsonl"):
        for row in read_jsonl(path):
            rid = make_race_id(row)
            race_record_rows[rid] += 1
            if rid not in races:
                base = {
                    "race_id": rid,
                    "year": int(str(row["rcDate"])[:4]),
                    "rc_date": int(row["rcDate"]),
                    "meet": normalize_meet(row["meet"]),
                    "rc_no": int(row["rcNo"]),
                }
                for key in ("rcDist", "rcName", "rank", "ageCond", "sexCond", "budam", "weather", "track"):
                    if key in row:
                        base[key] = row[key]
                races[rid] = base

    valid = set(races)
    counts = {
        "races": len(valid),
        "race_record_rows": sum(race_record_rows.values()),
        "entries_rows": 0,
        "results_rows": 0,
        "sales_rows": 0,
        "odds_rows": 0,
        "nonrace_odds_rows": 0,
    }
    sales_pools: dict[str, set[str]] = defaultdict(set)
    odds_pools: dict[str, set[str]] = defaultdict(set)

    with writer(output / "races.jsonl.gz") as handle:
        for rid in sorted(valid):
            row = dict(races[rid])
            row["race_record_rows"] = race_record_rows[rid]
            emit(handle, row)

    for kind, pattern in (("entries", "entries-all.jsonl"), ("results", "results-all/date-*.jsonl")):
        with writer(output / f"{kind}.jsonl.gz") as handle:
            for path in iter_paths(staged_roots, pattern):
                for row in read_jsonl(path):
                    rid = make_race_id(row)
                    if rid not in valid:
                        continue
                    row = dict(row)
                    row["race_id"] = rid
                    row["meet"] = normalize_meet(row["meet"])
                    emit(handle, row)
                    counts[f"{kind}_rows"] += 1

    with writer(output / "sales.jsonl.gz") as handle:
        for path in iter_paths(staged_roots, "sales-all.jsonl"):
            for row in read_jsonl(path):
                rid = make_race_id(row)
                if rid not in valid:
                    continue
                pool = POOL_MAP.get(row.get("pool"), str(row.get("pool")))
                row = dict(row)
                row["race_id"] = rid
                row["meet"] = normalize_meet(row["meet"])
                row["pool_code"] = pool
                emit(handle, row)
                sales_pools[rid].add(pool)
                counts["sales_rows"] += 1

    with writer(output / "odds.jsonl.gz") as handle:
        for name in ODDS_FILES:
            for path in iter_paths(staged_roots, name):
                for row in read_jsonl(path):
                    rid = make_race_id(row)
                    if rid not in valid:
                        counts["nonrace_odds_rows"] += 1
                        continue
                    pool = POOL_MAP.get(row.get("pool"), str(row.get("pool")))
                    row = dict(row)
                    row["race_id"] = rid
                    row["meet"] = normalize_meet(row["meet"])
                    row["pool_code"] = pool
                    emit(handle, row)
                    odds_pools[rid].add(pool)
                    counts["odds_rows"] += 1

    with writer(output / "coverage.jsonl.gz") as handle:
        for rid in sorted(valid):
            row = {"race_id": rid}
            for pool in ALL_POOLS:
                row[f"sales_{pool.lower()}"] = pool in sales_pools[rid]
                row[f"odds_{pool.lower()}"] = pool in odds_pools[rid]
            row["sales_missing_all"] = not sales_pools[rid]
            row["triple_not_offered"] = "TLA" not in sales_pools[rid] and "TRI" not in sales_pools[rid]
            emit(handle, row)

    counts["coverage_rows"] = len(valid)
    manifest = {
        "schema_version": 1,
        "race_universe": "race_record",
        "race_id_format": "YYYYMMDD-meet-rcNo",
        "missing_policy": "source gaps remain missing; never impute zero",
        "tables": counts,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.staged, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
