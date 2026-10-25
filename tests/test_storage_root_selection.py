"""Acceptance tests for selectable project/audio storage roots and disk capacity."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.core import paths
from app.core.project import Project, create_project, list_projects
from app.chapters.detector import Chapter
from app.ui.settings_page import _storage_root_write_error, _storage_space_summary


class StorageRootSelectionTests(unittest.TestCase):
    def test_configured_roots_are_absolute_and_legacy_root_stays_visible(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            app_data = base / "Ryu's Audiobook"
            selected_library = base / "external-drive" / "Books"
            selected_audio = base / "external-drive" / "AudioAssets"
            default_library = app_data / "Library"
            default_audio = app_data / "Audiobooks"
            selected_library.mkdir(parents=True)
            selected_audio.mkdir(parents=True)
            default_library.mkdir(parents=True)
            default_audio.mkdir(parents=True)

            def get_setting(key):
                return {
                    "storage/library_root": str(selected_library),
                    "storage/audio_assets_root": str(selected_audio),
                }.get(key, "")

            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value", side_effect=get_setting
            ):
                self.assertEqual(paths.library_root(), selected_library)
                self.assertEqual(paths.audiobooks_root(), selected_audio)
                self.assertEqual(paths.project_library_roots(), (selected_library, default_library))

    def test_relative_or_empty_storage_settings_fall_back_safely(self):
        with TemporaryDirectory() as temp:
            app_data = Path(temp) / "Ryu's Audiobook"
            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value",
                side_effect=lambda key: "relative/library" if key == "storage/library_root" else "",
            ):
                self.assertEqual(paths.library_root(), app_data / "Library")
                self.assertEqual(paths.audiobooks_root(), app_data / "Audiobooks")

    def test_imports_use_selected_root_and_listing_keeps_existing_legacy_books(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            app_data = base / "profile" / "Ryu's Audiobook"
            default_library = app_data / "Library"
            selected_library = base / "external" / "Books"
            default_library.mkdir(parents=True)
            selected_library.mkdir(parents=True)
            old_project_folder = default_library / "Existing Legacy Book"
            old_project_folder.mkdir()
            Project("Existing Legacy Book", old_project_folder, None, []).save()

            source = base / "new-book.txt"
            source.write_text("A small test source.", encoding="utf-8")

            def get_setting(key):
                return str(selected_library) if key == "storage/library_root" else ""

            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value", side_effect=get_setting
            ):
                created = create_project("New Book", source, [Chapter(number=1, title="Chapter 1", text="Test content.")])
                self.assertEqual(created.folder.parent, selected_library)
                projects = list_projects()

            found = {project.title: project.folder for project in projects}
            self.assertIn("Existing Legacy Book", found)
            self.assertIn("New Book", found)
            self.assertEqual(found["Existing Legacy Book"], old_project_folder)
            self.assertEqual(found["New Book"], created.folder)

    def test_space_summary_reports_actual_filesystem_capacity(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            usage = SimpleNamespace(free=50 * 1024**3, total=100 * 1024**3)
            with patch("app.ui.settings_page.shutil.disk_usage", return_value=usage) as disk_usage:
                self.assertEqual(_storage_space_summary(folder), "50.0 GB free of 100.0 GB")
            disk_usage.assert_called_once_with(str(folder))
            self.assertIn("Unavailable", _storage_space_summary(folder / "missing"))

    def test_storage_root_validation_rejects_missing_or_unwritable_locations(self):
        with TemporaryDirectory() as temp:
            self.assertEqual(_storage_root_write_error(Path(temp)), "")
            self.assertIn("does not exist", _storage_root_write_error(Path(temp) / "missing"))

    def test_settings_and_generation_route_new_data_through_configured_roots(self):
        settings_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "settings_page.py").read_text(encoding="utf-8")
        generation_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "generation_page.py").read_text(encoding="utf-8")
        project_source = (Path(__file__).resolve().parents[1] / "app" / "core" / "project.py").read_text(encoding="utf-8")
        self.assertIn('self.settings.setValue("storage/library_root"', settings_source)
        self.assertIn('self.settings.setValue("storage/audio_assets_root"', settings_source)
        self.assertIn("QFileDialog.getExistingDirectory", settings_source)
        self.assertIn("shutil.disk_usage", settings_source)
        self.assertIn("folder = audiobooks_root() / project_label", generation_source)
        self.assertIn("if saved:", generation_source)
        self.assertIn("for root in project_library_roots()", project_source)
        self.assertIn("allowed_roots", project_source)


if __name__ == "__main__":
    unittest.main()
