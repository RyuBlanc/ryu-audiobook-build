"""Regression tests for non-blocking active-project resolution.

The active-project bridge path must not enumerate or deserialize every book in
the Library for each chapter, voice, cast, sound, or generation request.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.core.project import Project, create_project, resolve_library_project_folder


class _Settings:
    def __init__(self, values: dict[str, str]):
        self.values = dict(values)

    def value(self, key: str, default=None):
        return self.values.get(key, default)

    def remove(self, key: str) -> None:
        self.values.pop(key, None)

    def setValue(self, key: str, value) -> None:
        self.values[key] = value

    def sync(self) -> None:
        pass


class ActiveProjectLookupPerformanceTests(unittest.TestCase):
    def test_active_project_reuses_loaded_object_without_library_enumeration(self):
        from app.ui.premium_v2_host import PremiumV2Bridge

        with TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("Chapter 1\nA real chapter body.", encoding="utf-8")
            with patch("app.core.project.library_root", return_value=root):
                created = create_project(
                    "Active Book", source,
                    [Chapter(1, "Chapter 1", "A real chapter body.")],
                )

            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            bridge.settings = _Settings({"project/active_folder": str(created.folder)})
            bridge._active_project_cache_lock = threading.RLock()
            bridge._active_project_cache = None
            bridge._active_project_migrated_folders = set()

            with (
                patch("app.core.project.project_library_roots", return_value=(root,)),
                patch("app.ui.premium_v2_host.list_projects", side_effect=AssertionError(
                    "active-project access must not enumerate every Library project"
                )),
                patch.object(Project, "load", wraps=Project.load) as load,
            ):
                first = PremiumV2Bridge._active_project(bridge)
                second = PremiumV2Bridge._active_project(bridge)

            self.assertIs(first, second)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(second.chapters[0].text, "A real chapter body.")

    def test_active_project_reloads_changed_chapter_file_without_repeating_legacy_migration(self):
        from app.ui.premium_v2_host import PremiumV2Bridge

        with TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("Chapter 1\nFirst body.", encoding="utf-8")
            with patch("app.core.project.library_root", return_value=root):
                created = create_project(
                    "Changed Book", source, [Chapter(1, "Chapter 1", "First body.")],
                )

            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            bridge.settings = _Settings({"project/active_folder": str(created.folder)})
            bridge._active_project_cache_lock = threading.RLock()
            bridge._active_project_cache = None
            bridge._active_project_migrated_folders = set()

            with (
                patch("app.core.project.project_library_roots", return_value=(root,)),
                patch.object(Project, "load", wraps=Project.load) as load,
            ):
                first = PremiumV2Bridge._active_project(bridge)
                first.chapters[0].text = "Updated body with a different size."
                first.save()
                second = PremiumV2Bridge._active_project(bridge)

            self.assertIsNot(first, second)
            self.assertEqual(second.chapters[0].text, "Updated body with a different size.")
            self.assertEqual(load.call_count, 2)
            self.assertTrue(load.call_args_list[0].kwargs["migrate_legacy"])
            self.assertFalse(load.call_args_list[1].kwargs["migrate_legacy"])

    def test_active_project_preserves_selected_path_when_library_drive_is_unavailable(self):
        from app.ui.premium_v2_host import PremiumV2Bridge

        with TemporaryDirectory() as temp:
            missing_root = Path(temp) / "disconnected-library"
            folder = missing_root / "Existing Book"
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            bridge.settings = _Settings({"project/active_folder": str(folder)})
            bridge._active_project_cache_lock = threading.RLock()
            bridge._active_project_cache = None
            bridge._active_project_migrated_folders = set()

            with patch("app.core.project.project_library_roots", return_value=(missing_root,)):
                with self.assertRaisesRegex(FileNotFoundError, "Library location is unavailable"):
                    PremiumV2Bridge._active_project(bridge)

            self.assertEqual(bridge.settings.value("project/active_folder"), str(folder))

    def test_library_folder_resolver_rejects_paths_outside_direct_library_children(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.mkdir()
            project_folder = root / "Book"
            project_folder.mkdir()
            (project_folder / "project.json").write_text('{"title":"Book"}', encoding="utf-8")
            (project_folder / "chapters.json").write_text("[]", encoding="utf-8")

            with patch("app.core.project.project_library_roots", return_value=(root,)):
                self.assertEqual(resolve_library_project_folder(project_folder), project_folder.resolve())
                self.assertIsNone(resolve_library_project_folder(outside / "Book"))

    def test_known_project_actions_resolve_directly_without_enumerating_the_library(self):
        """A command with an exact saved folder must load only that project."""
        source = (Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        method_names = {
            "_project_trash",
            "_project_delete",
            "_production_generate_book",
            "_restart_generation_from_job",
            "_player_get_active",
            "_player_position_save",
            "_character_library_save",
        }
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in method_names
        }
        self.assertEqual(set(methods), method_names)
        for name, method in methods.items():
            with self.subTest(method=name):
                full_library_scans = [
                    node for node in ast.walk(method)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "list_projects"
                ]
                direct_project_loads = [
                    node for node in ast.walk(method)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                    and node.func.attr == "_load_library_project"
                ]
                self.assertFalse(
                    full_library_scans,
                    f"{name} has a known project folder but still enumerates every Library project",
                )
                self.assertTrue(
                    direct_project_loads,
                    f"{name} must use the validated direct-child project resolver",
                )

    def test_known_project_folder_actions_still_use_the_library_boundary_resolver(self):
        from app.ui.premium_v2_host import PremiumV2Bridge

        with TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("Chapter 1\\nA real chapter body.", encoding="utf-8")
            with patch("app.core.project.library_root", return_value=root):
                created = create_project(
                    "Direct Folder Book", source,
                    [Chapter(1, "Chapter 1", "A real chapter body.")],
                )
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            bridge._active_project_cache_lock = threading.RLock()
            bridge._active_project_cache = None
            bridge._active_project_migrated_folders = set()
            bridge.settings = _Settings({})
            with (
                patch("app.core.project.project_library_roots", return_value=(root,)),
                patch("app.ui.premium_v2_host.list_projects", side_effect=AssertionError(
                    "known-folder operations must not enumerate the entire Library"
                )),
            ):
                loaded = PremiumV2Bridge._load_library_project(bridge, created.folder)
                rejected = PremiumV2Bridge._load_library_project(bridge, root.parent / "outside")
            self.assertEqual(loaded.folder.resolve(), created.folder.resolve())
            self.assertIsNone(rejected)

    def test_project_reload_without_migration_does_not_walk_narration_or_rewrite_legacy_bgm(self):
        from app.core.state import save_state

        with TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("Chapter 1\nBody.", encoding="utf-8")
            with patch("app.core.project.library_root", return_value=root):
                created = create_project(
                    "No Migration Book", source, [Chapter(1, "Chapter 1", "Body.")],
                )
            working_audio = created.folder / "working_audio"
            (working_audio / "chapter_1").mkdir(parents=True)
            (working_audio / "chapter_1" / "narration.json").write_text(
                json.dumps({"chapter": 1, "title": "Chapter 1"}),
                encoding="utf-8",
            )
            save_state(created.folder, {"chapter_bgm_overrides": {"1": {"track_path": "music.mp3"}}})

            with (
                patch.object(Path, "iterdir", side_effect=AssertionError(
                    "non-migrating project reload must not enumerate narration folders"
                )),
                patch("app.core.state.save_state", side_effect=AssertionError(
                    "non-migrating project reload must not rewrite legacy BGM state"
                )),
            ):
                loaded = Project.load(created.folder, migrate_legacy=False)

            self.assertEqual(loaded.chapters[0].text, "Body.")
            narration = json.loads((working_audio / "chapter_1" / "narration.json").read_text(encoding="utf-8"))
            self.assertNotIn("chapter_id", narration)
            state = json.loads((created.folder / "state.json").read_text(encoding="utf-8"))
            self.assertIn("1", state["chapter_bgm_overrides"])


if __name__ == "__main__":
    unittest.main()
