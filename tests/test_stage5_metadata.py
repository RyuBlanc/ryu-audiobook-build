from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.project import Project
from app.core.state import load_state, save_state
from app.production_metadata import missing_required_metadata_fields, normalize_metadata_text
from app.ui import premium_v2_host as host


class MetadataContractTests(unittest.TestCase):
    def test_empty_saved_metadata_reports_all_nine_non_title_fields(self):
        self.assertEqual(
            missing_required_metadata_fields("Untitled", {}, ""),
            [
                "Author", "Narrator", "Publisher", "Series", "Series Volume",
                "Language", "Release Year", "Genre", "Cover Image",
            ],
        )

    def test_complete_saved_metadata_requires_all_ten_declared_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.png"
            cover.write_bytes(b"valid image fixture")
            state = {
                "author": "A. Writer",
                "publisher": "Example Press",
                "series": "Dragon Library",
                "series_volume": "2",
                "language": "en-US",
                "year": "2026",
                "genre": "Fantasy",
                "cover_path": str(cover),
            }
            self.assertEqual(
                missing_required_metadata_fields("The First Book", state, "Saved Narrator"),
                [],
            )

    def test_each_required_descriptive_field_blocks_completion_when_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.png"
            cover.write_bytes(b"valid image fixture")
            complete = {
                "author": "A. Writer", "publisher": "Example Press",
                "series": "Dragon Library", "series_volume": "2",
                "language": "en", "year": "2026", "genre": "Fantasy",
                "cover_path": str(cover),
            }
            for key, label in (
                ("publisher", "Publisher"), ("series", "Series"),
                ("series_volume", "Series Volume"), ("year", "Release Year"),
                ("cover_path", "Cover Image"),
            ):
                incomplete = dict(complete)
                incomplete[key] = ""
                with self.subTest(field=key):
                    self.assertIn(
                        label,
                        missing_required_metadata_fields("A Book", incomplete, "Narrator"),
                    )

    def test_missing_invalid_or_unsupported_cover_blocks_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.webp"
            cover.write_bytes(b"webp")
            state = {
                "author": "A. Writer", "publisher": "Example Press",
                "series": "Dragon Library", "series_volume": "2",
                "language": "en", "year": "2026", "genre": "Fantasy",
                "cover_path": str(cover),
            }
            self.assertIn(
                "Cover Image",
                missing_required_metadata_fields("A Book", state, "Narrator"),
            )
            state["year"] = "26"
            self.assertIn(
                "Release Year",
                missing_required_metadata_fields("A Book", state, "Narrator"),
            )

    def test_metadata_normalization_removes_nulls_and_collapses_whitespace(self):
        self.assertEqual(normalize_metadata_text("  A\x00  book  title "), "A book title")


class MetadataBridgeHarness:
    _metadata_expected_project = host.PremiumV2Bridge._metadata_expected_project
    _project_metadata_history = host.PremiumV2Bridge._project_metadata_history
    _project_metadata_save = host.PremiumV2Bridge._project_metadata_save
    _project_metadata_cover_choose = host.PremiumV2Bridge._project_metadata_cover_choose

    def __init__(self, project):
        self.project = project

    def _active_project(self):
        return self.project

    def _project_series_name(self, project, state=None):
        saved = state if isinstance(state, dict) else load_state(project.folder)
        return str(saved.get("series_name") or saved.get("series") or project.title)

    def _narrator_series_default_read(self, project, state, series):
        return {"effective_profile_name": "Saved Narrator"}

    def _now(self):
        return "2026-11-02T22:00:00+05:30"


class MetadataBridgeTests(unittest.TestCase):
    def test_metadata_save_persists_fields_and_updates_project_title(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "book-project"
            folder.mkdir()
            project = Project("Old Project Name", folder, None, [])
            project.save()
            save_state(folder, {"author": "Old Author", "language": "en", "genre": "Fiction"})
            bridge = MetadataBridgeHarness(project)

            result = bridge._project_metadata_save({
                "expected_project_folder": str(folder),
                "title": "New Book Title",
                "author": "New Author",
                "publisher": "Example Press",
                "series": "Dragon Library",
                "series_volume": "2",
                "language": "en-GB",
                "year": "2026",
                "genre": "Fantasy; Adventure",
                "cover_path": "",
            })

            self.assertTrue(result["saved"])
            self.assertEqual(Project.load(folder).title, "New Book Title")
            saved = load_state(folder)
            self.assertEqual(saved["author"], "New Author")
            self.assertEqual(saved["publisher"], "Example Press")
            self.assertEqual(saved["series"], "Dragon Library")
            self.assertEqual(saved["series_name"], "Dragon Library")
            self.assertEqual(saved["series_volume"], "2")
            self.assertEqual(saved["language"], "en-GB")
            self.assertEqual(saved["year"], "2026")
            self.assertEqual(saved["genre"], "Fantasy; Adventure")
            self.assertEqual(saved["narrator"], "Saved Narrator")

    def test_metadata_save_rejects_stale_project_identity_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "active"
            folder.mkdir()
            project = Project("Active", folder, None, [])
            project.save()
            save_state(folder, {"author": "Unchanged"})
            bridge = MetadataBridgeHarness(project)

            with self.assertRaisesRegex(RuntimeError, "active project changed"):
                bridge._project_metadata_save({
                    "expected_project_folder": str(Path(temp) / "different-project"),
                    "title": "Wrong Target",
                    "author": "Should Not Persist",
                })

            self.assertEqual(load_state(folder)["author"], "Unchanged")
            self.assertEqual(Project.load(folder).title, "Active")

    def test_metadata_history_uses_saved_project_and_character_library_values(self):
        with tempfile.TemporaryDirectory() as temp:
            current_folder = Path(temp) / "current"
            other_folder = Path(temp) / "other"
            current_folder.mkdir()
            other_folder.mkdir()
            current = Project("Current Book", current_folder, None, [])
            other = Project("Other Book", other_folder, None, [])
            current.save()
            other.save()
            states = {
                current_folder: {"author": "Current Author", "language": "en", "genre": "Fantasy", "series": "Current Series"},
                other_folder: {"author": "Other Author", "publisher": "Other Press", "language": "ja", "genre": "Mystery", "series_volume": "3"},
            }
            bridge = MetadataBridgeHarness(current)
            with patch.object(host, "list_projects", return_value=[current, other]):
                with patch.object(host, "load_state", side_effect=lambda folder: states[Path(folder)]):
                    with patch.object(host, "list_reusable_characters", return_value=[{"series": "Character Library Series"}]):
                        history = bridge._project_metadata_history({"expected_project_folder": str(current_folder)})

            self.assertEqual(history["values"]["author"], ["Current Author", "Other Author"])
            self.assertEqual(history["values"]["publisher"], ["Other Press"])
            self.assertIn("Current Series", history["values"]["series"])
            self.assertIn("Character Library Series", history["values"]["series"])
            self.assertEqual(history["values"]["series_volume"], ["3"])
            self.assertEqual(history["values"]["language"], ["en", "ja"])
            self.assertEqual(history["values"]["genre"], ["Fantasy", "Mystery"])

    def test_metadata_save_rolls_back_project_json_when_state_write_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "book-project"
            folder.mkdir()
            project = Project("Original Title", folder, None, [])
            project.save()
            original_state = {
                "author": "Original Author",
                "language": "en",
                "genre": "Fiction",
                "publisher": "Original Press",
                "year": "2020",
            }
            save_state(folder, original_state)
            original_project_json = project.project_file.read_text(encoding="utf-8")
            original_state_json = (folder / "state.json").read_text(encoding="utf-8")
            bridge = MetadataBridgeHarness(project)
            atomic_write = Project._atomic_write_text

            def fail_state_write(path, content):
                if Path(path).name == "state.json":
                    raise OSError("simulated disk write failure")
                return atomic_write(path, content)

            with patch.object(Project, "_atomic_write_text", side_effect=fail_state_write):
                with self.assertRaisesRegex(OSError, "previous project details were restored"):
                    bridge._project_metadata_save({
                        "expected_project_folder": str(folder),
                        "title": "Partially Applied Title",
                        "author": "New Author",
                        "publisher": "New Press",
                        "series": "",
                        "series_volume": "",
                        "language": "ja",
                        "year": "2026",
                        "genre": "Fantasy",
                        "cover_path": "",
                    })

            self.assertEqual(project.project_file.read_text(encoding="utf-8"), original_project_json)
            self.assertEqual((folder / "state.json").read_text(encoding="utf-8"), original_state_json)
            self.assertEqual(project.title, "Original Title")

    def test_metadata_save_rejects_short_and_long_release_year_values(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "book-project"
            folder.mkdir()
            project = Project("Book", folder, None, [])
            project.save()
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            before = (folder / "state.json").read_text(encoding="utf-8")
            bridge = MetadataBridgeHarness(project)
            for invalid_year in ("26", "20265"):
                with self.subTest(year=invalid_year):
                    with self.assertRaisesRegex(ValueError, "four-digit year"):
                        bridge._project_metadata_save({
                            "expected_project_folder": str(folder),
                            "title": "Book",
                            "author": "Author",
                            "language": "en",
                            "genre": "Fantasy",
                            "year": invalid_year,
                            "cover_path": "",
                        })
            self.assertEqual((folder / "state.json").read_text(encoding="utf-8"), before)

    def test_cover_is_saved_project_locally_and_survives_project_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "book-project"
            folder.mkdir()
            project = Project("Book", folder, None, [])
            project.save()
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            external_cover = root / "cover.png"
            external_cover.write_bytes(b"valid test cover bytes")
            bridge = MetadataBridgeHarness(project)
            class ValidImage:
                def isNull(self):
                    return False
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ValidImage()
                def errorString(self):
                    return ""

            with patch.object(host, "QImageReader", Reader):
                result = bridge._project_metadata_save({
                    "expected_project_folder": str(folder),
                    "title": "Book",
                    "author": "Author",
                    "publisher": "",
                    "series": "",
                    "series_volume": "",
                    "language": "en",
                    "year": "2026",
                    "genre": "Fantasy",
                    "cover_path": str(external_cover),
                })
            saved = load_state(folder)
            persisted_cover = Path(saved["cover_path"])
            self.assertTrue(result["saved"])
            self.assertTrue(persisted_cover.is_file())
            self.assertEqual(persisted_cover.parent, (folder / "assets").resolve())
            self.assertEqual(Project.load(folder).title, "Book")
            self.assertEqual(persisted_cover.read_bytes(), external_cover.read_bytes())

    def test_cover_picker_validates_and_returns_source_without_persisting_early(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "book-project"
            folder.mkdir()
            project = Project("Book", folder, None, [])
            project.save()
            source_cover = Path(temp) / "cover.png"
            source_cover.write_bytes(b"image test")
            bridge = MetadataBridgeHarness(project)
            class ValidImage:
                def isNull(self):
                    return False
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ValidImage()
                def errorString(self):
                    return ""

            with patch.object(host.QFileDialog, "getOpenFileName", return_value=(str(source_cover), "Images")):
                with patch.object(host, "QImageReader", Reader):
                    with patch.object(host, "persist_project_cover") as persist:
                        result = bridge._project_metadata_cover_choose({"expected_project_folder": str(folder)})
            self.assertFalse(result["cancelled"])
            self.assertEqual(result["cover_path"], str(source_cover.resolve()))
            self.assertEqual(result["project_folder"], str(folder.resolve()))
            persist.assert_not_called()

    def test_webp_cover_is_converted_to_m4b_compatible_png(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "book-project"
            folder.mkdir()
            project = Project("Book", folder, None, [])
            project.save()
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            external_cover = root / "cover.webp"
            external_cover.write_bytes(b"valid webp input bytes")
            bridge = MetadataBridgeHarness(project)
            class ConvertedImage:
                def isNull(self):
                    return False
                def save(self, path, image_format):
                    self.assert_unused = image_format
                    Path(path).write_bytes(b"converted png data")
                    return image_format == "PNG"
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ConvertedImage()
                def errorString(self):
                    return ""

            with patch.object(host, "QImageReader", Reader):
                with patch.object(host, "persist_project_cover") as persist:
                    result = bridge._project_metadata_save({
                        "expected_project_folder": str(folder),
                        "title": "Book",
                        "author": "Author",
                        "publisher": "",
                        "series": "",
                        "series_volume": "",
                        "language": "en",
                        "year": "2026",
                        "genre": "Fantasy",
                        "cover_path": str(external_cover),
                    })
            saved = load_state(folder)
            cover_path = Path(saved["cover_path"])
            self.assertTrue(result["saved"])
            self.assertEqual(cover_path.suffix, ".png")
            self.assertTrue(cover_path.is_file())
            self.assertEqual(cover_path.read_bytes(), b"converted png data")
            persist.assert_not_called()

    def test_webp_cover_and_metadata_are_restored_when_state_write_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "book-project"
            folder.mkdir()
            project = Project("Original Title", folder, None, [])
            project.save()
            state_file = folder / "state.json"
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            assets = folder / "assets"
            assets.mkdir()
            old_cover = assets / "cover.png"
            old_cover.write_bytes(b"original cover bytes")
            previous_project_json = project.project_file.read_text(encoding="utf-8")
            previous_state_json = state_file.read_text(encoding="utf-8")
            external_cover = root / "replacement.webp"
            external_cover.write_bytes(b"replacement webp bytes")
            bridge = MetadataBridgeHarness(project)
            atomic_write = Project._atomic_write_text

            class ConvertedImage:
                def isNull(self):
                    return False
                def save(self, path, image_format):
                    Path(path).write_bytes(b"replacement converted png")
                    return image_format == "PNG"
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ConvertedImage()
                def errorString(self):
                    return ""

            def fail_state_write(path, content):
                if Path(path).name == "state.json":
                    raise OSError("simulated state write failure")
                return atomic_write(path, content)

            with patch.object(host, "QImageReader", Reader):
                with patch.object(Project, "_atomic_write_text", side_effect=fail_state_write):
                    with self.assertRaisesRegex(OSError, "previous project details were restored"):
                        bridge._project_metadata_save({
                            "expected_project_folder": str(folder),
                            "title": "New Title",
                            "author": "New Author",
                            "publisher": "",
                            "series": "",
                            "series_volume": "",
                            "language": "ja",
                            "year": "2026",
                            "genre": "Fantasy",
                            "cover_path": str(external_cover),
                        })
            self.assertEqual(project.project_file.read_text(encoding="utf-8"), previous_project_json)
            self.assertEqual(state_file.read_text(encoding="utf-8"), previous_state_json)
            self.assertEqual(old_cover.read_bytes(), b"original cover bytes")
            self.assertEqual(project.title, "Original Title")

    def test_webp_cover_is_converted_to_png_for_m4b_embedding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "book-project"
            folder.mkdir()
            project = Project("Book", folder, None, [])
            project.save()
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            source_cover = root / "cover.webp"
            source_cover.write_bytes(b"valid webp bytes")
            bridge = MetadataBridgeHarness(project)
            class ConvertedImage:
                def isNull(self):
                    return False
                def save(self, path, image_format):
                    Path(path).write_bytes(b"converted png bytes")
                    return image_format == "PNG"
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ConvertedImage()
                def errorString(self):
                    return ""

            with patch.object(host, "QImageReader", Reader):
                with patch.object(host, "persist_project_cover") as persist:
                    result = bridge._project_metadata_save({
                        "expected_project_folder": str(folder),
                        "title": "Book",
                        "author": "Author",
                        "publisher": "",
                        "series": "",
                        "series_volume": "",
                        "language": "en",
                        "year": "2026",
                        "genre": "Fantasy",
                        "cover_path": str(source_cover),
                    })

            saved_cover = Path(load_state(folder)["cover_path"])
            self.assertTrue(result["saved"])
            self.assertEqual(saved_cover.suffix, ".png")
            self.assertEqual(saved_cover.read_bytes(), b"converted png bytes")
            persist.assert_not_called()

    def test_failed_metadata_commit_restores_existing_cover_when_converting_webp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "book-project"
            folder.mkdir()
            project = Project("Original Title", folder, None, [])
            project.save()
            state_file = folder / "state.json"
            save_state(folder, {"author": "Author", "language": "en", "genre": "Fantasy"})
            assets = folder / "assets"
            assets.mkdir()
            existing_cover = assets / "cover.png"
            existing_cover.write_bytes(b"original embedded cover")
            original_project = project.project_file.read_text(encoding="utf-8")
            original_state = state_file.read_text(encoding="utf-8")
            source_cover = root / "replacement.webp"
            source_cover.write_bytes(b"replacement webp bytes")
            bridge = MetadataBridgeHarness(project)
            atomic_write = Project._atomic_write_text

            class ConvertedImage:
                def isNull(self):
                    return False
                def save(self, path, image_format):
                    Path(path).write_bytes(b"replacement png bytes")
                    return image_format == "PNG"
            class Reader:
                def __init__(self, path):
                    self.path = path
                def setAutoTransform(self, enabled):
                    self.auto_transform = enabled
                def read(self):
                    return ConvertedImage()
                def errorString(self):
                    return ""

            def fail_state_write(path, content):
                if Path(path).name == "state.json":
                    raise OSError("simulated state write failure")
                return atomic_write(path, content)

            with patch.object(host, "QImageReader", Reader):
                with patch.object(Project, "_atomic_write_text", side_effect=fail_state_write):
                    with self.assertRaisesRegex(OSError, "previous project details were restored"):
                        bridge._project_metadata_save({
                            "expected_project_folder": str(folder),
                            "title": "New Title",
                            "author": "New Author",
                            "publisher": "",
                            "series": "",
                            "series_volume": "",
                            "language": "ja",
                            "year": "2026",
                            "genre": "Fantasy",
                            "cover_path": str(source_cover),
                        })
            self.assertEqual(project.project_file.read_text(encoding="utf-8"), original_project)
            self.assertEqual(state_file.read_text(encoding="utf-8"), original_state)
            self.assertEqual(existing_cover.read_bytes(), b"original embedded cover")
            self.assertEqual(project.title, "Original Title")

    def test_full_generation_is_blocked_when_saved_metadata_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "book"
            folder.mkdir()
            project = SimpleNamespace(
                folder=folder,
                title="Incomplete Book",
                chapters=[SimpleNamespace(number=1, title="Chapter 1", text="Actual chapter text", skip_for_generation=False)],
            )
            profile = SimpleNamespace(name="Saved Narrator", voice_id="narrator-1")
            bridge = SimpleNamespace(
                _assert_no_active_model_lifecycle=Mock(),
                _active_project=Mock(return_value=project),
                _resolve_narrator_for_generation=Mock(return_value=(profile, {"source": "project_override"})),
            )
            with patch.object(host, "load_state", return_value={"background_audio_mode": "off", "language": "en"}):
                with patch("app.audio.library.validate_saved_audio_paths"):
                    with self.assertRaisesRegex(ValueError, "Input Project Details"):
                        host.PremiumV2Bridge._production_generate_book(bridge, {})


class MetadataPremiumV2UiTests(unittest.TestCase):
    def test_production_studio_exposes_metadata_dialog_and_backend_contract(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for marker in (
            'id="openProjectDetails"',
            'id="inputProjectDetailsDialog"',
            'id="metadataSeriesVolume"',
            'id="metadataCoverPath"',
            'id="productionMetadataStatus"',
        ):
            self.assertIn(marker, html)
        for marker in (
            "project.metadata.history",
            "project.metadata.save",
            "project.metadata.cover.choose",
            "renderProductionMetadataGate",
            "metadata_missing_fields",
            "Save or explicitly discard Input Project Details before switching projects.",
            "Project details were saved, but the production summary could not refresh:",
        ):
            self.assertIn(marker, adapter)


if __name__ == "__main__":
    unittest.main()
