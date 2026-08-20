from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kra_data.cli import main as collect_main
from kra_data.client import Page
from kra_data.config import ENDPOINTS
from kra_data.ledger import Ledger
from kra_data.planning import (
    build_monthly_units,
    build_result_units,
    build_units,
    discover_result_dates,
    race_record_coverage_complete,
)
from kra_data.preflight import estimate_calls


class RaceDayPlanningTests(unittest.TestCase):
    def test_monthly_phase_excludes_api227(self) -> None:
        units = build_monthly_units(2020, 2021, (1, 2, 3), tuple(ENDPOINTS))
        self.assertEqual(len(units), 720)
        self.assertFalse(any(unit.endpoint == "results" for unit in units))
        calls = estimate_calls(units)
        self.assertNotIn("API227", calls)
        self.assertEqual(sum(calls.values()), 792)

    def test_discovery_deduplicates_race_dates_and_builds_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            ledger = Ledger(output / "ledger.json")
            expected = build_units(2020, 2020, (1,), ("race_record",))
            for unit in expected:
                staged = output / "staged" / unit.staged_relative_path
                staged.parent.mkdir(parents=True, exist_ok=True)
                rows = []
                if unit.month == "202001":
                    rows = [
                        {"rcDate": "20200104", "rcNo": "1"},
                        {"rcDate": "20200104", "rcNo": "2"},
                    ]
                elif unit.month == "202002":
                    rows = [{"rcDate": "2020-02-01", "rcNo": "1"}]
                staged.write_text(
                    "".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8",
                )
                ledger.update(unit.key, "complete")

            self.assertTrue(race_record_coverage_complete(output, 2020, 2020, (1,)))
            dates = discover_result_dates(output, 2020, 2020, (1,))
            self.assertEqual(dates, ((1, "20200104"), (1, "20200201")))

            result_units = build_result_units(2020, 2020, (1,), dates)
            self.assertEqual(len(result_units), 2)
            self.assertEqual(
                {unit.key for unit in result_units},
                {"20200104:m1:results:-", "20200201:m1:results:-"},
            )

    def test_incomplete_race_record_coverage_blocks_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(race_record_coverage_complete(output, 2020, 2020, (1,)))
            with self.assertRaisesRegex(ValueError, "coverage is incomplete"):
                discover_result_dates(output, 2020, 2020, (1,))

    def test_cli_collects_monthly_phase_then_only_discovered_api227_dates(self) -> None:
        class FakeClient:
            calls: list[str] = []

            def __init__(self, service_key: str):
                self.service_key = service_key

            def collect_unit(self, unit, num_rows=100_000, on_page=None):
                self.calls.append(unit.key)
                if unit.endpoint == "race_record" and unit.month == "202001":
                    rows = [
                        {"rcDate": "20200104", "rcNo": "1", "chulNo": "1"},
                        {"rcDate": "20200104", "rcNo": "1", "chulNo": "2"},
                    ]
                elif unit.endpoint == "results":
                    rows = [
                        {"rcDate": unit.race_date, "rcNo": "1", "chulNo": "1"},
                        {"rcDate": unit.race_date, "rcNo": "1", "chulNo": "2"},
                    ]
                else:
                    rows = []
                page = Page(
                    page_no=1,
                    total_count=len(rows),
                    rows=rows,
                    raw_body=b"<response />",
                    response_format="xml",
                )
                if on_page is not None:
                    on_page(page)
                return [page]

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            FakeClient.calls = []
            with (
                patch.dict(os.environ, {"RACE_DAY_TEST_KEY": "secret-value"}),
                patch("kra_data.cli.KRAClient", FakeClient),
                redirect_stdout(output),
            ):
                status = collect_main([
                    "--start-year", "2020",
                    "--end-year", "2020",
                    "--meets", "1",
                    "--endpoints", "race_record,results",
                    "--output", directory,
                    "--service-key-env", "RACE_DAY_TEST_KEY",
                ])

            self.assertEqual(status, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["phase1_processed"], 12)
            self.assertEqual(report["phase2_processed"], 1)
            self.assertEqual(report["phase2_selected_units"], 1)
            self.assertEqual(report["result_dates_discovered"], 1)
            self.assertFalse(report["results_deferred"])
            self.assertEqual(len(report["phase2_budget"]), 1)
            api227_budget = report["phase2_budget"][0]
            self.assertEqual(api227_budget["service"], "API227")
            self.assertEqual(api227_budget["estimated_calls"], 1)
            self.assertEqual(api227_budget["safety_margin"], 1)
            self.assertEqual(api227_budget["daily_limit"], 3000)
            self.assertTrue(api227_budget["allowed"])
            result_calls = [key for key in FakeClient.calls if ":results:" in key]
            self.assertEqual(result_calls, ["20200104:m1:results:-"])


if __name__ == "__main__":
    unittest.main()
