from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from kra_collector.cli import month_range
from kra_collector.client import (
    KRAClient,
    KRAResponseError,
    ParsedEnvelope,
    parse_envelope,
    service_key_candidates,
    sha256_bytes,
)
from kra_collector.collect import (
    ENFORCED_GATES,
    UNRUN_PILOT_GATES,
    Collector,
    canonical_json,
    request_id,
    write_deterministic_jsonl_gz,
)
from kra_collector.registry import ENDPOINTS
from kra_collector.scan import scan_tree
from kra_collector.verify import main as verify_main


def test_candidates_do_not_guess_from_key_shape() -> None:
    assert service_key_candidates("abc+def/ghi=") == [("as_provided", "abc+def/ghi=")]
    assert service_key_candidates("abc%2Bdef%2Fghi%3D") == [
        ("as_provided", "abc%2Bdef%2Fghi%3D"),
        ("url_decoded_once", "abc+def/ghi="),
    ]


def test_decoding_candidate_is_encoded_once_by_requests() -> None:
    normalized = service_key_candidates("abc%2Bdef%2Fghi%3D")[1][1]
    prepared = requests.Request(
        "GET", "https://example.test", params={"serviceKey": normalized}
    ).prepare()
    assert "%252B" not in prepared.url
    assert "%252F" not in prepared.url
    assert "%253D" not in prepared.url
    assert parse_qs(urlsplit(prepared.url).query)["serviceKey"] == [normalized]


class ProbeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.headers = {"Content-Type": "application/json"}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


class ProbeSession:
    def __init__(self) -> None:
        self.candidates: list[str] = []

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        candidate = str(params["serviceKey"])
        self.candidates.append(candidate)
        if "%2B" in candidate:
            payload = {
                "response": {
                    "header": {
                        "resultCode": "30",
                        "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    },
                    "body": {},
                }
            }
        else:
            payload = {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                    "body": {"items": {}, "totalCount": 0},
                }
            }
            return ProbeResponse(json.dumps(payload).encode())
        return ProbeResponse(json.dumps(payload).encode(), status_code=400)


def test_live_probe_selects_decoded_candidate_without_logging_key() -> None:
    session = ProbeSession()
    client = KRAClient("abc%2Bdef%2Fghi%3D", session=session)  # type: ignore[arg-type]
    assert client.key_candidate == "url_decoded_once"
    assert client.service_key == "abc+def/ghi="
    assert session.candidates == ["abc%2Bdef%2Fghi%3D", "abc+def/ghi="]


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
    assert request_id("api30", params) == request_id(
        "api30", dict(reversed(list(params.items())))
    )


def test_deterministic_normalized_hash(tmp_path: Path) -> None:
    rows = [{"b": 2, "a": 1}, {"a": "가"}]
    first = write_deterministic_jsonl_gz(tmp_path / "first.gz", rows)
    second = write_deterministic_jsonl_gz(tmp_path / "second.gz", rows)
    assert first == second
    assert (tmp_path / "first.gz").read_bytes() == (tmp_path / "second.gz").read_bytes()


class TwoPageClient:
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        rows = (
            [{"row": 1}, {"row": 2}]
            if page == 1
            else ([{"row": 3}] if page == 2 else [])
        )
        content = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                    "body": {"items": {"item": rows}, "totalCount": 3},
                }
            }
        ).encode()
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
    assert record.terminal_probe is not None
    assert record.terminal_probe["returned_rows"] == 0
    assert record.verification_gates["unrun"]
    for page in record.pages:
        assert page["raw_sha256"] == sha256_bytes(
            (tmp_path / page["raw_path"]).read_bytes()
        )

    normalized = gzip.decompress((tmp_path / record.normalized_path).read_bytes())
    expected = b"".join(canonical_json({"row": value}) + b"\n" for value in (1, 2, 3))
    assert normalized == expected
    assert record.normalized_content_sha256 == sha256_bytes(expected)

    manifest = [
        json.loads(line) for line in collector.manifest_path.read_text().splitlines()
    ]
    assert manifest[0]["total_count"] == manifest[0]["stored_rows"] == 3
    assert manifest[0]["normalized_content_sha256"] == sha256_bytes(expected)

    result = verify_main(
        [
            "--root",
            str(tmp_path),
            "--snapshot-id",
            "test-snapshot",
            "--start",
            "2021-05",
            "--end",
            "2021-05",
            "--meets",
            "1",
            "--endpoints",
            "api28",
        ]
    )
    assert result == 0
    quality = json.loads(
        (tmp_path / "reports" / "quality-test-snapshot.json").read_text()
    )
    assert quality["status"] == "core_transport_verified"
    assert quality["pilot_promotion_ready"] is False


class OverlappingPageClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        rows = [{"row": 1}, {"row": 2}] if page == 1 else [{"row": 2}]
        content = json.dumps({"page": page, "rows": rows}).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope(rows, 3, "00", "NORMAL", "json"),
        )


def test_overlapping_pages_fail_closed(tmp_path: Path) -> None:
    collector = Collector(
        OverlappingPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="overlap",
    )
    with pytest.raises(KRAResponseError, match="duplicate row"):
        collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


class FailIfCalledClient:
    def get(self, path: str, params: dict[str, object]):
        raise AssertionError("network call should have been skipped by the ledger")


def test_complete_manifest_and_hashes_enable_resume(tmp_path: Path) -> None:
    first = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="resume",
    )
    first.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)

    resumed = Collector(
        FailIfCalledClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="resume",
    ).collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    assert resumed.resumed is True


class MainRequestFailureSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        self.calls += 1
        if self.calls == 1:
            payload = {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                    "body": {"items": {}, "totalCount": 0},
                }
            }
            return ProbeResponse(json.dumps(payload).encode())
        return ProbeResponse(b"{}", status_code=400)


def test_http_error_does_not_retry_or_expose_query_string() -> None:
    session = MainRequestFailureSession()
    client = KRAClient(
        "abc+def/ghi=",
        session=session,
        minimum_interval_seconds=0,  # type: ignore[arg-type]
    )
    with pytest.raises(KRAResponseError) as caught:
        client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert session.calls == 2
    assert "serviceKey" not in str(caught.value)
    assert "abc" not in str(caught.value)


def test_artifact_secret_scan_checks_encoded_and_decoded_forms(tmp_path: Path) -> None:
    (tmp_path / "safe.json").write_text('{"ok": true}')
    assert scan_tree(tmp_path, "abc%2Bdef%2Fghi%3D") == []
    (tmp_path / "leak.txt").write_text("abc+def/ghi=")
    assert scan_tree(tmp_path, "abc%2Bdef%2Fghi%3D") == ["secret_detected:leak.txt"]


def test_machine_readable_gate_registry_matches_collector() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "config" / "verification-gates.json").read_text())
    assert registry["core_transport"] == ENFORCED_GATES
    assert registry["full_pilot_required"] == UNRUN_PILOT_GATES


def test_evidence_registry_never_fabricates_missing_hashes() -> None:
    root = Path(__file__).resolve().parents[1]
    claims = [
        json.loads(line)
        for line in (root / "evidence" / "claims.jsonl").read_text().splitlines()
        if line
    ]
    assert claims
    for claim in claims:
        if claim["reproduce_required"]:
            assert claim["request_key"] is None
            assert claim["raw_sha256"] is None
