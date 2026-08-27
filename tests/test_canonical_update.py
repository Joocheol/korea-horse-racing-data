from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kra_data.canonical_update import compare_provider_to_html, load_html_backfill, natural_key


class CanonicalUpdateTests(unittest.TestCase):
    def test_natural_keys_respect_pool_ordering(self) -> None:
        base = {"race_id": "20251017-2-01"}
        self.assertEqual(
            natural_key({**base, "pool_code": "QNL", "chulNo1": 5, "chulNo2": 2}),
            ("20251017-2-01", "QNL", 2, 5, None),
        )
        self.assertEqual(
            natural_key({**base, "pool_code": "EXA", "chulNo1": 5, "chulNo2": 2}),
            ("20251017-2-01", "EXA", 5, 2, None),
        )

    def test_html_loader_rejects_duplicate_natural_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "html.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("race_id", "pool_code", "h1", "h2", "h3", "odds"))
                writer.writerow(("20251017-2-01", "WIN", 1, "", "", "3.4"))
                writer.writerow(("20251017-2-01", "WIN", 1, "", "", "3.4"))
            with self.assertRaises(ValueError):
                load_html_backfill(path)

    def test_comparison_requires_exact_values_and_keys(self) -> None:
        key = ("20251017-2-01", "WIN", 1, None, None)
        provider = [
            {
                "race_id": "20251017-2-01",
                "pool_code": "WIN",
                "chulNo": 1,
                "odds": 3.4,
            }
        ]
        report = compare_provider_to_html(provider, {key: __import__("decimal").Decimal("3.4")})
        self.assertEqual(report["common_keys"], 1)
        self.assertEqual(report["value_mismatches"], 0)
        self.assertFalse(report["exact_match"])


if __name__ == "__main__":
    unittest.main()
