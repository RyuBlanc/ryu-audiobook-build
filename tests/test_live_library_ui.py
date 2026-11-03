from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


class LiveUiRegressionTests(unittest.TestCase):
    def test_character_library_has_live_empty_state_and_no_hardcoded_demo_characters(self):
        source = (REPO_ROOT / "app/ui/character_library_page.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn("load_character_library", source)
        self.assertIn("No saved characters found", source)
        self.assertIn("Open Series in Studio", source)
        # No static character records should be present.
        self.assertNotIn("Rias Gremory", source)
        self.assertNotIn("Issei Hyoudou", source)

    def test_library_has_recovery_action_and_uses_reversible_trash_not_immediate_deletion(self):
        source = (REPO_ROOT / "app/ui/library.py").read_text(encoding="utf-8")
        self.assertIn("Deleted Books / Recover", source)
        self.assertIn("trash_project(project)", source)
        self.assertIn("restore_project", source)
        self.assertNotIn("delete_project(project)", source)

    def test_heavy_page_transition_skips_whole_widget_fade(self):
        source = (REPO_ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("whole-widget graphics effect can trigger black flashes", source)
        self.assertIn('("Character Library", "♟")', source)


if __name__ == "__main__":
    unittest.main()

    def test_import_page_uses_worker_progress_and_removes_stale_demo_copy(self):
        source = (REPO_ROOT / "app/ui/import_page.py").read_text(encoding="utf-8")
        workflow = (REPO_ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("show_import_status", source)
        self.assertIn("worker.status.connect(self.import_page.show_import_status)", workflow)
        self.assertIn("load_latest_import", source)
        self.assertNotIn("Continuing That Time", source)
        self.assertNotIn("extract_text(", source)
        self.assertNotIn("detect_chapters(", source)
