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

    def test_matching_crosscheck_passes_and_empty_file_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            self._write_zip(path)
            report = audit_normalized(path)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["totals"]["staged_files"], 3)
        self.assertEqual(report["totals"]["empty_files"], 1)
        self.assertEqual(report["quinella_crosscheck"]["status"], "pass")

    def test_odds_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            self._write_zip(path, mismatch=True)
            report = audit_normalized(path)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["quinella_crosscheck"]["odds_mismatches"], 1)


if __name__ == "__main__":
    unittest.main()
