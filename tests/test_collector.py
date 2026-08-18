from __future__ import annotations

import json
import gzip
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

from kra_collector.client import ParsedEnvelope, normalize_service_key, parse_envelope, sha256_bytes
from kra_collector.cli import month_range
from kra_collector.collect import Collector, canonical_json, request_id, write_deterministic_jsonl_gz
from kra_collector.registry import ENDPOINTS


def test_encoding_key_is_decoded_exactly_once() -> None:
    normalized, form = normalize_service_key("abc%2Bdef%2Fghi%3D")
    assert normalized == "abc+def/ghi="
    assert form == "encoding"

    prepared = requests.Request(
        "GET", "https://example.test", params={"serviceKey": normalized}
    ).prepare()
    assert "%252B" not in prepared.url
    assert "%252F" not in prepared.url
    assert "%253D" not in prepared.url
    assert parse_qs(urlsplit(prepared.url).query)["serviceKey"] == [normalized]


def test_decoding_key_is_unchanged() -> None:
    normalized, form = normalize_service_key("abc+def/ghi=")
    assert normalized == "abc+def/ghi="
    assert form == "decoding"


def test_parse_json_envelope() -> None:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL"},
            "body": {"items": {"item": [{"rcDate": 20210515}]}, "totalCount": 1},
        }
    }
    parsed = parse_envelope(json.dumps(payload).encode(), "application/json")
    assert parsed.total_count == 1
    assert parsed.rows == [{"rcDate": 20210515}]


def test_month_range_is_inclusive() -> None:
    assert month_range("2020-11", "2021-02") == [
        "2020-11",
        "2020-12",
        "2021-01",
        "2021-02",
    ]


def test_request_id_never_depends_on_service_key() -> None:
    params = {"meet": 1, "rc_month": "202101", "pageNo": 1}
    assert request_id("api30", params) == request_id("api30", dict(reversed(list(params.items()))))


def test_deterministic_normalized_hash(tmp_path: Path) -> None:
    rows = [{"b": 2, "a": 1}, {"a": "가"}]
    first = write_deterministic_jsonl_gz(tmp_path / "first.gz", rows)
    second = write_deterministic_jsonl_gz(tmp_path / "second.gz", rows)
    assert first == second
    assert (tmp_path / "first.gz").read_bytes() == (tmp_path / "second.gz").read_bytes()


class TwoPageClient:
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        rows = [{"row": 1}, {"row": 2}] if page == 1 else [{"row": 3}]
        content = json.dumps({"page": page, "rows": rows}).encode()
        envelope = ParsedEnvelope(rows, 3, "00", "NORMAL", "json")
        return content, "application/json", envelope


def test_manifest_records_counts_and_both_checksum_levels(tmp_path: Path) -> None:
    collector = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="test-snapshot",
    )
    record = collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)

    assert record.total_count == 3
    assert record.stored_rows == 3
    assert record.page_count == 2
    for page in record.pages:
        assert page["raw_sha256"] == sha256_bytes(
            (tmp_path / page["raw_path"]).read_bytes()
        )

    normalized = gzip.decompress((tmp_path / record.normalized_path).read_bytes())
    expected = b"".join(canonical_json({"row": value}) + b"\n" for value in (1, 2, 3))
    assert normalized == expected
    assert record.normalized_content_sha256 == sha256_bytes(expected)

    manifest = [json.loads(line) for line in collector.manifest_path.read_text().splitlines()]
    assert manifest[0]["total_count"] == manifest[0]["stored_rows"] == 3
    assert manifest[0]["normalized_content_sha256"] == sha256_bytes(expected)
