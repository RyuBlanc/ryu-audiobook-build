from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class CharacterLibraryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = self.root / "Settings"
        self.settings.mkdir()
        self.app_patch = patch("app.core.character_library.app_root", return_value=self.root)
        self.app_patch.start()
        self.addCleanup(self.app_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def test_empty_library_has_no_demo_records(self):
        from app.core.character_library import load_character_library
        self.assertEqual(load_character_library(), [])

    def test_character_studio_upsert_groups_by_series_and_limits_aliases_to_five(self):
        from app.core.character_library import (
            upsert_characters_from_studio, load_character_library,
        )
        first = upsert_characters_from_studio("Novel", [{
            "name": "Character One",
            "aliases": ["short", "nickname", "title", "alias 4", "alias 5", "alias 6"],
            "voice": "Voice A",
            "sample": "A real line from the book.",
        }])
        second = upsert_characters_from_studio("Novel", [{
            "name": "Character One",
            "aliases": ["later name"],
            "voice": "Voice B",
        }])
        rows = load_character_library()
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["series"], "Novel")
        self.assertLessEqual(len(rows[0]["aliases"]), 5)
        self.assertEqual(rows[0]["dialogue_sample"], "A real line from the book.")
        self.assertEqual(rows[0]["voice_name"], "Voice B")

    def test_edit_delete_and_restore_character_record(self):
        from app.core.character_library import (
            upsert_characters_from_studio, load_character_library,
            update_character, soft_delete_character, restore_character,
        )
        upsert_characters_from_studio("Series A", [{
            "name": "Character Two", "aliases": ["nickname"], "sample": "Hello."
        }])
        row = load_character_library()[0]
        updated = update_character(row["id"], {
            "primary_name": "Character Renamed",
            "aliases": ["one", "two", "three", "four", "five", "six"],
            "dialogue_sample": "Good morning.",
        })
        self.assertEqual(updated["primary_name"], "Character Renamed")
        self.assertEqual(len(updated["aliases"]), 5)
        deleted = soft_delete_character(row["id"])
        self.assertTrue(deleted["deleted"])
        restored = restore_character(row["id"])
        self.assertFalse(restored["deleted"])

    def test_character_library_rejects_voice_change_outside_studio(self):
        from app.core.character_library import (
            upsert_characters_from_studio, load_character_library, update_character,
        )
        upsert_characters_from_studio("Series B", [{"name": "Character Three"}])
        row = load_character_library()[0]
        with self.assertRaises(ValueError):
            update_character(row["id"], {"voice_name": "Voice X"})


if __name__ == "__main__":
    unittest.main()
