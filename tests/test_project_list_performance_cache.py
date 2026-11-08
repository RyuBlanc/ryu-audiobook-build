from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.core import project as project_module
from app.core.project import Project, list_projects


class ProjectListPerformanceCacheTests(unittest.TestCase):
    def setUp(self):
        project_module.invalidate_project_list_cache()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Library"
        self.root.mkdir()
        self.folder = self.root / "Book One"
        Project(
            "Book One",
            self.folder,
            chapters=[Chapter(1, "Chapter One", "Original chapter text.")],
        ).save()
        self.addCleanup(project_module.invalidate_project_list_cache)

    def test_repeated_library_refresh_reuses_parsed_chapter_data(self):
        original_load = Project.load
        with (
            patch.object(project_module, "project_library_roots", return_value=[self.root]),
            patch.object(
                Project, "load",
                side_effect=lambda folder, **kwargs: original_load(folder, **kwargs),
            ) as loader,
        ):
            first = list_projects()
            second = list_projects()

        self.assertEqual(loader.call_count, 1)
        self.assertIs(first[0], second[0])
        self.assertEqual(first[0].chapters[0].text, "Original chapter text.")
        self.assertFalse(loader.call_args.kwargs["migrate_legacy"])

    def test_saved_chapter_change_invalidates_cache_and_returns_fresh_project(self):
        original_load = Project.load
        with (
            patch.object(project_module, "project_library_roots", return_value=[self.root]),
            patch.object(
                Project, "load",
                side_effect=lambda folder, **kwargs: original_load(folder, **kwargs),
            ) as loader,
        ):
            first = list_projects()
            edited = Project.load(self.folder, migrate_legacy=False)
            edited.chapters[0].text = "Updated saved chapter text with a different length."
            edited.save()
            second = list_projects()

        self.assertEqual(loader.call_count, 2)
        self.assertIsNot(first[0], second[0])
        self.assertEqual(second[0].chapters[0].text, "Updated saved chapter text with a different length.")

    def test_deleted_project_is_removed_from_cache_after_root_scan(self):
        with patch.object(project_module, "project_library_roots", return_value=[self.root]):
            self.assertEqual(len(list_projects()), 1)
            shutil.rmtree(self.folder)
            self.assertEqual(list_projects(), [])
        self.assertEqual(project_module._PROJECT_LIST_CACHE, {})


if __name__ == "__main__":
    unittest.main()
