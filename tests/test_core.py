from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kra_data.client import Page, parse_page
from kra_data.audit import audit_output
from kra_data.collector import collect_units
from kra_data.cli import main as collect_main
from kra_data.errors import SchemaError, ValidationError
from kra_data.ledger import Ledger
from kra_data.models import RequestUnit
from kra_data.planning import build_units
from kra_data.preflight import check_budget
from kra_data.storage import write_immutable_json
from kra_data.validation import validate_pages


FIXTURES = Path(__file__).parent / "fixtures"


class ParseTests(unittest.TestCase):
    def test_single_row_is_normalized_to_list(self) -> None:
        payload = json.loads((FIXTURES / "page_one.json").read_text())
        page = parse_page(payload, 1)
        self.assertEqual(page.total_count, 1)
        self.assertEqual(len(page.rows), 1)

    def test_empty_items_are_valid_when_total_is_zero(self) -> None:
        payload = json.loads((FIXTURES / "page_empty.json").read_text())
        page = parse_page(payload, 1)
        self.assertEqual(page.total_count, 0)
        self.assertEqual(page.rows, [])

    def test_schema_drift_fails_closed(self) -> None:
        with self.assertRaises(SchemaError):
            parse_page({"changed": {}}, 1)


class ValidationTests(unittest.TestCase):
    def test_duplicate_rows_fail_even_when_total_count_matches(self) -> None:
        row = {"meet": 1, "rcDate": 20200104, "rcNo": 1}
        pages = [Page(1, 2, [row]), Page(2, 2, [row])]
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            validate_pages(pages)

    def test_missing_rows_fail(self) -> None:
        with self.assertRaisesRegex(ValidationError, "mismatch"):
            validate_pages([Page(1, 2, [{"id": 1}])])

    def test_complete_unique_rows_pass(self) -> None:
        summary = validate_pages([Page(1, 2, [{"id": 1}, {"id": 2}])])
        self.assertEqual(summary.unique_rows, 2)
        self.assertEqual(summary.duplicate_rows, 0)


class StorageAndResumeTests(unittest.TestCase):
    def test_raw_file_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            first = write_immutable_json(path, {"value": 1})
            self.assertEqual(first, write_immutable_json(path, {"value": 1}))
            with self.assertRaises(FileExistsError):
                write_immutable_json(path, {"value": 2})

    def test_completed_unit_is_skipped_on_resume(self) -> None:
        class FakeClient:
            calls = 0

            def collect_unit(self, unit: RequestUnit, num_rows: int = 100_000, on_page=None) -> list[Page]:
                self.calls += 1
                page = Page(1, 1, [{"id": unit.key}])
                if on_page is not None:
                    on_page(page)
                return [page]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unit = RequestUnit("single", 1, "202001")
            client = FakeClient()
            self.assertEqual(collect_units(client, [unit], output), (1, 0))
            self.assertEqual(collect_units(client, [unit], output), (0, 1))
            self.assertEqual(client.calls, 1)
            self.assertEqual(Ledger(output / "ledger.json").state(unit.key), "complete")

    def test_cli_budget_selection_starts_after_completed_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = RequestUnit("single", 1, "202001")
            Ledger(output / "ledger.json").update(first.key, "complete")
            # Missing secret proves preflight reached the next pending batch without calling the API.
            with self.assertRaisesRegex(SystemExit, "required secret"):
                collect_main([
                    "--start-year", "2020", "--end-year", "2020",
                    "--endpoints", "single", "--meets", "1",
                    "--max-units", "1", "--output", str(output),
                    "--service-key-env", "INTENTIONALLY_MISSING_KEY",
                ])

    def test_audit_detects_raw_corruption(self) -> None:
        class FakeClient:
            def collect_unit(self, unit: RequestUnit, num_rows: int = 100_000, on_page=None) -> list[Page]:
                page = Page(1, 1, [{"id": unit.key}])
                if on_page is not None:
                    on_page(page)
                return [page]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unit = RequestUnit("single", 1, "202001")
            collect_units(FakeClient(), [unit], output)
            self.assertTrue(audit_output(output)["passed"])
            raw_path = output / "raw" / unit.relative_path
            raw_path.write_text("{}\n", encoding="utf-8")
            report = audit_output(output)
            self.assertFalse(report["passed"])
            self.assertIn("checksum mismatch", report["errors"][0])

    def test_partial_pages_are_preserved_after_failure(self) -> None:
        class FailingClient:
            def collect_unit(self, unit: RequestUnit, num_rows: int = 100_000, on_page=None) -> list[Page]:
                first = Page(1, 2, [{"id": 1}])
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
            self.assertTrue((output / record["partial_raw_path"]).is_file())


class PlanningTests(unittest.TestCase):
    def test_pilot_unit_count(self) -> None:
        units = build_units(2020, 2021, (1, 2, 3), ("single", "double", "triple", "sales", "entries", "results"))
        # 24 months × 3 meets × (1 + 3 + 2 + 1 + 1 + 1 pools)
        self.assertEqual(len(units), 648)

    def test_sales_limit_is_enforced(self) -> None:
        units = [RequestUnit("sales", 1, f"2020{month:02d}") for month in range(1, 13)]
        result = check_budget(units, used={"sales": 2_990})
        self.assertFalse(result[0].allowed)


if __name__ == "__main__":
    unittest.main()
