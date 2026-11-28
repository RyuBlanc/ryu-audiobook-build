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
    prune_invalid_character_records,
    soft_delete_characters_many,
    purge_deleted_characters_many,
)
from app.core.paths import library_root as real_library_root
from app.core.project import Project, delete_project
from app.core.project_history import load_deleted_project_records
from app.core.state import save_state


class CharacterLibraryRegistryTests(unittest.TestCase):
    def test_series_registry_preserves_all_aliases_and_recovers_deleted_entries(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-registry-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters(
                "Star Volume Series",
                [{
                    "name": "Aria",
                    "short": "Ari",
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
            self.assertEqual(record["short"], "Ari")
            self.assertEqual(len(record["aliases"]), 6)
            self.assertIn("Sixth Alias", record["aliases"])
            self.assertEqual(record["voice_name"], "Voice A")
            self.assertEqual(record["dialogue_sample"], "I will protect the city.")

            update_character(record["id"], {
                "series": "Star Volume Series",
                "primary_name": "Aria the Star",
                "short": "Aria*",
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
            self.assertEqual(records[0]["short"], "Aria*")
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

    def test_sync_skips_ambiguous_alias_collision_without_mutating_either_identity(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-ambiguous-sync-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [
                    {"id": "mira", "series": "Series", "primary_name": "Mira",
                     "aliases": ["Captain"], "voice_name": "Voice A", "notes": "Mira notes"},
                    {"id": "ren", "series": "Series", "primary_name": "Ren",
                     "aliases": ["Captain"], "voice_name": "Voice B", "notes": "Ren notes"},
                ],
                "deleted": [],
            }, ensure_ascii=False), encoding="utf-8")
            before = list_characters(series="Series", path=store)
            sync_characters("Series", [{
                "name": "Captain", "aliases": ["New Alias"],
                "voice": "Wrong Voice", "notes": "Wrong identity",
            }], update_names=True, update_voice=True, path=store)
            after = list_characters(series="Series", path=store)
            self.assertEqual(after, before)
            self.assertEqual({row["primary_name"] for row in after}, {"Mira", "Ren"})
            self.assertEqual({row["voice_name"] for row in after}, {"Voice A", "Voice B"})
            self.assertFalse(any("New Alias" in row["aliases"] for row in after))

    def test_sync_blocks_alias_collision_with_recovery_bin(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-recovery-collision-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [{"id": "mira", "series": "Series", "primary_name": "Mira",
                            "aliases": ["Captain"], "voice_name": "Voice A"}],
                "deleted": [{"id": "old-ren", "series": "Series", "primary_name": "Ren",
                             "aliases": ["Captain"], "voice_name": "Voice B"}],
            }, ensure_ascii=False), encoding="utf-8")
            before = list_characters(series="Series", path=store)
            sync_characters("Series", [{"name": "Captain", "aliases": ["New Alias"],
                                        "voice": "Wrong Voice"}], update_voice=True, path=store)
            self.assertEqual(list_characters(series="Series", path=store), before)
            self.assertEqual(before[0]["voice_name"], "Voice A")

    def test_sync_normalizes_unicode_equivalent_names_and_aliases(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-unicode-sync-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series", [{"name": "Café"}], path=store)
            sync_characters("Series", [{"name": "Cafe\u0301",
                                        "aliases": ["Café", "Cafe\u0301", "Coffee"]}], path=store)
            saved = list_characters(series="Series", path=store)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["primary_name"], "Café")
            self.assertEqual(saved[0]["aliases"], ["Coffee"])

    def test_sync_preserves_age_variant_and_never_cross_merges_variant_aliases(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-variant-sync-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series", [
                {"name": "Mira", "aliases": ["Captain Mira"], "voice": "Adult Voice"},
                {"name": "Mira (Younger Version)", "identity_base_name": "Mira",
                 "identity_variant": "Younger Version", "aliases": ["Young Mira"],
                 "voice": "Young Voice"},
            ], path=store)
            before = list_characters(series="Series", path=store)
            self.assertEqual(len(before), 2)
            sync_characters("Series", [{
                "name": "Young Mira", "identity_base_name": "Mira",
                "identity_variant": "Younger Version", "aliases": ["Captain Mira"],
                "voice": "Wrong Voice",
            }], update_names=True, update_voice=True, path=store)
            self.assertEqual(list_characters(series="Series", path=store), before)
            sync_characters("Series", [{
                "name": "Mira (Younger Version)", "identity_base_name": "Mira",
                "identity_variant": "Younger Version", "aliases": ["Childhood Mira"],
                "voice": "Young Voice",
            }], update_voice=True, path=store)
            after = list_characters(series="Series", path=store)
            adult = next(row for row in after if row["primary_name"] == "Mira")
            younger = next(row for row in after if row["primary_name"] == "Mira (Younger Version)")
            self.assertEqual(len(after), 2)
            self.assertEqual(adult["voice_name"], "Adult Voice")
            self.assertEqual(younger["voice_name"], "Young Voice")
            self.assertIn("Childhood Mira", younger["aliases"])
            self.assertEqual(younger["identity_base_name"], "Mira")
            self.assertEqual(younger["identity_variant"], "Younger Version")

    def test_same_character_name_in_different_series_is_a_separate_identity(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-series-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series One", [{"name": "Mira", "voice": "Voice A"}], path=store)
            sync_characters("Series Two", [{"name": "Mira", "voice": "Voice B"}], path=store)
            records = list_characters(path=store)
            self.assertEqual(len(records), 2)
            self.assertEqual({item["series"] for item in records}, {"Series One", "Series Two"})


    def test_prune_legacy_english_false_characters_and_aliases_is_series_scoped_and_recoverable(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-prune-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [
                    {"id": "bad-magic", "series": "Series A", "primary_name": "Magic",
                     "aliases": ["Oh", "The"], "scope": "Series · Series A"},
                    {"id": "bad-any", "series": "Series A", "primary_name": "Any",
                     "aliases": [], "scope": "Series · Series A"},
                    {"id": "good-mira", "series": "Series A", "primary_name": "Mira",
                     "aliases": ["Captain Mira", "Oh", "Any"], "manual": True},
                    {"id": "other-series", "series": "Series B", "primary_name": "Magic",
                     "aliases": [], "scope": "Series · Series B"},
                ],
                "deleted": [],
            }, ensure_ascii=False), encoding="utf-8")

            result = prune_invalid_character_records("Series A", path=store)
            active_a = list_characters(series="Series A", path=store)
            active_b = list_characters(series="Series B", path=store)
            deleted = list_deleted_characters(path=store)

            self.assertEqual(result, {"removed": 2, "aliases_removed": 2})
            self.assertEqual([row["primary_name"] for row in active_a], ["Mira"])
            self.assertEqual(active_a[0]["aliases"], ["Captain Mira"])
            self.assertEqual([row["primary_name"] for row in active_b], ["Magic"])
            self.assertEqual({row["id"] for row in deleted}, {"bad-magic", "bad-any"})


    def test_restore_refuses_same_series_name_or_alias_collision_without_mutating_recovery(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-restore-collision-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [{
                    "id": "active-mira", "series": "Star Series",
                    "primary_name": "Mira", "aliases": ["Captain"],
                    "voice_name": "Mira Voice",
                }],
                "deleted": [{
                    "id": "deleted-ren", "series": "Star Series",
                    "primary_name": "Ren", "aliases": ["Captain"],
                    "voice_name": "Ren Voice", "deleted_at": "2026-11-22T10:00:00Z",
                }],
            }, ensure_ascii=False), encoding="utf-8")

            before_active = list_characters(series="Star Series", path=store)
            before_deleted = list_deleted_characters(path=store)

            with self.assertRaisesRegex(ValueError, "already in use"):
                restore_character("deleted-ren", path=store)

            self.assertEqual(list_characters(series="Star Series", path=store), before_active)
            self.assertEqual(list_deleted_characters(path=store), before_deleted)
            saved = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual([row["id"] for row in saved["active"]], ["active-mira"])
            self.assertEqual([row["id"] for row in saved["deleted"]], ["deleted-ren"])

    def test_restore_allows_same_name_in_a_different_series(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-restore-series-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [{
                    "id": "volume-one-mira", "series": "Series One",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                }],
                "deleted": [{
                    "id": "volume-two-mira", "series": "Series Two",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                }],
            }, ensure_ascii=False), encoding="utf-8")

            restored = restore_character("volume-two-mira", path=store)
            self.assertEqual(restored["series"], "Series Two")
            self.assertEqual(
                {(row["series"], row["primary_name"]) for row in list_characters(path=store)},
                {("Series One", "Mira"), ("Series Two", "Mira")},
            )
            self.assertEqual(list_deleted_characters(path=store), [])

    def test_bulk_soft_delete_moves_only_selected_records_and_preserves_voice_data(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-bulk-delete-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters(
                "Bulk Series",
                [
                    {"name": "Mira", "aliases": ["Captain Mira"], "voice": "Voice A",
                     "examples": ["I will protect you."], "pronunciation": "Mee-ra"},
                    {"name": "Ren", "aliases": ["Renji"], "voice": "Voice B",
                     "examples": ["Come with me."]},
                    {"name": "Akari", "voice": "Voice C"},
                ],
                path=store,
            )
            active = list_characters(path=store)
            selected_names = {"Mira", "Akari"}
            selected = [
                row["id"] for row in active
                if row["primary_name"] in selected_names
            ]
            moved = soft_delete_characters_many(selected, path=store)

            self.assertEqual({row["id"] for row in moved}, set(selected))
            self.assertEqual(
                {row["primary_name"] for row in list_characters(path=store)},
                {"Ren"},
            )
            recovery = list_deleted_characters(path=store)
            self.assertEqual({row["id"] for row in recovery}, set(selected))
            mira = next(row for row in recovery if row["primary_name"] == "Mira")
            self.assertEqual(mira["aliases"], ["Captain Mira"])
            self.assertEqual(mira["voice_name"], "Voice A")
            self.assertEqual(mira["dialogue_sample"], "I will protect you.")
            self.assertEqual(mira["pronunciation"], "Mee-ra")
            self.assertTrue(mira.get("deleted_at"))

    def test_bulk_soft_delete_rejects_stale_ids_without_partially_mutating_store(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-bulk-stale-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series", [{"name": "Mira"}, {"name": "Ren"}], path=store)
            before = list_characters(path=store)
            with self.assertRaises(KeyError):
                soft_delete_characters_many([before[0]["id"], "stale-id"], path=store)
            self.assertEqual(list_characters(path=store), before)
            self.assertEqual(list_deleted_characters(path=store), [])

    def test_recovery_purge_selected_and_clear_all_never_touch_active_records(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-purge-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters(
                "Series",
                [{"name": "Mira", "voice": "Voice A"},
                 {"name": "Ren", "voice": "Voice B"},
                 {"name": "Akari", "voice": "Voice C"}],
                path=store,
            )
            active = list_characters(path=store)
            soft_delete_characters_many([active[0]["id"], active[1]["id"]], path=store)
            deleted = list_deleted_characters(path=store)
            first = purge_deleted_characters_many([deleted[0]["id"]], path=store)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(list_deleted_characters(path=store)), 1)
            self.assertEqual(len(list_characters(path=store)), 1)

            all_purged = purge_deleted_characters_many(None, path=store)
            self.assertEqual(len(all_purged), 1)
            self.assertEqual(list_deleted_characters(path=store), [])
            self.assertEqual(list_characters(path=store), active[2:])

    def test_recovery_purge_rejects_unknown_ids_and_empty_explicit_selection(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-purge-validation-") as tmp:
            store = Path(tmp) / "character-library.json"
            sync_characters("Series", [{"name": "Mira"}], path=store)
            active = list_characters(path=store)
            soft_delete_characters_many([active[0]["id"]], path=store)
            deleted = list_deleted_characters(path=store)
            with self.assertRaises(KeyError):
                purge_deleted_characters_many(["unknown"], path=store)
            with self.assertRaises(ValueError):
                purge_deleted_characters_many([], path=store)
            self.assertEqual(list_deleted_characters(path=store), deleted)


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


class CharacterLibraryDuplicateRecoveryTests(unittest.TestCase):
    def test_restore_merges_exact_duplicate_without_replacing_active_id_or_voice(self):
        with tempfile.TemporaryDirectory(prefix="ryu-character-restore-duplicate-") as tmp:
            store = Path(tmp) / "character-library.json"
            store.write_text(json.dumps({
                "version": 1,
                "active": [{
                    "id": "active-ludivine", "series": "Silver Archive",
                    "primary_name": "Ludivine Marie-Ange de la Tréfle",
                    "aliases": ["Ludivine"], "identity_variant": "",
                    "voice_name": "Saved Qwen Ludivine Voice", "notes": "Active user notes",
                }],
                "deleted": [{
                    "id": "recovery-ludivine", "series": "Silver Archive",
                    "primary_name": "Ludivine Marie-Ange de la Tréfle",
                    "aliases": ["Lady Ludivine"], "identity_variant": "",
                    "voice_name": "Older Recovery Voice", "notes": "Recovery notes",
                    "deleted_at": "2026-11-20T10:00:00+00:00",
                }],
            }, ensure_ascii=False), encoding="utf-8")

            restored = restore_character("recovery-ludivine", path=store)

            self.assertTrue(restored.get("_merged_from_recovery"))
            active = list_characters(series="Silver Archive", path=store)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["id"], "active-ludivine")
            self.assertIn("Lady Ludivine", active[0]["aliases"])
            self.assertEqual(active[0]["voice_name"], "Saved Qwen Ludivine Voice")
            self.assertEqual(active[0]["notes"], "Active user notes")
            self.assertEqual(list_deleted_characters(path=store), [])
