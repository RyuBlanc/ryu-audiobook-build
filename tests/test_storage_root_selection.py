"""Acceptance tests for selectable project/audio storage roots and disk capacity."""
from pathlib import Path
import os
import subprocess
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

    def test_model_runtime_cache_and_temporary_roots_are_independently_configurable(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            app_data = base / "Ryu's Audiobook"
            selected = {
                "storage/models_root": str(base / "drive-a" / "Models"),
                "storage/runtime_root": str(base / "drive-b" / "Runtimes"),
                "storage/model_cache_root": str(base / "drive-c" / "ModelCache"),
                "storage/temporary_root": str(base / "drive-d" / "Temp"),
            }
            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value", side_effect=lambda key: selected.get(key, "")
            ):
                self.assertEqual(paths.models_root(), Path(selected["storage/models_root"]))
                self.assertEqual(paths.runtimes_root(), Path(selected["storage/runtime_root"]))
                self.assertEqual(paths.model_cache_root(), Path(selected["storage/model_cache_root"]))
                self.assertEqual(paths.temporary_root(), Path(selected["storage/temporary_root"]))

    @unittest.skipUnless(os.name == "nt", "Windows drive-letter disconnect simulation")
    def test_windows_subst_drive_disconnect_and_reconnect_preserves_root_availability(self):
        from app.tts.model_registry import _storage_location_available

        with TemporaryDirectory() as temporary:
            letter = next(
                (value for value in "ZYXWVUTSRQPONMLKJIHGFED"
                 if not Path(value + ":\\").exists()),
                None,
            )
            if letter is None:
                self.skipTest("No unused drive letter is available for the Windows disconnect simulation.")
            drive = letter + ":"
            root = Path(drive + "\\Models")
            mapped = False
            try:
                try:
                    subprocess.run(["subst", drive, temporary], check=True, capture_output=True, text=True)
                except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                    self.skipTest("Windows SUBST drive mapping is unavailable: " + str(exc))
                mapped = True
                root.mkdir(parents=True, exist_ok=True)
                self.assertTrue(_storage_location_available(root))
                subprocess.run(["subst", drive, "/D"], check=True, capture_output=True, text=True)
                mapped = False
                self.assertFalse(_storage_location_available(root))
                subprocess.run(["subst", drive, temporary], check=True, capture_output=True, text=True)
                mapped = True
                self.assertTrue(_storage_location_available(root))
            finally:
                if mapped:
                    subprocess.run(["subst", drive, "/D"], check=False, capture_output=True, text=True)

    def test_chatterbox_bootstrap_installer_uses_configured_temporary_root(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "tts" / "chatterbox_runtime.py").read_text(encoding="utf-8")
        self.assertIn("temporary_root", source)
        self.assertIn('installer = temporary_root() / "ryu-python-3.11.9-amd64.exe"', source)
        self.assertNotIn('installer = local_app_data / "Temp" / "ryu-python-3.11.9-amd64.exe"', source)

    def test_model_related_defaults_preserve_existing_installation_layout(self):
        with TemporaryDirectory() as temp:
            app_data = Path(temp) / "Ryu's Audiobook"
            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value", return_value=""
            ):
                legacy_models = app_data / "Models"
                self.assertEqual(paths.models_root(), legacy_models)
                self.assertEqual(paths.runtimes_root(), legacy_models)
                self.assertEqual(paths.model_cache_root(), legacy_models / "huggingface")
                self.assertEqual(paths.temporary_root(), app_data / "Temp")

    def test_relative_model_related_roots_fall_back_to_legacy_defaults(self):
        with TemporaryDirectory() as temp:
            app_data = Path(temp) / "Ryu's Audiobook"
            values = {
                "storage/models_root": "relative/models",
                "storage/runtime_root": "relative/runtime",
                "storage/model_cache_root": "relative/cache",
                "storage/temporary_root": "relative/temp",
            }
            with patch("app.core.paths.app_root", return_value=app_data), patch(
                "app.core.paths._setting_value", side_effect=lambda key: values.get(key, "")
            ):
                self.assertEqual(paths.models_root(), app_data / "Models")
                self.assertEqual(paths.runtimes_root(), app_data / "Models")
                self.assertEqual(paths.model_cache_root(), app_data / "Models" / "huggingface")
                self.assertEqual(paths.temporary_root(), app_data / "Temp")

    def test_capacity_summary_reports_used_free_and_total(self):
        from app.ui.settings_page import _storage_capacity_summary
        with TemporaryDirectory() as temp:
            usage = SimpleNamespace(free=50 * 1024**3, total=100 * 1024**3)
            with patch("app.ui.settings_page.shutil.disk_usage", return_value=usage):
                self.assertEqual(_storage_capacity_summary(Path(temp)), "50.0 GB used · 50.0 GB free · 100.0 GB total")
            self.assertIn("Unavailable", _storage_capacity_summary(Path(temp) / "missing"))

    def test_nonempty_storage_root_cannot_be_switched_without_migration(self):
        from app.ui.settings_page import _storage_root_change_error
        with TemporaryDirectory() as temp:
            source = Path(temp) / "Models"
            destination = Path(temp) / "NewModels"
            source.mkdir()
            destination.mkdir()
            (source / "weights.bin").write_bytes(b"model weights")
            self.assertIn("verified copy", _storage_root_change_error(source, destination))
            self.assertEqual(_storage_root_change_error(source, source), "")

    def test_unavailable_storage_root_cannot_be_silently_replaced(self):
        from app.ui.settings_page import _storage_root_change_error
        with TemporaryDirectory() as temp:
            source = Path(temp) / "disconnected-drive" / "Models"
            destination = Path(temp) / "NewModels"
            destination.mkdir()
            self.assertIn("Reconnect its drive", _storage_root_change_error(source, destination))


if __name__ == "__main__":
    unittest.main()
