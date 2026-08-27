from __future__ import annotations

import unittest
from itertools import combinations, permutations

from kra_data.provider_recheck import (
    analyze_2019_dusu,
    analyze_2023_placeholders,
    analyze_2025_gap,
    build_recheck_summary,
)


class ProviderRecheckTests(unittest.TestCase):
    @staticmethod
    def _complete_2025_case():
        horse_counts = {
            2: [9, 10, 10, 10, 10, 10, 10, 10],
            3: [12, 12, 12, 12, 12, 12, 12, 12],
        }
        entries = {}
        groups = {}
        for meet, counts in horse_counts.items():
            entries[meet] = []
            groups[meet] = {
                "single": [],
                "double-qnl": [],
                "double-exa": [],
                "double-qpl": [],
            }
            for race_no, count in enumerate(counts, start=1):
                horses = list(range(1, count + 1))
                entries[meet].extend(
                    {"rcNo": race_no, "chulNo": horse} for horse in horses
                )
                for pool in ("단승식", "연승식"):
                    groups[meet]["single"].extend(
                        {"rcNo": race_no, "pool": pool, "chulNo": horse}
                        for horse in horses
                    )
                for first, second in combinations(horses, 2):
                    groups[meet]["double-qnl"].append(
                        {
                            "rcNo": race_no,
                            "pool": "복승식",
                            "chulNo1": first,
                            "chulNo2": second,
                        }
                    )
                    groups[meet]["double-qpl"].append(
                        {
                            "rcNo": race_no,
                            "pool": "복연승식",
                            "chulNo1": first,
                            "chulNo2": second,
                        }
                    )
                groups[meet]["double-exa"].extend(
                    {
                        "rcNo": race_no,
                        "pool": "쌍승식",
                        "chulNo1": first,
                        "chulNo2": second,
                    }
                    for first, second in permutations(horses, 2)
                )
        return groups, entries, {2: [], 3: []}

    def test_2025_gap_requires_expected_total_and_all_races(self) -> None:
        groups, entries, results = self._complete_2025_case()
        self.assertTrue(analyze_2025_gap(groups, entries, results)["resolved"])

    def test_2025_gap_rejects_missing_key_hidden_by_duplicate(self) -> None:
        groups, entries, results = self._complete_2025_case()
        rows = groups[2]["double-qnl"]
        rows[-1] = dict(rows[0])
        report = analyze_2025_gap(groups, entries, results)
        group = report["meets"]["2"]["groups"]["double-qnl"]
        self.assertTrue(report["meets"]["2"]["row_total_matches"])
        self.assertEqual(group["duplicate_key_count"], 1)
        self.assertEqual(group["missing_key_count"], 1)
        self.assertFalse(group["exact_key_set_matches"])
        self.assertFalse(report["resolved"])

    def test_2025_gap_excludes_documented_pre_start_withdrawal(self) -> None:
        groups, entries, results = self._complete_2025_case()
        entries[2].append({"rcNo": 1, "chulNo": 10})
        results[2].append({"rcNo": 1, "chulNo": 10, "differ": "출전제외"})
        report = analyze_2025_gap(groups, entries, results)
        self.assertEqual(report["meets"]["2"]["pre_start_withdrawal_count"], 1)
        self.assertTrue(report["resolved"])

    def test_2023_placeholders_are_detected_against_entries(self) -> None:
        entries = [{"rcNo": 1, "chulNo": 1}, {"rcNo": 1, "chulNo": 2}]
        single = [
            {"rcNo": 1, "chulNo": 1, "pool": "단승식", "odds": 2.0},
            {"rcNo": 1, "chulNo": 3, "pool": "단승식", "odds": 9999.9},
        ]
        report = analyze_2023_placeholders(entries, single)
        self.assertEqual(report["invalid_row_count"], 1)
        self.assertEqual(report["out_of_entry_on_actual_race_count"], 1)
        self.assertEqual(report["out_of_entry_by_race"], {1: 1})
        self.assertEqual(report["phantom_race_row_count"], 0)
        self.assertFalse(report["resolved"])

    def test_2023_phantom_races_are_separate_from_out_of_entry_rows(self) -> None:
        entries = [{"rcNo": 1, "chulNo": 1}]
        single = [
            {"rcNo": 1, "chulNo": 1, "pool": "단승식", "odds": 2.0},
            {"rcNo": 9, "chulNo": 1, "pool": "단승식", "odds": 9999.9},
        ]
        report = analyze_2023_placeholders(entries, single)
        self.assertEqual(report["entry_races"], [1])
        self.assertEqual(report["single_response_races"], [1, 9])
        self.assertEqual(report["out_of_entry_on_actual_race_count"], 0)
        self.assertEqual(report["phantom_race_row_count"], 1)
        self.assertEqual(report["phantom_race_by_race"], {9: 1})

    def test_2019_dusu_requires_ten_rows_and_value_ten(self) -> None:
        rows = [{"rcNo": 6, "chulNo": value, "dusu": 10} for value in range(1, 11)]
        self.assertTrue(analyze_2019_dusu(rows)["resolved"])
        rows[0]["dusu"] = 9
        self.assertFalse(analyze_2019_dusu(rows)["resolved"])

    def test_canonical_permission_requires_both_explicit_gates(self) -> None:
        cases = {"a": {"resolved": True}, "b": {"resolved": True}}
        self.assertFalse(build_recheck_summary(cases, [])["canonical_update_allowed"])
        self.assertTrue(
            build_recheck_summary(
                cases,
                [],
                exact_key_value_comparison_passed=True,
            )["canonical_update_allowed"]
        )
        cases["b"]["resolved"] = False
        self.assertFalse(
            build_recheck_summary(
                cases,
                [],
                exact_key_value_comparison_passed=True,
            )["canonical_update_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
