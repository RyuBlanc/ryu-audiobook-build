from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.character_library import list_characters, sync_characters
from app.ui.premium_v2_host import _character_library_export_document


class CharacterLibraryExportDocumentTests(unittest.TestCase):
    def test_portable_document_exports_canonical_names_aliases_and_series_identity_only(self):
        document = _character_library_export_document([
            {
                "id": "local-id-should-not-export",
                "primary_name": "Mira",
                "series": "Silver Archive",
                "short": "Mi",
                "aliases": ["Captain Mira", "Mira-sama", "Mira"],
                "identity_base_name": "Mira",
                "identity_variant": "Adult",
                "notes": "The captain of the archive guard.",
                "dialogue_sample": "Stay behind me.",
                "pronunciation": "Mee-ra",
                "line_count": 47,
                "chapter_count": 6,
                "confidence": 98,
                "voice_name": "RTX 8GB local Qwen voice",
                "voice_profile_id": "local-profile-123",
                "voice_model_path": "C:/Users/private/models/profile",
                "model_path": "C:/Users/private/models/qwen",
                "source_project_folder": "D:/Books/Silver Archive",
            }
        ], "Silver Archive")

        self.assertEqual(document["schema"], "ryu.character-library")
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["scope"], "series")
        self.assertEqual(document["series"], "Silver Archive")
        self.assertFalse(document["voice_assets_included"])
        self.assertEqual(len(document["characters"]), 1)
        character = document["characters"][0]
        self.assertEqual(character["name"], "Mira")
        self.assertEqual(character["primary_name"], "Mira")
        self.assertEqual(character["aliases"], ["Captain Mira", "Mira-sama"])
        self.assertEqual(character["identity_base_name"], "Mira")
        self.assertEqual(character["identity_variant"], "Adult")
        self.assertEqual(character["notes"], "The captain of the archive guard.")
        self.assertNotIn("id", character)
        self.assertNotIn("voice_name", character)
        self.assertNotIn("voice_profile_id", character)
        self.assertNotIn("voice_model_path", character)
        self.assertNotIn("model_path", character)
        self.assertNotIn("source_project_folder", character)
        self.assertIn("assign a compatible local saved Voice Studio profile", document["voice_asset_note"])

    def test_all_series_export_keeps_same_name_separate_by_series(self):
        document = _character_library_export_document([
            {"primary_name": "Mira", "series": "Series One", "aliases": ["Captain Mira"]},
            {"primary_name": "Mira", "series": "Series Two", "aliases": ["Mira the Mage"]},
        ])
        self.assertEqual(document["scope"], "all_series")
        self.assertIsNone(document["series"])
        self.assertEqual(
            {(row["series"], row["name"]) for row in document["characters"]},
            {("Series One", "Mira"), ("Series Two", "Mira")},
        )

    def test_series_filter_excludes_other_series_and_rejects_duplicate_canonical_identities(self):
        filtered = _character_library_export_document([
            {"primary_name": "Mira", "series": "Series One"},
            {"primary_name": "Ren", "series": "Series Two"},
        ], "Series Two")
        self.assertEqual([row["name"] for row in filtered["characters"]], ["Ren"])
        self.assertEqual(filtered["series"], "Series Two")
        with self.assertRaisesRegex(ValueError, "duplicate canonical identities"):
            _character_library_export_document([
                {"primary_name": "Mira", "series": "Series One"},
                {"primary_name": "Mira", "series": "series one"},
            ])


    def test_export_then_import_merges_aliases_without_overwriting_a_local_voice(self):
        with tempfile.TemporaryDirectory(prefix="ryu-portable-library-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Silver Archive", [{
                "name": "Mira",
                "aliases": ["Captain Mira"],
                "voice": "This PC's Saved Qwen Voice",
            }], path=store)
            original = list_characters(series="Silver Archive", path=store)[0]
            document = _character_library_export_document([original], "Silver Archive")
            imported = document["characters"][0]

            # This is the import shape accepted by character_library.import:
            # no voice key is supplied because profile assets are machine-local.
            self.assertNotIn("voice", imported)
            self.assertNotIn("voice_name", imported)
            sync_characters("Silver Archive", [{
                "name": imported["name"],
                "short": imported["short"],
                "aliases": imported["aliases"],
                "identity_base_name": imported["identity_base_name"],
                "identity_variant": imported["identity_variant"],
                "notes": imported["notes"],
                "pronunciation": imported["pronunciation"],
                "line_count": imported["line_count"],
                "chapter_count": imported["chapter_count"],
                "confidence": imported["confidence"],
            }], update_names=True, update_voice=False, path=store)

            saved = list_characters(series="Silver Archive", path=store)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["primary_name"], "Mira")
            self.assertIn("Captain Mira", saved[0]["aliases"])
            self.assertEqual(saved[0]["voice_name"], "This PC's Saved Qwen Voice")



if __name__ == "__main__":
    unittest.main()
