from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from kra_data.research import build


class ResearchBuilderTests(unittest.TestCase):
    def test_entries_are_deduplicated_by_natural_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "staged"
            month = root / "2016" / "201607" / "meet-1"
            month.mkdir(parents=True)

            race_record = {
                "rcDate": 20160717,
                "meet": "서울",
                "rcNo": 5,
                "chulNo": 6,
                "hrNo": "0029850",
                "rcName": "test",
            }
            entry1 = {
                "rcDate": 20160717,
                "meet": "서울",
                "rcNo": 5,
                "chulNo": 6,
                "hrNo": "0029850",
                "owName": "링크폴로",
            }
            entry2 = dict(entry1, owName="(주)링크폴로")
            result = dict(race_record, ord=1)

            (month / "race_record-all.jsonl").write_text(
                json.dumps(race_record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (month / "entries-all.jsonl").write_text(
                json.dumps(entry1, ensure_ascii=False)
                + "\n"
                + json.dumps(entry2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            results = month / "results-all"
            results.mkdir()
            (results / "date-20160717.jsonl").write_text(
                json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
            )

            output = Path(directory) / "research"
            manifest = build([root], output)

            tables = manifest["tables"]
            self.assertEqual(tables["entries_rows"], 1)
            self.assertEqual(tables["results_rows"], 1)
            self.assertEqual(tables["entries_source_duplicate_rows_removed"], 1)
            self.assertEqual(tables["entries_source_conflicting_duplicate_keys"], 1)

            with gzip.open(output / "entries.jsonl.gz", "rt", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["race_id"], "20160717-1-05")
            self.assertEqual(rows[0]["meet"], 1)
            self.assertEqual(rows[0]["owName"], "링크폴로")


if __name__ == "__main__":
    unittest.main()
