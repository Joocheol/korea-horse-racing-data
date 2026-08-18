from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from kra_collector import preflight
from kra_collector.cli import month_range
from kra_collector.client import (
    KRAAuthenticationError,
    KRAClient,
    KRAQuotaExceededError,
    KRAResponseError,
    KRARetryableResponseError,
    ParsedEnvelope,
    parse_envelope,
    service_key_candidates,
    sha256_bytes,
)
from kra_collector.collect import (
    ENFORCED_GATES,
    MAX_CALLS_PER_LOGICAL_REQUEST,
    UNRUN_PILOT_GATES,
    Collector,
    business_key_hash,
    canonical_json,
    request_id,
    required_calls_for_total,
    write_deterministic_jsonl_gz,
)
from kra_collector.registry import ENDPOINTS
from kra_collector.scan import main as scan_main
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


@pytest.mark.parametrize(
    "payload",
    [
        {
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "returnReasonCode": "22",
                    "errMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
                }
            }
        },
        {
            "returnReasonCode": "22",
            "errMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
        },
    ],
)
def test_http_200_json_daily_quota_envelope_stops_immediately(
    payload: dict[str, object],
) -> None:
    with pytest.raises(KRAQuotaExceededError):
        parse_envelope(json.dumps(payload).encode(), "application/json")


def test_http_200_per_second_limit_is_retryable() -> None:
    payload = {
        "returnReasonCode": "23",
        "errMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR",
    }
    with pytest.raises(KRARetryableResponseError):
        parse_envelope(json.dumps(payload).encode(), "application/json")


def test_http_200_xml_auth_envelope_is_not_zero_rows() -> None:
    payload = b"""<OpenAPI_ServiceResponse><cmmMsgHeader>
    <returnReasonCode>30</returnReasonCode>
    <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
    </cmmMsgHeader></OpenAPI_ServiceResponse>"""
    with pytest.raises(KRAAuthenticationError):
        parse_envelope(payload, "application/xml")


def test_success_envelope_requires_total_count() -> None:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL"},
            "body": {"items": {}},
        }
    }
    with pytest.raises(KRAResponseError, match="totalCount"):
        parse_envelope(json.dumps(payload).encode(), "application/json")


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
            [api28_row(1, "2.1"), api28_row(2, "3.2")]
            if page == 1
            else ([api28_row(3, "4.3")] if page == 2 else [])
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


def api28_row(selection: int, odds: str) -> dict[str, object]:
    return {
        "rcDate": 20210515,
        "rcNo": 1,
        "pool": "WIN",
        "chulNo": selection,
        "odds": odds,
    }


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
    expected = b"".join(
        canonical_json(api28_row(selection, odds)) + b"\n"
        for selection, odds in ((1, "2.1"), (2, "3.2"), (3, "4.3"))
    )
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
        rows = (
            [api28_row(1, "2.1"), api28_row(2, "3.2")]
            if page == 1
            else [api28_row(2, "9.9")]
        )
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
    with pytest.raises(KRAResponseError, match="duplicate business key"):
        collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


class ServerCapClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        rows = [api28_row(1, "2.1"), api28_row(2, "3.2")]
        content = json.dumps({"rows": rows}).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope(rows, 10, "00", "NORMAL", "json"),
        )


def test_unexpected_server_page_cap_fails_on_first_page(tmp_path: Path) -> None:
    collector = Collector(
        ServerCapClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=100_000,
        snapshot_id="server-cap",
    )
    with pytest.raises(KRAResponseError, match="server page cap"):
        collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


def test_pagination_budget_fails_before_an_unapproved_fourth_call() -> None:
    assert required_calls_for_total(0, 100_000) == 2
    assert required_calls_for_total(115_356, 100_000) == 3
    assert required_calls_for_total(200_001, 100_000) == 4
    assert MAX_CALLS_PER_LOGICAL_REQUEST == 3


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


class InterruptAfterPageOneClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        if int(params["pageNo"]) > 1:
            raise KRAResponseError("simulated interruption")
        return super().get(path, params)


class TrackingTwoPageClient(TwoPageClient):
    def __init__(self) -> None:
        self.pages: list[int] = []

    def get(self, path: str, params: dict[str, object]):
        self.pages.append(int(params["pageNo"]))
        return super().get(path, params)


def test_partial_page_ledger_resumes_at_next_page(tmp_path: Path) -> None:
    interrupted = Collector(
        InterruptAfterPageOneClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="page-resume",
    )
    with pytest.raises(KRAResponseError, match="simulated interruption"):
        interrupted.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)

    ledger_path = tmp_path / "ledgers" / "pages-page-resume.jsonl"
    entries = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert [(entry["kind"], entry["page"]["page_no"]) for entry in entries] == [
        ("data", 1)
    ]

    client = TrackingTwoPageClient()
    record = Collector(
        client,  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="page-resume",
    ).collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    assert client.pages == [2, 3]
    assert record.resumed is True
    assert record.stored_rows == 3


def test_partial_resume_survives_commit_change_when_contract_is_same(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "first-commit")
    interrupted = Collector(
        InterruptAfterPageOneClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="commit-change",
    )
    with pytest.raises(KRAResponseError):
        interrupted.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    monkeypatch.setenv("GITHUB_SHA", "second-commit")
    client = TrackingTwoPageClient()
    record = Collector(
        client,  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="commit-change",
    ).collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    assert client.pages == [2, 3]
    assert record.collector_commit == "second-commit"


def test_resume_rejects_changed_request_identity(tmp_path: Path) -> None:
    first = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="resume-identity",
    )
    first.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    changed = Collector(
        FailIfCalledClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=3,
        snapshot_id="resume-identity",
    )
    with pytest.raises(KRAResponseError, match="resume identity"):
        changed.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


class ZeroPageClient:
    def get(self, path: str, params: dict[str, object]):
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                "body": {"items": {}, "totalCount": 0},
            }
        }
        content = json.dumps(payload).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope([], 0, "00", "NORMAL", "json"),
        )


def test_all_zero_snapshot_fails_and_uses_a_real_page_two_probe(tmp_path: Path) -> None:
    collector = Collector(
        ZeroPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=100,
        snapshot_id="all-zero",
    )
    record = collector.collect_month(ENDPOINTS["api28"], 1, "2020-04", None)
    assert record.terminal_probe is not None
    assert record.terminal_probe["page_no"] == 2
    result = verify_main(
        [
            "--root",
            str(tmp_path),
            "--snapshot-id",
            "all-zero",
            "--start",
            "2020-04",
            "--end",
            "2020-04",
            "--meets",
            "1",
            "--endpoints",
            "api28",
        ]
    )
    assert result == 2
    report = json.loads((tmp_path / "reports" / "quality-all-zero.json").read_text())
    assert "all_zero_snapshot_has_no_positive_row_evidence" in report["errors"]


def test_verifier_rejects_manifest_page_gap(tmp_path: Path) -> None:
    collector = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="page-gap",
    )
    collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    manifest_path = tmp_path / "manifests" / "manifest-page-gap.jsonl"
    record = json.loads(manifest_path.read_text())
    record["pages"] = record["pages"][1:]
    manifest_path.write_text(json.dumps(record) + "\n")
    result = verify_main(
        [
            "--root",
            str(tmp_path),
            "--snapshot-id",
            "page-gap",
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
    assert result == 2
    report = json.loads((tmp_path / "reports" / "quality-page-gap.json").read_text())
    assert any(error.startswith("page_sequence_mismatch") for error in report["errors"])


def test_verifier_recomputes_request_identity(tmp_path: Path) -> None:
    collector = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="request-identity",
    )
    collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    manifest_path = tmp_path / "manifests" / "manifest-request-identity.jsonl"
    record = json.loads(manifest_path.read_text())
    record["canonical_params_without_service_key"]["meet"] = 2
    manifest_path.write_text(json.dumps(record) + "\n")
    result = verify_main(
        [
            "--root",
            str(tmp_path),
            "--snapshot-id",
            "request-identity",
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
    assert result == 2
    report = json.loads(
        (tmp_path / "reports" / "quality-request-identity.json").read_text()
    )
    assert any(error.startswith("request_id_mismatch") for error in report["errors"])
    assert any(error.startswith("request_meet_mismatch") for error in report["errors"])


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


class AlwaysSuccessfulSession:
    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                "body": {"items": {}, "totalCount": 0},
            }
        }
        return ProbeResponse(json.dumps(payload).encode())


def test_quota_ledger_counts_attempts_and_enforces_local_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "quota" / "usage.jsonl"
    monkeypatch.setenv("KRA_QUOTA_LEDGER", str(ledger))
    monkeypatch.setenv("DATA_GO_KR_OPERATING_CAP_API5", "10")
    monkeypatch.setenv("DATA_GO_KR_OPERATING_CAP_API28", "1")
    client = KRAClient(
        "safe-key",
        session=AlwaysSuccessfulSession(),  # type: ignore[arg-type]
        minimum_interval_seconds=0,
    )
    client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    with pytest.raises(KRAQuotaExceededError, match="local operating cap"):
        client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 2})
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [record["endpoint_id"] for record in records] == ["api5", "api28"]


class FakePreflightClient:
    key_candidate = "as_provided"

    def __init__(self, secret: str) -> None:
        assert secret

    def get(self, path: str, params: dict[str, object]):
        content = json.dumps({"probe": path, "params": params}, sort_keys=True).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope([], 0, "00", "NORMAL", "json"),
        )


def test_preflight_reports_tier_used_calls_and_operating_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "safe-key")
    monkeypatch.setenv("KRA_QUOTA_LEDGER", str(tmp_path / "quota.jsonl"))
    monkeypatch.setattr(preflight, "KRAClient", FakePreflightClient)
    output = tmp_path / "preflight.json"
    result = preflight.main(
        [
            "--start",
            "2020-01",
            "--end",
            "2021-12",
            "--meets",
            "1,2,3",
            "--endpoints",
            "api28,api29,api30,api179",
            "--page-size",
            "100000",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    report = json.loads(output.read_text())
    assert report["budgets"]["api28"]["account_tier"] == "development"
    assert report["budgets"]["api28"]["production_approval_status"] == "unverified"
    assert report["budgets"]["api28"]["production_review_lead_time"] == "unverified"
    assert report["budgets"]["api28"]["official_daily_cap"] == 3000
    assert report["budgets"]["api28"]["operating_cap"] == 2500
    assert report["budgets"]["api28"]["estimated_operating_days"] == 1
    assert report["budgets"]["api5"]["approval_status"] == "credential_probe_success"


def test_artifact_secret_scan_checks_encoded_and_decoded_forms(tmp_path: Path) -> None:
    (tmp_path / "safe.json").write_text('{"ok": true}')
    assert scan_tree(tmp_path, "abc%2Bdef%2Fghi%3D") == []
    (tmp_path / "leak.txt").write_text("abc+def/ghi=")
    assert scan_tree(tmp_path, "abc%2Bdef%2Fghi%3D") == ["secret_detected:leak.txt"]


def test_secret_scan_writes_redacted_quarantine_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "leak.txt").write_text("abc+def/ghi=")
    report = tmp_path / "scan-report.json"
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "abc%2Bdef%2Fghi%3D")
    assert scan_main(["--root", str(tmp_path), "--report", str(report)]) == 2
    payload = json.loads(report.read_text())
    assert payload == {"status": "failed", "findings": ["secret_detected:leak.txt"]}
    assert "abc" not in report.read_text()


def test_machine_readable_gate_registry_matches_collector() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "config" / "verification-gates.json").read_text())
    assert registry["core_transport"] == ENFORCED_GATES
    assert registry["full_pilot_required"] == UNRUN_PILOT_GATES


def test_endpoint_registry_freezes_transport_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "config" / "endpoints.yml").read_text())
    assert set(registry["endpoints"]) == set(ENDPOINTS)
    for endpoint_id, spec in ENDPOINTS.items():
        frozen = registry["endpoints"][endpoint_id]
        assert frozen["response_format"] == spec.response_format == "json"
        assert "totalCount" in frozen["pagination"]
        assert set(spec.success_codes)
        assert spec.business_key_fields
        if spec.pool_param == "required":
            assert all(pool is not None for pool in spec.pools)


def test_business_keys_normalize_aliases_and_ignore_changed_values() -> None:
    spec = ENDPOINTS["api30"]
    first = {
        "rcDate": "2021-05-15",
        "rcNo": "01",
        "pool": "tri",
        "chulNo1": "01",
        "chulNo2": 2,
        "chulNo3": "03",
        "odds": "100.0",
    }
    changed_value = {**first, "odds": "999.9"}
    aliases = {
        "rc_date": "20210515",
        "rc_no": 1,
        "poolName": "TRI",
        "hrNo1": 1,
        "hrNo2": "02",
        "hrNo3": 3,
        "odds": "100.0",
    }
    assert business_key_hash(spec, first) == business_key_hash(spec, changed_value)
    assert business_key_hash(spec, first) == business_key_hash(spec, aliases)


def test_evidence_registry_never_fabricates_missing_hashes() -> None:
    root = Path(__file__).resolve().parents[1]
    claims = [
        json.loads(line)
        for line in (root / "evidence" / "claims.jsonl").read_text().splitlines()
        if line
    ]
    assert claims
    for claim in claims:
        assert {
            "status",
            "observed_at",
            "run_id",
            "endpoint_version",
            "supersedes",
        } <= set(claim)
        if claim["reproduce_required"]:
            assert claim["status"] == "reproduce_required"
            assert claim["request_key"] is None
            assert claim["raw_sha256"] is None


def test_collection_workflow_has_encrypted_durable_quarantine() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "collect-2020-2021.yml").read_text()
    assert "KRA_ARCHIVE_PASSPHRASE" in workflow
    assert "--cipher-algo AES256" in workflow
    assert "kra-private-archive" in workflow
    assert "if: always()" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "quota-$(date -u +%F).jsonl.gpg" in workflow
    assert "group: collect-kra-data-go-kr-key" in workflow
