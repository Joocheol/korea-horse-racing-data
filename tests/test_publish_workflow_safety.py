from __future__ import annotations

import unittest
from pathlib import Path


class PublishWorkflowSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "publish-api-canonical-once.yml"
        ).read_text(encoding="utf-8")

    def test_reruns_use_attempt_specific_paths(self) -> None:
        self.assertIn("GITHUB_RUN_ATTEMPT_VALUE: ${{ github.run_attempt }}", self.workflow)
        self.assertIn("{run_id}-{run_attempt}", self.workflow)

    def test_failed_canonical_is_quarantined_before_backup_restore(self) -> None:
        quarantine = self.workflow.index("move_wait(canonical, failed)")
        restore = self.workflow.index("move_wait(backup, canonical)", quarantine)
        self.assertLess(quarantine, restore)
        self.assertIn("if path_exists(canonical):", self.workflow)


if __name__ == "__main__":
    unittest.main()
