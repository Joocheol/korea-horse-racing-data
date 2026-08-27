from __future__ import annotations

import unittest

from kra_data.provider_recheck import (
    analyze_2019_dusu,
    analyze_2023_placeholders,
    analyze_2025_gap,
)


class ProviderRecheckTests(unittest.TestCase):
    def test_2025_gap_requires_expected_total_and_all_races(self) -> None:
        groups = {}
        for meet, total in ((2, 1_562), (3, 2_304)):
            rows = [{"rcNo": race} for race in range(1, 9)]
            rows.extend({"rcNo": 1} for _ in range(total - 8))
            groups[meet] = {
                "single": rows,
                "double-qnl": [{"rcNo": race} for race in range(1, 9)],
                "double-exa": [{"rcNo": race} for race in range(1, 9)],
                "double-qpl": [{"rcNo": race} for race in range(1, 9)],
            }
            groups[meet]["single"] = groups[meet]["single"][: total - 24]
        self.assertTrue(analyze_2025_gap(groups)["resolved"])

    def test_2023_placeholders_are_detected_against_entries(self) -> None:
        entries = [{"rcNo": 1, "chulNo": 1}, {"rcNo": 1, "chulNo": 2}]
        single = [
            {"rcNo": 1, "chulNo": 1, "pool": "단승식", "odds": 2.0},
            {"rcNo": 1, "chulNo": 3, "pool": "단승식", "odds": 9999.9},
        ]
        report = analyze_2023_placeholders(entries, single)
        self.assertEqual(report["invalid_row_count"], 1)
        self.assertFalse(report["resolved"])

    def test_2019_dusu_requires_ten_rows_and_value_ten(self) -> None:
        rows = [{"rcNo": 6, "chulNo": value, "dusu": 10} for value in range(1, 11)]
        self.assertTrue(analyze_2019_dusu(rows)["resolved"])
        rows[0]["dusu"] = 9
        self.assertFalse(analyze_2019_dusu(rows)["resolved"])


if __name__ == "__main__":
    unittest.main()
