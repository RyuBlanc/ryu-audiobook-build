from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.core.project import Project


class ProjectTrashTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = self.root / "Library"
        self.app = self.root / "app"
        self.library.mkdir()
        self.app.mkdir()
        self.app_root_patch = patch("app.core.project_trash.app_root", return_value=self.app)
        self.library_root_patch = patch("app.core.project_trash.library_root", return_value=self.library)
        self.app_root_patch.start()
        self.library_root_patch.start()
        self.addCleanup(self.app_root_patch.stop)
        self.addCleanup(self.library_root_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def _make_project(self):
        folder = self.library / "Novel Vol 1"
        project = Project(
            "Novel Vol 1",
            folder,
            None,
            [Chapter(1, "Chapter One", "Hello, world.")],
        )
        project.save()
        (folder / "generated.m4b").write_bytes(b"audio")
        (folder / "state.json").write_text(json.dumps({
            "pronunciation_dictionary": [
                {"written": "Akeno Himejima", "spoken": "Ah-keh-no", "enabled": True, "source": "manual"}
            ],
            "pronunciation_dictionary_version": 2,
        }), encoding="utf-8")
        return project

    def test_trash_removes_from_active_library_but_keeps_chapters_audio_and_pronunciation_for_restore(self):
        from app.core.project_trash import trash_project, list_trashed_projects, restore_project

        project = self._make_project()
        original_folder = project.folder
        entry = trash_project(project)
        self.assertFalse(original_folder.exists())
        self.assertEqual(len(list_trashed_projects()), 1)
        manifest = list_trashed_projects()[0]
        moved_folder = Path(manifest["project_folder"])
        self.assertTrue((moved_folder / "chapters.json").exists())
        self.assertTrue((moved_folder / "generated.m4b").exists())
        state = json.loads((moved_folder / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["pronunciation_dictionary"][0]["written"], "Akeno Himejima")

        restored = restore_project(entry)
        self.assertTrue(restored.exists())
        restored_state = json.loads((restored / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(restored_state["pronunciation_dictionary"][0]["spoken"], "Ah-keh-no")
        events = (self.app / "History" / "project-events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["event"] for line in events], ["project_trashed", "project_restored"])

    def test_restore_chooses_non_destructive_destination_when_title_is_reused(self):
        from app.core.project_trash import trash_project, restore_project

        project = self._make_project()
        entry = trash_project(project)
        (self.library / "Novel Vol 1").mkdir()
        restored = restore_project(entry)
        self.assertEqual(restored.name, "Novel Vol 1 (restored 2)")
        self.assertTrue((restored / "chapters.json").exists())

    def test_permanent_purge_is_limited_to_managed_trash(self):
        from app.core.project_trash import trash_project, purge_trashed_project

        project = self._make_project()
        entry = trash_project(project)
        purge_trashed_project(entry)
        self.assertFalse(entry.exists())
        events = (self.app / "History" / "project-events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["event"] for line in events], ["project_trashed", "project_purged"])

    def test_trash_refuses_project_outside_library(self):
        from app.core.project_trash import trash_project

        external = self.root / "external"
        external.mkdir()
        project = Project("External", external, None, [])
        with self.assertRaises(ValueError):
            trash_project(project)
        self.assertTrue(external.exists())


if __name__ == "__main__":
    unittest.main()
