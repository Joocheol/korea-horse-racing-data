from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from kra_data.audit import audit_output
from kra_data.cli import main as collect_main
from kra_data.client import KRAClient, Page, parse_page, parse_response
from kra_data.collector import collect_units
from kra_data.config import ENDPOINTS
from kra_data.errors import PermanentAPIError, SchemaError, TransientAPIError, ValidationError
from kra_data.ledger import Ledger
from kra_data.models import RequestUnit
from kra_data.planning import build_units
from kra_data.preflight import check_budget, estimate_calls
from kra_data.probe import main as probe_main
from kra_data.storage import write_immutable_bytes
from kra_data.validation import validate_pages


FIXTURES = Path(__file__).parent / "fixtures"


def json_page(page_no: int, total_count: int, rows: list[dict[str, object]]) -> Page:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": {"item": rows} if rows else "", "totalCount": total_count},
        }
    }
    raw = json.dumps(payload, ensure_ascii=False).encode()
    return parse_response(raw, "json", page_no)


class ParseTests(unittest.TestCase):
    def test_single_json_row_is_normalized_to_list(self) -> None:
        raw = (FIXTURES / "page_one.json").read_bytes()
        page = parse_response(raw, "json", 1)
        self.assertEqual(page.total_count, 1)
        self.assertEqual(len(page.rows), 1)
        self.assertEqual(page.raw_body, raw)

    def test_xml_row_is_parsed_without_changing_raw_bytes(self) -> None:
        raw = (FIXTURES / "page_one.xml").read_bytes()
        page = parse_response(raw, "xml", 1)
        self.assertEqual(page.rows[0]["rcNo"], "1")
        self.assertEqual(page.raw_body, raw)

    def test_empty_items_are_valid_when_total_is_zero(self) -> None:
        payload = json.loads((FIXTURES / "page_empty.json").read_text())
        page = parse_page(payload, 1)
        self.assertEqual(page.total_count, 0)
        self.assertEqual(page.rows, [])

    def test_schema_drift_fails_closed(self) -> None:
        with self.assertRaises(SchemaError):
            parse_page({"changed": {}}, 1)

    def test_transport_error_keeps_underlying_reason_without_service_key(self) -> None:
        def timed_out(*args, **kwargs):
            raise URLError(TimeoutError("timed out"))

        client = KRAClient("secret-value", max_attempts=1, opener=timed_out)
        with self.assertRaises(TransientAPIError) as raised:
            client.fetch_page(RequestUnit("single", 1, "202001"), 1, 10)
        message = str(raised.exception)
        self.assertIn("TimeoutError: timed out", message)
        self.assertNotIn("secret-value", message)

    def test_http_error_reports_body_without_service_key(self) -> None:
        service_key = "decoded+secret/key=="
        encoded_key = "decoded%2Bsecret%2Fkey%3D%3D"

        def forbidden(*args, **kwargs):
            body = (
                "<error><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
                f"</returnAuthMsg><request>serviceKey={encoded_key}&amp;pageNo=1</request></error>"
            ).encode()
            raise HTTPError(
                "https://example.invalid",
                403,
                "Forbidden",
                {},
                io.BytesIO(body),
            )

        client = KRAClient(service_key, max_attempts=1, opener=forbidden)
        with self.assertRaises(PermanentAPIError) as raised:
            client.fetch_page(RequestUnit("results", 1, "202512"), 1, 10)
        message = str(raised.exception)
        self.assertIn("permanent HTTP 403", message)
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", message)
        self.assertNotIn(service_key, message)
        self.assertNotIn(encoded_key, message)


class FormatAndPlanningTests(unittest.TestCase):
    def test_current_endpoint_formats_are_declared(self) -> None:
        self.assertEqual(ENDPOINTS["results"].service, "API227")
        self.assertEqual(
            ENDPOINTS["results"].path,
            "racedetailresult/getracedetailresult",
        )
        self.assertEqual(ENDPOINTS["results"].response_format, "xml")
        self.assertEqual(ENDPOINTS["race_record"].service, "API4_3")
        self.assertEqual(ENDPOINTS["race_record"].response_format, "xml")
        self.assertTrue(all(
            endpoint.response_format == "json"
            for name, endpoint in ENDPOINTS.items()
            if name not in {"results", "race_record"}
        ))

    def test_raw_extension_follows_response_format(self) -> None:
        self.assertTrue(RequestUnit("race_record", 1, "202001").raw_page_relative_path(1).endswith(".xml"))
        self.assertTrue(RequestUnit("results", 1, "202001").raw_page_relative_path(1).endswith(".xml"))
        self.assertTrue(RequestUnit("single", 1, "202001").raw_page_relative_path(1).endswith(".json"))

    def test_pilot_has_eight_services_and_864_reserved_calls(self) -> None:
        units = build_units(2020, 2021, (1, 2, 3), tuple(ENDPOINTS))
        self.assertEqual(len(units), 792)
        calls = estimate_calls(units)
        self.assertEqual(set(calls), {endpoint.service for endpoint in ENDPOINTS.values()})
        self.assertEqual(sum(calls.values()), 864)

    def test_every_service_uses_3000_daily_limit(self) -> None:
        units = [RequestUnit("single", 1, "202001")]
        result = check_budget(units, used={"API28_1": 2_999})
        self.assertFalse(result[0].allowed)
        self.assertTrue(all(endpoint.daily_limit == 3_000 for endpoint in ENDPOINTS.values()))


class ProbeTests(unittest.TestCase):
    def test_probe_fetches_one_page_and_never_prints_service_key(self) -> None:
        raw = b'{"safe":true}'
        page = Page(1, 123, [{"id": 1}], raw, "json")
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"PROBE_TEST_KEY": "secret-value"}),
            patch("kra_data.probe.KRAClient.fetch_page", return_value=page) as fetch,
            redirect_stdout(output),
        ):
            result = probe_main([
                "--endpoint", "single", "--meet", "1", "--month", "202001",
                "--num-rows", "10", "--service-key-env", "PROBE_TEST_KEY",
            ])
        self.assertEqual(result, 0)
        fetch.assert_called_once()
        report = json.loads(output.getvalue())
        self.assertEqual(report["response"]["total_count"], 123)
        self.assertEqual(report["response"]["row_count"], 1)
        self.assertNotIn("secret-value", output.getvalue())


class ValidationTests(unittest.TestCase):
    def test_duplicate_rows_fail_even_when_total_count_matches(self) -> None:
        row = {"meet": 1, "rcDate": 20200104, "rcNo": 1}
        pages = [Page(1, 2, [row]), Page(2, 2, [row])]
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            validate_pages(pages)

    def test_missing_rows_fail(self) -> None:
        with self.assertRaisesRegex(ValidationError, "mismatch"):
            validate_pages([Page(1, 2, [{"id": 1}])])


class StorageAndResumeTests(unittest.TestCase):
    def test_raw_file_is_byte_for_byte_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            first = write_immutable_bytes(path, b'{ "value": 1 }\n')
            self.assertEqual(first, write_immutable_bytes(path, b'{ "value": 1 }\n'))
            with self.assertRaises(FileExistsError):
                write_immutable_bytes(path, b'{"value":1}\n')

    def test_completed_unit_is_skipped_and_raw_is_exact(self) -> None:
        class FakeClient:
            calls = 0
            def collect_unit(self, unit, num_rows=100_000, on_page=None):
                self.calls += 1
                page = json_page(1, 1, [{"id": unit.key}])
                if on_page is not None:
                    on_page(page)
                return [page]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unit = RequestUnit("single", 1, "202001")
            client = FakeClient()
            self.assertEqual(collect_units(client, [unit], output), (1, 0))
            self.assertEqual(collect_units(client, [unit], output), (0, 1))
            record = Ledger(output / "ledger.json").data["units"][unit.key]
            raw_file = output / record["raw_files"][0]["path"]
            self.assertEqual(raw_file.read_bytes(), json_page(1, 1, [{"id": unit.key}]).raw_body)

    def test_cli_budget_selection_starts_after_completed_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            Ledger(output / "ledger.json").update(RequestUnit("single", 1, "202001").key, "complete")
            with self.assertRaisesRegex(SystemExit, "required secret"):
                collect_main([
                    "--start-year", "2020", "--end-year", "2020", "--endpoints", "single",
                    "--meets", "1", "--max-units", "1", "--output", str(output),
                    "--service-key-env", "INTENTIONALLY_MISSING_KEY",
                ])

    def test_audit_detects_raw_corruption(self) -> None:
        class FakeClient:
            def collect_unit(self, unit, num_rows=100_000, on_page=None):
                page = json_page(1, 1, [{"id": unit.key}])
                if on_page is not None:
                    on_page(page)
                return [page]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unit = RequestUnit("single", 1, "202001")
            collect_units(FakeClient(), [unit], output)
            self.assertTrue(audit_output(output)["passed"])
            record = Ledger(output / "ledger.json").data["units"][unit.key]
            (output / record["raw_files"][0]["path"]).write_bytes(b"{}")
            report = audit_output(output)
            self.assertFalse(report["passed"])
            self.assertIn("checksum mismatch", report["errors"][0])

    def test_partial_page_raw_bytes_are_preserved_after_failure(self) -> None:
        class FailingClient:
            def collect_unit(self, unit, num_rows=100_000, on_page=None):
                first = json_page(1, 2, [{"id": 1}])
                if on_page is not None:
                    on_page(first)
                raise RuntimeError("second page failed")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unit = RequestUnit("single", 1, "202001")
            with self.assertRaisesRegex(RuntimeError, "second page"):
                collect_units(FailingClient(), [unit], output)
            record = Ledger(output / "ledger.json").data["units"][unit.key]
            self.assertEqual(record["state"], "failed")
            self.assertEqual(record["partial_page_count"], 1)
            self.assertTrue((output / record["partial_raw_paths"][0]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
