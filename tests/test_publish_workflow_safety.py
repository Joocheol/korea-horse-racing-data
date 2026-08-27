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

    def test_app_folder_api_paths_are_relative_to_kra_data_root(self) -> None:
        self.assertIn("research_root = '/research'", self.workflow)
        self.assertIn("canonical = f'{research_root}/2016-2025'", self.workflow)
        self.assertNotIn("canonical = '/앱/kra-data", self.workflow)

    def test_first_publish_handles_an_empty_app_folder(self) -> None:
        self.assertIn("if not path_exists(research_root):", self.workflow)
        self.assertIn("if path_exists(canonical):", self.workflow)
        self.assertIn("promotion['rollback'] = 'not_required'", self.workflow)
        self.assertIn("promotion['backup_cleanup'] = 'not_required'", self.workflow)

    def test_failed_canonical_is_quarantined_before_backup_restore(self) -> None:
        quarantine = self.workflow.index("move_wait(canonical, failed)")
        restore = self.workflow.index("move_wait(backup, canonical)", quarantine)
        self.assertLess(quarantine, restore)
        self.assertIn("if path_exists(canonical):", self.workflow)


if __name__ == "__main__":
    unittest.main()
