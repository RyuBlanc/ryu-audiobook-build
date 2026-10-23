from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings

from app.core.character_library import (
    list_characters, list_deleted_characters, restore_character,
    soft_delete_character, sync_characters, update_character,
)
from app.core.paths import library_root as real_library_root
from app.core.project import Project, delete_project
from app.core.project_history import load_deleted_project_records
from app.core.state import save_state


class CharacterLibraryRegistryTests(unittest.TestCase):
    def test_series_registry_limits_aliases_keeps_manual_samples_and_recovers_deleted_entries(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-registry-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters(
                "Star Volume Series",
                [{
                    "name": "Aria",
                    "aliases": ["Ari", "Little Star", "Captain", "A", "Songbird", "Sixth Alias"],
                    "voice": "Voice A",
                    "examples": ["I will protect the city."],
                }],
                source_project_title="Star Volume 1",
                path=store,
            )
            records = list_characters(path=store)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["series"], "Star Volume Series")
            self.assertEqual(len(record["aliases"]), 5)
            self.assertEqual(record["voice_name"], "Voice A")
            self.assertEqual(record["dialogue_sample"], "I will protect the city.")

            update_character(record["id"], {
                "series": "Star Volume Series",
                "primary_name": "Aria the Star",
                "aliases": ["Ari", "Little Star"],
                "dialogue_sample": "A manually edited dialogue line.",
                "pronunciation": "AH-ree-ah",
            }, path=store)
            sync_characters(
                "Star Volume Series",
                [{"name": "Aria", "aliases": ["Aria the Star"], "voice": "Voice B", "examples": ["An AI example."]}],
                source_project_title="Star Volume 2",
                update_voice=True,
                path=store,
            )
            records = list_characters(path=store)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["primary_name"], "Aria the Star")
            self.assertEqual(records[0]["voice_name"], "Voice B")
            self.assertEqual(records[0]["dialogue_sample"], "A manually edited dialogue line.")
            self.assertEqual(records[0]["pronunciation"], "AH-ree-ah")

            soft_delete_character(records[0]["id"], path=store)
            self.assertEqual(list_characters(path=store), [])
            self.assertEqual(len(list_deleted_characters(path=store)), 1)

            # Character Studio sync must not silently recreate an item the user
            # moved to Recovery Bin.
            sync_characters(
                "Star Volume Series",
                [{"name": "Aria", "aliases": ["Aria the Star"], "voice": "Voice B"}],
                path=store,
            )
            self.assertEqual(list_characters(path=store), [])
            recovered = restore_character(records[0]["id"], path=store)
            self.assertEqual(recovered["primary_name"], "Aria the Star")
            self.assertEqual(len(list_characters(path=store)), 1)

    def test_same_character_name_in_different_series_is_a_separate_identity(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-series-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series One", [{"name": "Mira", "voice": "Voice A"}], path=store)
            sync_characters("Series Two", [{"name": "Mira", "voice": "Voice B"}], path=store)
            records = list_characters(path=store)
            self.assertEqual(len(records), 2)
            self.assertEqual({item["series"] for item in records}, {"Series One", "Series Two"})


class ProjectDeletionHistoryTests(unittest.TestCase):
    def test_project_delete_removes_saved_output_but_keeps_history_character_and_pronunciation(self):
        with tempfile.TemporaryDirectory(prefix="ryu-project-delete-") as tmp:
            root = Path(tmp)
            library = root / "Library"
            folder = library / "Star Volume 1"
            folder.mkdir(parents=True)
            output = root / "Audiobooks" / "Star Volume 1.m4b"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"generated-audiobook")
            project = Project("Star Volume 1", folder)
            project.save()
            save_state(folder, {
                "status": "completed",
                "output_path": str(output),
                "completed_chapters": [1, 2],
                "failed_chapters": [],
                "series_name": "Star Series",
                "voice_cast": {"Aria": "Voice A"},
                "voice_cast_character_roster": [{
                    "name": "Aria",
                    "aliases": ["Ari"],
                    "examples": ["I will protect the city."],
                    "voice": "Voice A",
                }],
                "pronunciation_dictionary": [{
                    "written": "Aria",
                    "spoken": "AH-ree-ah",
                    "enabled": True,
                    "source": "manual",
                }],
            })
            history_file = root / "Settings" / "project_history.json"
            character_file = root / "Settings" / "character_library.json"
            settings = QSettings("RyuBlanc", "Ryu's Audiobook")
            previous = settings.value("pronunciation/global_dictionary", None)
            existed = settings.contains("pronunciation/global_dictionary")
            try:
                with (
                    patch("app.core.paths.library_root", return_value=library),
                    patch("app.core.project_history.history_path", return_value=history_file),
                    patch("app.core.character_library.character_library_path", return_value=character_file),
                ):
                    delete_project(project)
                    self.assertFalse(folder.exists())
                    self.assertFalse(output.exists())

                    history = load_deleted_project_records(history_file)
                    self.assertEqual(len(history), 1)
                    self.assertEqual(history[0]["title"], "Star Volume 1")
                    self.assertEqual(history[0]["deletion_state"], "deleted")
                    self.assertTrue(history[0]["output_removed"])
                    self.assertEqual(history[0]["chapter_count"], 0)

                    characters = list_characters(path=character_file)
                    self.assertEqual(len(characters), 1)
                    self.assertEqual(characters[0]["primary_name"], "Aria")
                    self.assertEqual(characters[0]["voice_name"], "Voice A")
                    self.assertEqual(characters[0]["series"], "Star Series")

                    global_entries = json.loads(str(settings.value("pronunciation/global_dictionary", "[]")))
                    self.assertTrue(any(item.get("written") == "Aria" and item.get("spoken") == "AH-ree-ah" for item in global_entries))
            finally:
                if existed:
                    settings.setValue("pronunciation/global_dictionary", previous)
                else:
                    settings.remove("pronunciation/global_dictionary")
                settings.sync()


if __name__ == "__main__":
    unittest.main()
