from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from kra_data.normalized_audit import audit_normalized


class NormalizedAuditTests(unittest.TestCase):
    def _write_zip(self, path: Path, *, mismatch: bool = False) -> None:
        qnl = {
            "rcDate": 20250101,
            "meet": "서울",
            "rcNo": 1,
            "chulNo1": 1,
            "chulNo2": 2,
            "odds": 3.4,
            "pool": "복승식",
        }
        cross = {key: value for key, value in qnl.items() if key != "pool"}
        if mismatch:
            cross["odds"] = 3.5
        entry1 = {
            "rcDate": 20160717,
            "meet": "서울",
            "rcNo": 5,
            "chulNo": 6,
            "hrNo": "0029850",
            "owName": "링크폴로",
        }
        entry2 = dict(entry1, owName="(주)링크폴로")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "output/staged/2025/202501/meet-1/double-qnl.jsonl",
                json.dumps(qnl) + "\n",
            )
            archive.writestr(
                "output/staged/2025/202501/meet-1/quinella_crosscheck-all.jsonl",
                json.dumps(cross) + "\n",
            )
            archive.writestr(
                "output/staged/2025/202501/meet-1/results-all/date-20250101.jsonl",
                "",
            )
            archive.writestr(
                "output/staged/2016/201607/meet-1/entries-all.jsonl",
                json.dumps(entry1, ensure_ascii=False)
                + "\n"
                + json.dumps(entry2, ensure_ascii=False)
                + "\n",
            )

    def test_matching_crosscheck_passes_and_empty_file_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            self._write_zip(path)
            report = audit_normalized(path)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["totals"]["staged_files"], 4)
        self.assertEqual(report["totals"]["empty_files"], 1)
        self.assertEqual(report["quinella_crosscheck"]["status"], "pass")
        entries = report["entries_natural_key_duplicates"]
        self.assertEqual(entries["unique_keys"], 1)
        self.assertEqual(entries["duplicate_rows"], 1)
        self.assertEqual(entries["conflicting_duplicate_keys"], 1)

    def test_odds_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            self._write_zip(path, mismatch=True)
            report = audit_normalized(path)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["quinella_crosscheck"]["odds_mismatches"], 1)


if __name__ == "__main__":
    unittest.main()
