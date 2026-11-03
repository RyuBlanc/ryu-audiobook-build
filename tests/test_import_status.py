from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class LatestImportStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = self.root / "Library"
        self.settings = self.root / "Settings"
        self.library.mkdir()
        self.settings.mkdir()
        self.patches = [
            patch("app.core.import_status.library_root", return_value=self.library),
            patch("app.core.import_status.settings_root", return_value=self.settings),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.temp.cleanup)

    def _project(self, name="Novel Vol 1"):
        folder = self.library / name
        folder.mkdir()
        (folder / "project.json").write_text(json.dumps({"title": name}), encoding="utf-8")
        (folder / "chapters.json").write_text("[]", encoding="utf-8")
        source = folder / "source" / "novel.epub"
        source.parent.mkdir()
        source.write_bytes(b"book")
        return SimpleNamespace(title=name, folder=folder, source_path=source, chapters=[1, 2, 3])

    def test_latest_import_is_persisted_for_active_project(self):
        from app.core.import_status import record_latest_import, load_latest_import
        project = self._project()
        saved = record_latest_import(project)
        loaded = load_latest_import()
        self.assertEqual(loaded["title"], "Novel Vol 1")
        self.assertEqual(loaded["source_name"], "novel.epub")
        self.assertEqual(saved["chapter_count"], 3)

    def test_deleted_project_clears_recent_import_status(self):
        from app.core.import_status import record_latest_import, load_latest_import, clear_latest_import_for_folder
        project = self._project()
        record_latest_import(project)
        self.assertTrue(clear_latest_import_for_folder(project.folder))
        self.assertIsNone(load_latest_import())

    def test_stale_record_is_removed_after_seven_days(self):
        from app.core.import_status import record_latest_import, load_latest_import, _record_path
        project = self._project()
        record_latest_import(project)
        future = datetime.now(timezone.utc) + timedelta(days=8)
        self.assertIsNone(load_latest_import(now=future))
        self.assertFalse(_record_path().exists())

    def test_record_outside_active_library_is_rejected(self):
        from app.core.import_status import record_latest_import
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "project.json").write_text("{}", encoding="utf-8")
        (outside / "chapters.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            record_latest_import(SimpleNamespace(title="Outside", folder=outside, source_path=None, chapters=[]))


if __name__ == "__main__":
    unittest.main()
