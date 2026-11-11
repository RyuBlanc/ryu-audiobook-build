from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
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
                _jobs_lock=threading.RLock(),
                _jobs={},
                _generators={},
            )
            with patch.object(host, "load_state", return_value={"background_audio_mode": "off", "language": "en"}):
                with patch("app.audio.library.validate_saved_audio_paths"):
                    with self.assertRaisesRegex(ValueError, "Input Project Details"):
                        host.PremiumV2Bridge._production_generate_book(bridge, {})


class ProjectSummaryReadinessHarness:
    _project_summary = host.PremiumV2Bridge._project_summary
    _effective_generation_character_rows = host.PremiumV2Bridge._effective_generation_character_rows
    _character_series_for_voice_assignment = staticmethod(
        host.PremiumV2Bridge._character_series_for_voice_assignment
    )

    def _project_series_name(self, project, state=None):
        values = state if isinstance(state, dict) else load_state(project.folder)
        return str(values.get("series") or project.title)

    def _narrator_series_default_read(self, _project, _state, _series):
        return {
            "effective_profile_name": "Saved Narrator",
            "profile_name": "Saved Narrator",
            "profile_available": True,
            "source": "project_override",
        }

    def _unassigned_character_default_read(self):
        return {"profile_name": None, "profile_available": False, "profile": None}


class ProjectSummaryReadinessTests(unittest.TestCase):
    def _project(self, root: Path, *, target: str = ""):
        folder = root / "library" / "saved-book"
        folder.mkdir(parents=True)
        source = root / "source-book.txt"
        source.write_text("Original imported text", encoding="utf-8")
        project = Project(
            "Readiness Book",
            folder,
            source,
            [
                Chapter(1, "Opening", "This chapter can be generated."),
                Chapter(2, "Empty", "  \n "),
                Chapter(3, "Excluded", "This chapter is explicitly excluded.", skip_for_generation=True),
            ],
        )
        project.save()
        cover = folder / "assets" / "cover.png"
        cover.parent.mkdir(parents=True, exist_ok=True)
        cover.write_bytes(b"cover fixture")
        state = {
            "author": "A. Writer",
            "publisher": "Example Press",
            "series": "Example Series",
            "series_volume": "1",
            "language": "en",
            "year": "2026",
            "genre": "Fantasy",
            "cover_path": str(cover),
        }
        if target:
            state["generation_target_path"] = target
        save_state(folder, state)
        return project, state, cover

    def _summary(
        self, project, root: Path, *, writable: bool = True, profiles=None
    ):
        audio_root = root / "AudioBooks"
        audio_root.mkdir(parents=True, exist_ok=True)
        with (
            patch.object(host, "audiobooks_root", return_value=audio_root),
            patch.object(host, "persist_project_cover", side_effect=lambda source, _folder: Path(source).resolve()),
            patch.object(host, "load_profiles", return_value=list(profiles or [])),
            patch.object(host.os, "access", return_value=writable),
        ):
            return ProjectSummaryReadinessHarness()._project_summary(project)

    def test_new_book_reports_usable_default_output_before_first_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _state, _cover = self._project(root)
            summary = self._summary(project, root)

            self.assertIsNone(summary["output_path"])
            self.assertFalse(summary["completed"])
            self.assertTrue(summary["output_configured"])
            self.assertTrue(summary["output_folder_ready"])
            self.assertTrue(summary["output_format_supported"])
            self.assertEqual(Path(summary["output_target_path"]).suffix, ".m4b")
            self.assertEqual(summary["eligible_chapter_count"], 1)
            self.assertEqual(summary["empty_chapter_count"], 1)
            self.assertEqual(summary["excluded_chapter_count"], 1)
            self.assertTrue(summary["metadata_complete"])

    def test_production_readiness_uses_the_canonical_dialogue_passage_index(self):
        from types import SimpleNamespace
        from app.chapters.speaker_segmentation import segment_chapter_speakers
        from app.chapters.assignment_utils import assign_dialogue_to_chapters

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, state, _cover = self._project(root)
            chapter = Chapter(
                1,
                "Opening",
                'The door opened. “Hello there,” Mira said. The room was quiet.',
            )
            project.chapters = [chapter]
            project.save()
            state["characters"] = [{"name": "Mira", "voice_profile": "Mira Voice"}]
            save_state(project.folder, state)
            profiles = [
                SimpleNamespace(name="Mira Voice", voice_id="mira", provider="piper"),
            ]

            pending = self._summary(project, root, profiles=profiles)
            self.assertTrue(pending["dialogue_index_ready"])
            self.assertGreater(pending["dialogue_passage_count"], 0)
            self.assertGreater(pending["pending_dialogue_count"], 0)
            self.assertFalse(pending["dialogue_review_complete"])
            self.assertEqual(pending["configured_character_voice_profile_count"], 1)

            dialogue = next(
                segment for segment in segment_chapter_speakers(chapter)
                if segment.kind != "narration"
            )
            assign_dialogue_to_chapters(
                project.chapters,
                dialogue.text,
                ["Mira"],
                chapter_number=1,
            )
            project.save()

            reviewed = self._summary(project, root, profiles=profiles)
            self.assertTrue(reviewed["dialogue_index_ready"])
            self.assertTrue(reviewed["dialogue_review_complete"])
            self.assertEqual(reviewed["pending_dialogue_count"], 0)
            self.assertGreater(reviewed["assigned_dialogue_count"], 0)
            self.assertEqual(reviewed["configured_character_voice_profile_count"], 1)

    def test_stale_character_profile_references_are_reported_not_counted_as_configured(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, state, _cover = self._project(root)
            project.chapters = [
                Chapter(1, "Opening", '“Hello there,” Mira said.'),
            ]
            project.save()
            state["characters"] = [{"name": "Mira", "voice_profile": "Deleted Voice"}]
            save_state(project.folder, state)

            summary = self._summary(project, root, profiles=[])
            self.assertEqual(summary["configured_character_voice_profile_count"], 0)
            self.assertGreater(summary["character_assignment_issue_count"], 0)
            self.assertFalse(summary["dialogue_review_complete"])

    def test_missing_custom_output_directory_is_ready_when_existing_parent_is_writable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "new-output" / "nested" / "Readiness Book.m4b"
            project, _state, _cover = self._project(root, target=str(target))
            summary = self._summary(project, root)

            self.assertFalse(target.parent.exists())
            self.assertTrue(summary["output_folder_ready"])
            self.assertTrue(summary["output_configured"])
            self.assertTrue(summary["output_format_supported"])

    def test_unsupported_output_format_and_unwritable_parent_are_not_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "Readiness Book.mp3"
            project, _state, _cover = self._project(root, target=str(target))
            unsupported = self._summary(project, root)
            self.assertFalse(unsupported["output_format_supported"])
            self.assertFalse(unsupported["output_configured"])

            supported_target = root / "Readiness Book.m4b"
            save_state(project.folder, {
                "author": "A. Writer", "publisher": "Example Press", "series": "Example Series",
                "series_volume": "1", "language": "en", "year": "2026", "genre": "Fantasy",
                "cover_path": str(project.folder / "assets" / "cover.png"),
                "generation_target_path": str(supported_target),
            })
            unwritable = self._summary(project, root, writable=False)
            self.assertFalse(unwritable["output_folder_ready"])
            self.assertFalse(unwritable["output_configured"])


class ProductionReadinessUiTests(unittest.TestCase):
    def test_dashboard_and_start_button_use_complete_generation_prerequisites(self):
        root = Path(__file__).resolve().parents[1]
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")

        helper_start = adapter.index("function productionGenerationBlockReason(active)")
        helper_end = adapter.index("function renderProductionMetadataGate(active)", helper_start)
        helper = adapter[helper_start:helper_end]
        for marker in (
            "active.metadata_complete !== true",
            "active.narrator_voice_configured !== true",
            "active.narrator_profile_available !== true",
            "active.eligible_chapter_count ?? active.prepared_chapter_count ?? 0",
            "active.output_format_supported !== true",
            "active.output_folder_ready !== true",
            "active.output_configured !== true",
            "active.dialogue_index_ready !== true",
            "active.dialogue_review_complete !== true",
            "active.character_assignment_issue_count",
            "active.pending_dialogue_count",
        ):
            self.assertIn(marker, helper)

        gate_start = adapter.index("function renderProductionMetadataGate(active)")
        gate_end = adapter.index("\n  function populateMetadataHistory", gate_start)
        gate = adapter[gate_start:gate_end]
        self.assertIn("const generationBlockReason = productionGenerationBlockReason(active);", gate)
        self.assertIn("start.disabled = Boolean(generationBlockReason) || audioActive;", gate)

        generation_start = adapter.index("function renderProductionGeneration(")
        generation_end = adapter.index("async function refreshChapterBgm(", generation_start)
        generation = adapter[generation_start:generation_end]
        self.assertIn("const generationBlockReason = productionGenerationBlockReason(project);", generation)
        self.assertIn("fullStart.disabled = anyAudioActive || Boolean(generationBlockReason);", generation)
        self.assertIn("productionGenerationBlockReason(project)", generation)
        self.assertIn("fullStart.title = anyAudioActive", generation)
        self.assertNotIn("fullStart.disabled = anyAudioActive || !metadataComplete;", generation)
        self.assertIn("previewStart.disabled = anyAudioActive;", generation)

        flow_start = adapter.index("function refreshDashboardFlow(project)")
        flow_end = adapter.index("\n  function ", flow_start + 10)
        flow = adapter[flow_start:flow_end]
        for marker in (
            "const metadataComplete = project.metadata_complete === true;",
            "project.eligible_chapter_count ?? project.prepared_chapter_count ?? 0",
            "project.narrator_only_generation === true",
            "project.configured_character_voice_profile_count",
            "const narratorOnlyEligibilityInvalid = narratorOnlyRequested && configuredCharacterVoiceCount > 0;",
            "const charactersReady = !narratorOnlyEligibilityInvalid && (",
            "project.dialogue_index_ready === true",
            "project.dialogue_review_complete === true",
            "project.character_assignment_issue_count",
            "project.narrator_profile_available === true",
            "project.output_folder_ready === true",
            "project.output_format_supported === true",
            "{key:'import', ready:metadataComplete",
            "const canGenerate = chaptersReady && metadataComplete && narratorReady && outputReady && charactersReady;",
        ):
            self.assertIn(marker, flow)
        self.assertNotIn("{key:'import', ready:Boolean(project.source_exists)", flow)
        self.assertIn(
            "0 configured character voice profiles · saved narrator reads all passages",
            flow,
        )
        self.assertNotIn("Narrator-only · character voices bypassed", flow)


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


class ProductionPreviewSaveHarness:
    _production_preview_save = host.PremiumV2Bridge._production_preview_save

    def __init__(self, job):
        self._jobs_lock = threading.RLock()
        self._jobs = {str(job["job_id"]): dict(job)}


class ProductionPreviewSaveTests(unittest.TestCase):
    def _preview_job(self, root: Path):
        preview_root = root / "app" / "Previews"
        preview_root.mkdir(parents=True, exist_ok=True)
        project_folder = root / "library" / "saved-book"
        project_folder.mkdir(parents=True)
        source = preview_root / "production-preview-stable-job.m4a"
        source.write_bytes(b"validated chapter preview bytes" * 128)
        job = {
            "job_id": "stable-preview-job",
            "type": "production-preview",
            "state": "completed",
            "project_folder": str(project_folder.resolve()),
            "current_chapter": 4,
            "current_chapter_id": "stable-chapter-four",
            "result": {"output_path": str(source.resolve())},
        }
        return preview_root, project_folder, source, job

    def test_completed_preview_saves_exact_job_project_and_chapter_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _preview_root, project_folder, source, job = self._preview_job(root)
            bridge = ProductionPreviewSaveHarness(job)
            requested_destination = root / "Downloads" / "saved-preview.wav"
            requested_destination.parent.mkdir(parents=True, exist_ok=True)
            expected_destination = requested_destination.with_suffix(".m4a")
            payload = {
                "job_id": job["job_id"],
                "project_folder": str(project_folder.resolve()),
                "chapter_number": 4,
                "chapter_id": "stable-chapter-four",
                "source_path": str(source.resolve()),
                "suggested_name": "Opening / Chapter Four",
            }

            with (
                patch.object(host, "app_root", return_value=root / "app"),
                patch.object(host.QFileDialog, "getSaveFileName", return_value=(str(requested_destination), "")),
            ):
                result = bridge._production_preview_save(payload)

            self.assertFalse(result["cancelled"])
            self.assertEqual(Path(result["path"]).resolve(), expected_destination.resolve())
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertEqual(result["chapter_number"], 4)
            self.assertEqual(expected_destination.read_bytes(), source.read_bytes())
            self.assertEqual(result["bytes"], source.stat().st_size)

    def test_preview_save_rejects_stale_identity_and_foreign_audio_paths(self):
        mutations = (
            ("job type", lambda job, payload, _root: job.update(type="voice-preview")),
            ("unfinished job", lambda job, payload, _root: job.update(state="running")),
            ("project", lambda job, payload, _root: job.update(project_folder=str(_root / "other-project"))),
            ("chapter number", lambda job, payload, _root: job.update(current_chapter=3)),
            ("chapter id", lambda job, payload, _root: job.update(current_chapter_id="replacement-chapter")),
            ("worker output", lambda job, payload, root: job["result"].update(output_path=str(root / "foreign.m4a"))),
            ("payload source", lambda job, payload, root: payload.update(source_path=str(root / "foreign.m4a"))),
        )
        for label, mutate in mutations:
            with self.subTest(identity=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _preview_root, project_folder, source, original_job = self._preview_job(root)
                job = dict(original_job)
                job["result"] = dict(original_job["result"])
                payload = {
                    "job_id": job["job_id"],
                    "project_folder": str(project_folder.resolve()),
                    "chapter_number": 4,
                    "chapter_id": "stable-chapter-four",
                    "source_path": str(source.resolve()),
                }
                mutate(job, payload, root)
                bridge = ProductionPreviewSaveHarness(job)
                with patch.object(host, "app_root", return_value=root / "app"):
                    with self.assertRaises(ValueError):
                        bridge._production_preview_save(payload)


class ProductionPreviewDispatchHarness:
    _production_preview = host.PremiumV2Bridge._production_preview

    def __init__(self, project, selection, profile):
        self.project = project
        self.selection = selection
        self.profile = profile
        self._active_project = Mock(return_value=project)
        self._project_series_name = Mock(return_value="Saved Series")
        self._narrator_series_default_read = Mock(return_value=selection)
        self._find_profile = Mock(return_value=profile)
        self._voice_preview = Mock(return_value={"job_id": "production-preview-job", "state": "running"})


class ProductionPreviewDispatchTests(unittest.TestCase):
    def _fixture(self, *, narrator_only: bool):
        chapter = SimpleNamespace(
            number=4,
            chapter_id="stable-chapter-four",
            title="The Crossing",
            text="The saved chapter text is authoritative. The bridge is old.",
            skip_for_generation=False,
        )
        project = SimpleNamespace(
            folder=Path("saved-project"),
            title="Saved Production Book",
            chapters=[chapter],
        )
        profile = SimpleNamespace(name="Persisted Narrator Profile", voice_id="persisted-narrator-voice")
        selection = {
            "effective_profile_name": profile.name,
            "profile_available": True,
            "source": "project_override",
        }
        state = {
            "series": "Saved Series",
            "narrator_only_generation": narrator_only,
            "pronunciation_enabled": True,
        }
        return project, chapter, profile, selection, state

    def test_production_preview_uses_saved_narrator_and_forces_final_generation_parity(self):
        for narrator_only in (False, True):
            with self.subTest(narrator_only=narrator_only):
                project, chapter, profile, selection, state = self._fixture(
                    narrator_only=narrator_only,
                )
                bridge = ProductionPreviewDispatchHarness(project, selection, profile)
                caller_payload = {
                    "chapter_number": 4,
                    "chapter_id": chapter.chapter_id,
                    "provider": "caller-controlled-provider",
                    "voice_id": "caller-controlled-voice",
                    "profile_name": "Unsaved UI selection",
                    "text": "Caller text must not replace saved chapter text.",
                    "allow_projectless_preview": True,
                    "_bypass_pronunciation_dictionary": True,
                    "apply_pronunciation_rules": False,
                    "include_sound_design": False,
                }

                with patch.object(host, "load_state", return_value=state):
                    result = bridge._production_preview(caller_payload)

                self.assertEqual(result["job_id"], "production-preview-job")
                bridge._narrator_series_default_read.assert_called_once_with(
                    project, state, "Saved Series",
                )
                preview_payload = bridge._voice_preview.call_args.args[0]
                self.assertEqual(preview_payload["chapter_number"], 4)
                self.assertEqual(preview_payload["chapter_id"], "stable-chapter-four")
                self.assertEqual(preview_payload["profile_name"], profile.name)
                self.assertIs(preview_payload["route_character_cast"], not narrator_only)
                self.assertIs(preview_payload["apply_pronunciation_rules"], True)
                self.assertIs(preview_payload["include_sound_design"], True)
                self.assertIs(preview_payload["_production_preview"], True)
                for forbidden in (
                    "provider", "voice_id", "text", "allow_projectless_preview",
                    "_bypass_pronunciation_dictionary",
                ):
                    self.assertNotIn(forbidden, preview_payload)

    def test_production_preview_rejects_stale_chapter_identity_and_blank_text(self):
        project, chapter, profile, selection, state = self._fixture(narrator_only=False)
        bridge = ProductionPreviewDispatchHarness(project, selection, profile)
        with self.assertRaisesRegex(ValueError, "chapter identity changed"):
            bridge._production_preview({
                "chapter_number": 4,
                "chapter_id": "old-chapter-id",
            })
        bridge._voice_preview.assert_not_called()

        chapter.text = "   "
        with self.assertRaisesRegex(ValueError, "no saved narration text"):
            bridge._production_preview({
                "chapter_number": 4,
                "chapter_id": chapter.chapter_id,
            })
        bridge._voice_preview.assert_not_called()

    def test_production_preview_blocks_missing_or_unavailable_saved_narrator(self):
        project, chapter, profile, selection, state = self._fixture(narrator_only=True)
        for narrator_selection in (
            {"effective_profile_name": "", "profile_available": False},
            {"effective_profile_name": profile.name, "profile_available": False},
        ):
            with self.subTest(selection=narrator_selection):
                bridge = ProductionPreviewDispatchHarness(
                    project, narrator_selection, profile,
                )
                with patch.object(host, "load_state", return_value=state):
                    with self.assertRaises(ValueError):
                        bridge._production_preview({
                            "chapter_number": 4,
                            "chapter_id": chapter.chapter_id,
                        })
                bridge._voice_preview.assert_not_called()


class ProductionPreviewJobIsolationHarness:
    _voice_preview = host.PremiumV2Bridge._voice_preview

    def __init__(self, project, profile):
        self.project = project
        self.profile = profile
        self._active_project = Mock(return_value=project)
        self._assert_no_active_model_lifecycle = Mock()
        self._assert_no_active_audio_synthesis = Mock()
        self._find_profile = Mock(return_value=profile)
        self._new_job = Mock(return_value="isolated-production-preview-job")
        self._job_update = Mock()
        self._now = Mock(return_value="2026-11-08T20:00:00+05:30")
        self._jobs_lock = threading.RLock()
        self._preview_cancel_events = {}
        self._preview_worker = Mock()


class ProductionPreviewJobIsolationTests(unittest.TestCase):
    def test_production_preview_creates_independent_job_without_changing_generation_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "project"
            folder.mkdir()
            chapter = SimpleNamespace(
                number=2,
                title="The Crossing",
                text="The saved chapter remains the source of preview narration.",
                chapter_id="chapter-two-stable",
            )
            project = SimpleNamespace(
                folder=folder,
                title="Independent Preview Book",
                chapters=[chapter],
            )
            profile = SimpleNamespace(name="Saved Narrator")
            persisted_state = {
                "generation_job_id": "already-running-full-generation",
                "status": "generating",
                "output_path": None,
                "generation_target_path": str(folder / "final-book.m4b"),
                "voice_profile": "Saved Narrator",
                "narrator_only_generation": True,
            }
            bridge = ProductionPreviewJobIsolationHarness(project, profile)
            thread = Mock()

            with (
                patch.object(host, "load_state", side_effect=lambda _folder: dict(persisted_state)),
                patch.object(host.threading, "Thread", return_value=thread) as thread_factory,
            ):
                result = bridge._voice_preview({
                    "profile_name": profile.name,
                    "chapter_number": 2,
                    "chapter_id": "chapter-two-stable",
                    "duration_seconds": 30,
                    "_production_preview": True,
                    "include_sound_design": True,
                    "route_character_cast": False,
                    "apply_pronunciation_rules": True,
                })

            self.assertEqual(result["job_id"], "isolated-production-preview-job")
            self.assertEqual(result["state"], "running")
            self.assertEqual(
                bridge._new_job.call_args.args[0],
                "production-preview",
            )
            self.assertNotEqual(
                bridge._new_job.call_args.args[0],
                "audiobook-generation",
            )
            self.assertEqual(
                bridge._new_job.call_args.args[1],
                "Production preview · Saved Narrator",
            )
            thread_factory.assert_called_once()
            self.assertEqual(
                thread_factory.call_args.kwargs["args"][2],
                chapter.text,
            )
            self.assertEqual(
                bridge._job_update.call_args.kwargs["current_chapter_id"],
                chapter.chapter_id,
            )
            self.assertEqual(
                persisted_state,
                {
                    "generation_job_id": "already-running-full-generation",
                    "status": "generating",
                    "output_path": None,
                    "generation_target_path": str(folder / "final-book.m4b"),
                    "voice_profile": "Saved Narrator",
                    "narrator_only_generation": True,
                },
            )
            thread.start.assert_called_once()
