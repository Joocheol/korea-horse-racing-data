from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
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
    retry_after_seconds,
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
    def __init__(
        self,
        content: bytes,
        status_code: int = 200,
        *,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type, **(headers or {})}
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
            return ProbeResponse(api5_success_xml(), content_type="application/xml")
        return ProbeResponse(json.dumps(payload).encode(), status_code=400)


def api5_success_xml() -> bytes:
    return b"""<response><header><resultCode>00</resultCode><resultMsg>NORMAL</resultMsg>
    </header><body><items/><totalCount>0</totalCount></body></response>"""


def test_live_probe_selects_decoded_candidate_without_logging_key() -> None:
    session = ProbeSession()
    client = KRAClient("abc%2Bdef%2Fghi%3D", session=session)  # type: ignore[arg-type]
    assert client.key_candidate == "url_decoded_once"
    assert client.service_key == "abc+def/ghi="
    assert session.candidates == ["abc%2Bdef%2Fghi%3D", "abc+def/ghi="]


class FlakyProbeSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        self.calls += 1
        if self.calls == 1:
            raise requests.Timeout("transient probe timeout")
        return ProbeResponse(api5_success_xml(), content_type="application/xml")


def test_live_xml_probe_retries_transient_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FlakyProbeSession()
    sleeps: list[float] = []
    monkeypatch.setattr("kra_collector.client.time.sleep", sleeps.append)
    client = KRAClient(
        "safe-key",
        session=session,
        max_attempts=2,  # type: ignore[arg-type]
    )
    assert client.key_candidate == "as_provided"
    assert session.calls == 2
    assert sleeps == [1]


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


class WrongPartitionClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        content, content_type, envelope = super().get(path, params)
        wrong_rows = [{**row, "rcDate": 20210601} for row in envelope.rows]
        payload = json.loads(content)
        payload["response"]["body"]["items"] = {"item": wrong_rows}
        return (
            json.dumps(payload).encode(),
            content_type,
            ParsedEnvelope(
                wrong_rows,
                envelope.total_count,
                envelope.result_code,
                envelope.result_message,
                envelope.response_format,
            ),
        )


def test_collector_rejects_rows_outside_requested_partition(tmp_path: Path) -> None:
    collector = Collector(
        WrongPartitionClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="wrong-partition",
    )
    with pytest.raises(KRAResponseError, match="requested month"):
        collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


class WrongPoolClient:
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        rows = (
            [
                {
                    "rcDate": 20210515,
                    "rcNo": 1,
                    "pool": "TRI",
                    "chulNo": 1,
                    "chulNo2": 2,
                    "chulNo3": 3,
                    "odds": "100.0",
                }
            ]
            if page == 1
            else []
        )
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL"},
                "body": {"items": {"item": rows}, "totalCount": 1},
            }
        }
        return (
            json.dumps(payload).encode(),
            "application/json",
            ParsedEnvelope(rows, 1, "00", "NORMAL", "json"),
        )


def test_collector_rejects_rows_from_another_requested_pool(tmp_path: Path) -> None:
    collector = Collector(
        WrongPoolClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=100,
        snapshot_id="wrong-pool",
    )
    with pytest.raises(KRAResponseError, match="requested pool"):
        collector.collect_month(ENDPOINTS["api30"], 1, "2021-05", "TLA")


def test_verifier_rejects_internally_consistent_wrong_partition(tmp_path: Path) -> None:
    collector = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="wrong-partition-verify",
    )
    record = collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    manifest = json.loads(collector.manifest_path.read_text())
    changed_rows: list[dict[str, object]] = []
    for page in manifest["pages"]:
        raw_path = tmp_path / page["raw_path"]
        payload = json.loads(raw_path.read_text())
        rows = payload["response"]["body"]["items"]["item"]
        for row in rows:
            row["rcDate"] = 20210615
        changed_rows.extend(rows)
        content = json.dumps(payload).encode()
        raw_path.write_bytes(content)
        page["raw_sha256"] = sha256_bytes(content)
    manifest["normalized_content_sha256"] = write_deterministic_jsonl_gz(
        tmp_path / record.normalized_path, changed_rows
    )
    collector.manifest_path.write_text(json.dumps(manifest) + "\n")

    assert (
        verify_main(
            [
                "--root",
                str(tmp_path),
                "--snapshot-id",
                "wrong-partition-verify",
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
        == 2
    )
    report = json.loads(
        (tmp_path / "reports" / "quality-wrong-partition-verify.json").read_text()
    )
    assert any(
        error.startswith("row_partition_or_business_key_invalid")
        for error in report["errors"]
    )


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


class TotalCountDriftClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        if page == 1:
            return super().get(path, params)
        rows = [api28_row(3, "4.3")]
        content = json.dumps({"page": page, "rows": rows}).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope(rows, 4, "00", "NORMAL", "json"),
        )


def test_total_count_drift_fails_closed(tmp_path: Path) -> None:
    collector = Collector(
        TotalCountDriftClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="total-count-drift",
    )
    with pytest.raises(KRAResponseError, match="totalCount changed"):
        collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


class NonemptyTerminalProbeClient(TwoPageClient):
    def get(self, path: str, params: dict[str, object]):
        page = int(params["pageNo"])
        if page < 3:
            return super().get(path, params)
        rows = [api28_row(4, "5.4")]
        content = json.dumps({"page": page, "rows": rows}).encode()
        return (
            content,
            "application/json",
            ParsedEnvelope(rows, 3, "00", "NORMAL", "json"),
        )


def test_nonempty_terminal_probe_fails_closed(tmp_path: Path) -> None:
    collector = Collector(
        NonemptyTerminalProbeClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="nonempty-terminal",
    )
    with pytest.raises(KRAResponseError, match="terminal page is not empty"):
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


def test_partial_resume_rejects_tampered_raw_page(tmp_path: Path) -> None:
    interrupted = Collector(
        InterruptAfterPageOneClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="tampered-partial",
    )
    with pytest.raises(KRAResponseError, match="simulated interruption"):
        interrupted.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)

    ledger_path = tmp_path / "ledgers" / "pages-tampered-partial.jsonl"
    entry = json.loads(ledger_path.read_text().splitlines()[0])
    raw_path = tmp_path / entry["page"]["raw_path"]
    raw_path.write_bytes(raw_path.read_bytes() + b"\n")

    with pytest.raises(KRAResponseError, match="partial raw page hash differs"):
        Collector(
            TrackingTwoPageClient(),  # type: ignore[arg-type]
            tmp_path,
            page_size=2,
            snapshot_id="tampered-partial",
        ).collect_month(ENDPOINTS["api28"], 1, "2021-05", None)


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


def test_verifier_rejects_missing_terminal_probe(tmp_path: Path) -> None:
    collector = Collector(
        TwoPageClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="missing-terminal",
    )
    collector.collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    manifest_path = tmp_path / "manifests" / "manifest-missing-terminal.jsonl"
    record = json.loads(manifest_path.read_text())
    record["terminal_probe"] = None
    manifest_path.write_text(json.dumps(record) + "\n")

    result = verify_main(
        [
            "--root",
            str(tmp_path),
            "--snapshot-id",
            "missing-terminal",
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
        (tmp_path / "reports" / "quality-missing-terminal.json").read_text()
    )
    assert any(error.startswith("terminal_probe_missing") for error in report["errors"])

    resumed = Collector(
        FailIfCalledClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=2,
        snapshot_id="missing-terminal",
    ).collect_month(ENDPOINTS["api28"], 1, "2021-05", None)
    assert resumed.resumed is True
    assert resumed.terminal_probe is not None
    assert resumed.terminal_probe["page_no"] == 3


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


def test_verifier_reports_durable_unresolved_request_state(tmp_path: Path) -> None:
    collector = Collector(
        FailIfCalledClient(),  # type: ignore[arg-type]
        tmp_path,
        page_size=100,
        snapshot_id="request-state",
    )
    collector.record_request_state(
        ENDPOINTS["api28"],
        1,
        "2021-05",
        None,
        "unresolved_transport",
        "KRAResponseError",
    )
    assert (
        verify_main(
            [
                "--root",
                str(tmp_path),
                "--snapshot-id",
                "request-state",
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
        == 2
    )
    report = json.loads(
        (tmp_path / "reports" / "quality-request-state.json").read_text()
    )
    assert report["request_state_counts"]["unresolved_transport"] == 1
    assert report["unresolved_requests"] == [
        {
            "endpoint_id": "api28",
            "meet": 1,
            "year_month": "2021-05",
            "pool": None,
            "state": "unresolved_transport",
            "error_type": "KRAResponseError",
        }
    ]


class MainRequestFailureSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        self.calls += 1
        if self.calls == 1:
            return ProbeResponse(api5_success_xml(), content_type="application/xml")
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
    def __init__(self) -> None:
        self.calls = 0

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        self.calls += 1
        if self.calls == 1:
            return ProbeResponse(api5_success_xml(), content_type="application/xml")
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


def successful_json_response() -> ProbeResponse:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL"},
            "body": {"items": {}, "totalCount": 0},
        }
    }
    return ProbeResponse(json.dumps(payload).encode())


class ProbeThenScriptedSession:
    def __init__(self, scripted: list[ProbeResponse]) -> None:
        self.scripted = scripted
        self.calls = 0

    def get(
        self, url: str, *, params: dict[str, object], **kwargs: object
    ) -> ProbeResponse:
        self.calls += 1
        if self.calls == 1:
            return ProbeResponse(api5_success_xml(), content_type="application/xml")
        return self.scripted.pop(0)


def test_retry_after_parser_supports_seconds_and_http_date() -> None:
    now = datetime(2026, 8, 18, 5, 0, tzinfo=UTC)
    assert retry_after_seconds("7", now=now) == 7
    assert (
        retry_after_seconds(
            format_datetime(now + timedelta(seconds=30), usegmt=True), now=now
        )
        == 30
    )
    assert retry_after_seconds("not-a-retry-after", now=now) is None


def test_429_honors_numeric_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ProbeThenScriptedSession(
        [
            ProbeResponse(b"{}", status_code=429, headers={"Retry-After": "7"}),
            successful_json_response(),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr("kra_collector.client.time.sleep", sleeps.append)
    client = KRAClient(
        "safe-key",
        session=session,  # type: ignore[arg-type]
        minimum_interval_seconds=0,
        max_attempts=2,
    )
    client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert sleeps == [7]
    assert session.calls == 3


def test_429_honors_http_date_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    retry_at = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    session = ProbeThenScriptedSession(
        [
            ProbeResponse(b"{}", status_code=429, headers={"Retry-After": retry_at}),
            successful_json_response(),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr("kra_collector.client.time.sleep", sleeps.append)
    client = KRAClient(
        "safe-key",
        session=session,  # type: ignore[arg-type]
        minimum_interval_seconds=0,
        max_attempts=2,
    )
    client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert len(sleeps) == 1
    assert 20 <= sleeps[0] <= 30


def test_repeated_503_stops_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ProbeThenScriptedSession(
        [ProbeResponse(b"{}", status_code=503) for _ in range(3)]
    )
    sleeps: list[float] = []
    monkeypatch.setattr("kra_collector.client.time.sleep", sleeps.append)
    client = KRAClient(
        "safe-key",
        session=session,  # type: ignore[arg-type]
        minimum_interval_seconds=0,
        max_attempts=3,
    )
    with pytest.raises(KRARetryableResponseError, match="after 3 attempts"):
        client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert session.calls == 4
    assert sleeps == [1, 2]


def test_http_200_daily_quota_envelope_is_not_retried() -> None:
    payload = {
        "returnReasonCode": "22",
        "errMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
    }
    session = ProbeThenScriptedSession([ProbeResponse(json.dumps(payload).encode())])
    client = KRAClient(
        "safe-key",
        session=session,  # type: ignore[arg-type]
        minimum_interval_seconds=0,
        max_attempts=5,
    )
    with pytest.raises(KRAQuotaExceededError):
        client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert session.calls == 2


def test_http_403_is_fatal_authentication_error() -> None:
    session = ProbeThenScriptedSession([ProbeResponse(b"forbidden", status_code=403)])
    client = KRAClient(
        "safe-key",
        session=session,  # type: ignore[arg-type]
        minimum_interval_seconds=0,
        max_attempts=5,
    )
    with pytest.raises(KRAAuthenticationError, match="authentication"):
        client.get("API28_1/singlePredictionRateInfo_1", {"pageNo": 1})
    assert session.calls == 2


class FakePreflightClient:
    key_candidate = "as_provided"

    def __init__(self, secret: str) -> None:
        assert secret

    def get(self, path: str, params: dict[str, object]):
        content = json.dumps({"probe": path, "params": params}, sort_keys=True).encode()
        base = {"rcDate": f"{params['rc_month']}04", "rcNo": 1}
        if path.startswith("API28"):
            row = {**base, "pool": "WIN", "chulNo": 1}
        elif path.startswith("API29"):
            row = {**base, "pool": "QNL", "chulNo1": 1, "chulNo2": 2}
        elif path.startswith("API30"):
            row = {
                **base,
                "pool": params["pool"],
                "chulNo": 1,
                "chulNo2": 2,
                "chulNo3": 3,
            }
        else:
            row = {**base, "pool": "WIN"}
        return (
            content,
            "application/json",
            ParsedEnvelope([row], 1, "00", "NORMAL", "json"),
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
    for probe in report["approval_probes"]:
        assert probe["raw_sha256"]
        assert probe["business_key_sha256"]
        assert probe["observed_business_key_aliases"]


class MissingBusinessKeyPreflightClient(FakePreflightClient):
    def get(self, path: str, params: dict[str, object]):
        content, content_type, _ = super().get(path, params)
        return (
            content,
            content_type,
            ParsedEnvelope([{"rcDate": "20200104"}], 1, "00", "NORMAL", "json"),
        )


def test_preflight_fails_when_live_row_does_not_support_business_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "safe-key")
    monkeypatch.setenv("KRA_QUOTA_LEDGER", str(tmp_path / "quota.jsonl"))
    monkeypatch.setattr(preflight, "KRAClient", MissingBusinessKeyPreflightClient)
    output = tmp_path / "preflight.json"
    assert (
        preflight.main(
            [
                "--start",
                "2020-01",
                "--end",
                "2020-01",
                "--meets",
                "1",
                "--endpoints",
                "api28",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


class ZeroThenPositivePreflightClient(FakePreflightClient):
    def get(self, path: str, params: dict[str, object]):
        if params["rc_month"] == "202001":
            content = json.dumps({"month": "202001"}).encode()
            return (
                content,
                "application/json",
                ParsedEnvelope([], 0, "00", "NORMAL", "json"),
            )
        return super().get(path, params)


def test_preflight_records_zero_month_then_validates_next_positive_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "safe-key")
    monkeypatch.setenv("KRA_QUOTA_LEDGER", str(tmp_path / "quota.jsonl"))
    monkeypatch.setattr(preflight, "KRAClient", ZeroThenPositivePreflightClient)
    output = tmp_path / "preflight.json"
    assert (
        preflight.main(
            [
                "--start",
                "2020-01",
                "--end",
                "2020-02",
                "--meets",
                "1",
                "--endpoints",
                "api28",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    probes = json.loads(output.read_text())["approval_probes"]
    assert [probe["approval_status"] for probe in probes] == [
        "probe_success_zero_rows",
        "probe_success_with_schema_evidence",
    ]


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
    expected_core = [
        "all_pages_total_count_constant",
        "rows_match_requested_partition",
        "business_key_unique_across_pages",
        "business_key_union_equals_total_count",
        "terminal_page_empty",
        "raw_sha256_verified",
        "normalized_content_sha256_verified",
    ]
    expected_pilot = [
        "api26_independent_starter_count",
        "api5_api29_quinella_cell_agreement",
        "overround_vs_verified_takeout",
        "turnover_ticket_interval_check",
        "turnover_and_finish_order_race_classification",
        "seven_pool_completeness",
        "quarantine_table_preservation",
    ]
    assert registry["core_transport"] == expected_core
    assert registry["full_pilot_required"] == expected_pilot
    assert ENFORCED_GATES == expected_core
    assert UNRUN_PILOT_GATES == expected_pilot


def test_endpoint_registry_freezes_transport_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "config" / "endpoints.yml").read_text())
    assert registry["credential_probe"] == {
        "endpoint_id": "api5",
        "service": "API5",
        "operation": "quinellaOddsInfo",
        "response_format": "xml",
        "required_params": [
            "meet",
            "rc_date",
            "rc_no",
            "pageNo",
            "numOfRows",
            "_type",
        ],
    }
    expected = {
        "api28": {
            "path": "API28_1/singlePredictionRateInfo_1",
            "pool_param": "prohibited",
            "pools": (None,),
            "key_fields": ("race_date", "race_number", "market", "selection_1"),
        },
        "api29": {
            "path": "API29_1/doublePredictionRateInfo_1",
            "pool_param": "prohibited",
            "pools": (None,),
            "key_fields": (
                "race_date",
                "race_number",
                "market",
                "selection_1",
                "selection_2",
            ),
        },
        "api30": {
            "path": "API30_1/triplePredictionRateInfo_1",
            "pool_param": "required",
            "pools": ("TLA", "TRI"),
            "key_fields": (
                "race_date",
                "race_number",
                "market",
                "selection_1",
                "selection_2",
                "selection_3",
            ),
        },
        "api179": {
            "path": "API179_1/salesAndDividendRate_1",
            "pool_param": "prohibited",
            "pools": (None,),
            "key_fields": ("race_date", "race_number", "market"),
        },
    }
    assert set(registry["endpoints"]) == set(expected) == set(ENDPOINTS)
    for endpoint_id, contract in expected.items():
        spec = ENDPOINTS[endpoint_id]
        assert spec.path == contract["path"]
        assert spec.response_format == "json"
        assert spec.pool_param == contract["pool_param"]
        assert spec.pools == contract["pools"]
        assert (
            tuple(field.name for field in spec.business_key_fields)
            == contract["key_fields"]
        )
        assert "totalCount" in spec.pagination
    selection_1 = ENDPOINTS["api30"].business_key_fields[3]
    assert selection_1.aliases == ("chulNo",)


def test_business_keys_normalize_aliases_and_ignore_changed_values() -> None:
    spec = ENDPOINTS["api30"]
    first = {
        "rcDate": "2021-05-15",
        "rcNo": "01",
        "pool": "tri",
        "chulNo": "01",
        "chulNo2": 2,
        "chulNo3": "03",
        "odds": "100.0",
    }
    changed_value = {**first, "odds": "999.9"}
    aliases = {
        "rc_date": "20210515",
        "rc_no": 1,
        "poolName": "TRI",
        "chulNo": 1,
        "chulNo2": "02",
        "chulNo3": 3,
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
    assert "quota-$(date -u +%F)-${GITHUB_RUN_ID}.jsonl.gpg" in workflow
    assert "quota-${quota_date}-" in workflow
    assert "group: collect-kra-data-go-kr-key" in workflow
    assert "${ARTIFACT_NAME}-run-${GITHUB_RUN_ID}.tar.gz.gpg" in workflow
    assert "${ARTIFACT_NAME}-run-${GITHUB_RUN_ID}-scan.json" in workflow
    assert "${ARTIFACT_NAME}-${SCAN_OUTCOME}" not in workflow


def test_snapshot_pr_explicitly_dispatches_collector_ci() -> None:
    root = Path(__file__).resolve().parents[1]
    collector_workflow = (
        root / ".github" / "workflows" / "collect-2020-2021.yml"
    ).read_text()
    ci_workflow = (root / ".github" / "workflows" / "ci.yml").read_text()
    assert "gh workflow run ci.yml" in collector_workflow
    assert "context='Collector CI'" in collector_workflow
    assert "workflow_dispatch:" in ci_workflow
    assert "TARGET_SHA: ${{ inputs.head_sha }}" in ci_workflow
    assert "context: 'Collector CI'" in ci_workflow


def test_implementation_review_publishes_a_fixed_blocking_status() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github" / "workflows" / "claude-implementation-review.yml"
    ).read_text()
    assert "contains(github.event.pull_request.labels" not in workflow
    assert "statuses: write" in workflow
    assert "context: 'Claude collector implementation review'" in workflow
    assert "if: always()" in workflow
