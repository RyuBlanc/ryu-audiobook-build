from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.character_library import (
    import_character_library_records,
    list_characters,
    soft_delete_character,
    sync_characters,
    character_library_exclusion_keys,
    reconcile_project_character_cast,
)
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



    def test_portable_import_merges_all_series_and_preserves_local_voice_and_manual_details(self):
        with tempfile.TemporaryDirectory(prefix="ryu-portable-library-atomic-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Silver Archive", [{
                "name": "Mira",
                "aliases": ["Captain Mira"],
                "voice": "This PC's Qwen 1.7B voice",
                "notes": "Locally confirmed notes.",
                "dialogue_sample": "Stay behind me.",
            }], path=store)
            imported = import_character_library_records([
                {
                    "name": "Mira",
                    "series": "Silver Archive",
                    "aliases": ["Mira-sama", "Captain Mira"],
                    "identity_base_name": "Mira",
                    "identity_variant": "",
                    "notes": "Notes from the transfer PC.",
                    "dialogue_sample": "Transferred sample.",
                    "pronunciation": "Mee-ra",
                    "line_count": 70,
                    "chapter_count": 9,
                    "confidence": 99,
                },
                {
                    "name": "Ren",
                    "series": "Another Series",
                    "aliases": ["Ren-kun"],
                    "identity_base_name": "Ren",
                    "identity_variant": "",
                    "notes": "A different series character.",
                    "dialogue_sample": "I will go first.",
                    "pronunciation": "Wren",
                    "line_count": 12,
                    "chapter_count": 2,
                    "confidence": 96,
                },
            ], path=store)

            saved = list_characters(path=store)
            self.assertEqual(len(imported), 2)
            self.assertEqual({(row["series"], row["primary_name"]) for row in saved}, {
                ("Silver Archive", "Mira"), ("Another Series", "Ren")
            })
            mira = next(row for row in saved if row["series"] == "Silver Archive")
            self.assertEqual(mira["voice_name"], "This PC's Qwen 1.7B voice")
            self.assertEqual(mira["notes"], "Locally confirmed notes.")
            self.assertEqual(mira["dialogue_sample"], "Stay behind me.")
            self.assertIn("Mira-sama", mira["aliases"])
            self.assertIn("Captain Mira", mira["aliases"])
            ren = next(row for row in saved if row["series"] == "Another Series")
            self.assertEqual(ren["dialogue_sample"], "I will go first.")
            self.assertEqual(ren["pronunciation"], "Wren")
            self.assertEqual(ren["line_count"], 12)
            self.assertEqual(ren["chapter_count"], 2)
            self.assertFalse(ren.get("voice_name"))

    def test_portable_import_is_atomic_when_a_later_series_hits_recovery_conflict(self):
        with tempfile.TemporaryDirectory(prefix="ryu-portable-library-rollback-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series Two", [{"name": "Deleted Hero", "aliases": ["Old Alias"]}], path=store)
            deleted = list_characters(series="Series Two", path=store)[0]
            soft_delete_character(deleted["id"], path=store)
            before = store.read_bytes()

            with self.assertRaisesRegex(ValueError, "Recovery Bin"):
                import_character_library_records([
                    {
                        "name": "New Character",
                        "series": "Series One",
                        "aliases": ["New Alias"],
                    },
                    {
                        "name": "Replacement",
                        "series": "Series Two",
                        "aliases": ["Old Alias"],
                    },
                ], path=store)

            self.assertEqual(store.read_bytes(), before)
            self.assertEqual(list_characters(series="Series One", path=store), [])
            self.assertEqual(list_characters(series="Series Two", include_deleted=True, path=store)[0]["primary_name"], "Deleted Hero")





    def test_project_cast_reconciles_to_active_series_library_and_removes_deleted_rows(self):
        project_rows = [
            {
                "name": "Captain Mira",
                "series": "Silver Archive",
                "aliases": ["Mira-sama"],
                "voice_profile": "This PC's Qwen Mira voice",
            },
            {
                "name": "Deleted Hero",
                "series": "Silver Archive",
                "aliases": ["Old Hero"],
                "character_library_id": "deleted-id",
            },
        ]
        registry_rows = [
            {
                "id": "mira-active", "primary_name": "Mira", "series": "Silver Archive",
                "aliases": ["Captain Mira", "Mira-sama"], "identity_variant": "",
                "voice_name": "Other PC's voice label",
            },
            {
                "id": "ren-active", "primary_name": "Ren", "series": "Silver Archive",
                "aliases": ["Ren-kun"], "identity_variant": "",
            },
        ]
        reconciled, orphaned = reconcile_project_character_cast(
            project_rows, registry_rows, default_series="Silver Archive"
        )
        by_name = {row["name"]: row for row in reconciled}
        self.assertEqual(set(by_name), {"Mira", "Ren"})
        self.assertEqual(by_name["Mira"]["character_library_id"], "mira-active")
        self.assertEqual(by_name["Mira"]["voice_profile"], "This PC's Qwen Mira voice")
        self.assertEqual(by_name["Mira"]["aliases"], ["Captain Mira", "Mira-sama"])
        self.assertEqual(by_name["Ren"]["character_library_id"], "ren-active")
        self.assertEqual([row["name"] for row in orphaned], ["Deleted Hero"])
        exclusions = character_library_exclusion_keys(orphaned, "Silver Archive", registry_rows)
        self.assertEqual(exclusions, {"deleted hero", "old hero"})
        self.assertNotIn("captain mira", exclusions)

    def test_project_cast_reconciliation_keeps_age_versions_distinct(self):
        registry_rows = [
            {"id": "mira-adult", "primary_name": "Mira", "series": "Silver Archive",
             "aliases": ["Captain Mira"], "identity_variant": "Adult"},
            {"id": "mira-young", "primary_name": "Mira", "series": "Silver Archive",
             "aliases": ["Young Mira"], "identity_variant": "Younger"},
        ]
        project_rows = [
            {"name": "Mira", "series": "Silver Archive", "identity_variant": "Adult",
             "character_library_id": "mira-adult", "voice_profile": "Adult profile"},
            {"name": "Mira", "series": "Silver Archive", "identity_variant": "Younger",
             "character_library_id": "mira-young", "voice_profile": "Young profile"},
        ]
        reconciled, orphaned = reconcile_project_character_cast(
            project_rows, registry_rows, default_series="Silver Archive"
        )
        self.assertEqual(orphaned, [])
        self.assertEqual(
            {(row["character_library_id"], row["identity_variant"], row["voice_profile"]) for row in reconciled},
            {("mira-adult", "Adult", "Adult profile"), ("mira-young", "Younger", "Young profile")},
        )

if __name__ == "__main__":
    unittest.main()
