"""Stage 4 pronunciation dictionary persistence, scope, and validation regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ui import premium_v2_host as host
from app.tts.narration import apply_pronunciation_dictionary


class _BridgeHarness:
    def __init__(self, folder):
        self.project = SimpleNamespace(folder=Path(folder))
    def _active_project(self):
        return self.project
    def _now(self):
        return "2026-10-22T00:00:00+00:00"


class PronunciationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_a = self.root / "project-a"
        self.project_b = self.root / "project-b"
        self.project_a.mkdir()
        self.project_b.mkdir()
        self.bridge_a = _BridgeHarness(self.project_a)
        self.bridge_b = _BridgeHarness(self.project_b)
        self.settings = self.root / "settings"
        self.settings.mkdir()
        self.settings_patch = patch.object(host, "settings_root", return_value=self.settings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def save(self, bridge, written, spoken, **extra):
        return host.PremiumV2Bridge._pronunciation_save(
            bridge, {"written_form": written, "spoken_form": spoken, **extra}
        )

    def list(self, bridge):
        return host.PremiumV2Bridge._pronunciation_list(bridge, {})

    def delete(self, bridge, written, **extra):
        return host.PremiumV2Bridge._pronunciation_delete(
            bridge, {"written_form": written, **extra}
        )

    def test_save_reload_and_nfc_casefold_duplicate_update(self):
        self.save(self.bridge_a, "e\u0301owyn", "Ay-oh-win")
        result = self.save(self.bridge_a, "ÉOWYN", "Ee-oh-win")
        rows = self.list(self.bridge_a)
        self.assertEqual(1, len(rows))
        self.assertEqual("ÉOWYN", rows[0]["written_form"])
        self.assertEqual("Ee-oh-win", rows[0]["spoken_form"])
        self.assertTrue(result["updated_existing"])
        self.assertTrue(result["conflict_resolved"])
        persisted = json.loads((self.project_a / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(persisted["pronunciation_dictionary"]))

    def test_legacy_duplicate_rows_are_collapsed_on_edit(self):
        (self.project_a / "state.json").write_text(json.dumps({
            "pronunciation_dictionary": [
                {"written": "Mira", "spoken": "Mee-rah"},
                {"written_form": "mira", "spoken_form": "My-rah"},
                {"written_form": "", "spoken_form": "invalid"},
            ]
        }), encoding="utf-8")
        result = self.save(self.bridge_a, "MIRA", "Mih-rah")
        self.assertEqual(1, result["duplicate_rows_collapsed"])
        rows = self.list(self.bridge_a)
        self.assertEqual(1, len(rows))
        self.assertEqual("Mih-rah", rows[0]["spoken_form"])

    def test_project_scope_is_isolated_between_projects(self):
        self.save(self.bridge_a, "Mira", "Mee-rah")
        self.assertEqual(["Mira"], [row["written_form"] for row in self.list(self.bridge_a)])
        self.assertEqual([], self.list(self.bridge_b))

    def test_global_library_entry_persists_and_is_visible_across_projects(self):
        self.save(self.bridge_a, "Ryu", "Ree-yoo", scope="Global library")
        rows_a = self.list(self.bridge_a)
        rows_b = self.list(self.bridge_b)
        self.assertEqual(1, len(rows_a))
        self.assertEqual(1, len(rows_b))
        self.assertEqual("global_library", rows_b[0]["scope_type"])
        self.assertTrue(host._pronunciation_scope_path("global_library").is_file())

    def test_series_entries_are_separate_by_normalized_series_name(self):
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", scope="Series · Slime")
        self.save(self.bridge_a, "Rimuru", "Rim-oo-roo", scope="Series · Other")
        rows = [row for row in self.list(self.bridge_b) if row["scope_type"] == "series"]
        self.assertEqual({"Slime", "Other"}, {row["scope_id"] for row in rows})
        self.delete(self.bridge_b, "Rimuru", scope="Series · Slime")
        rows = [row for row in self.list(self.bridge_b) if row["scope_type"] == "series"]
        self.assertEqual({"Other"}, {row["scope_id"] for row in rows})

    def test_empty_delete_and_invalid_save_do_not_mutate_dictionary(self):
        self.save(self.bridge_a, "Mira", "Mee-rah")
        with self.assertRaisesRegex(ValueError, "Written term"):
            host.PremiumV2Bridge._pronunciation_delete(self.bridge_a, {"written_form": ""})
        for written, spoken in (("", "reading"), ("term", ""), ("x" * 501, "reading"), ("term", "y" * 1001)):
            with self.subTest(written=written[:8], spoken_length=len(spoken)):
                with self.assertRaises(ValueError):
                    self.save(self.bridge_a, written, spoken)
        self.assertEqual(["Mira"], [row["written_form"] for row in self.list(self.bridge_a)])

    def test_invalid_scope_is_rejected_instead_of_saved_as_unimplemented_metadata(self):
        with self.assertRaisesRegex(ValueError, "Choose Current book"):
            self.save(self.bridge_a, "Mira", "Mee-rah", scope="Everywhere")
        self.assertEqual([], self.list(self.bridge_a))

    def test_corrupt_global_dictionary_is_reported_and_not_overwritten(self):
        path = host._pronunciation_scope_path("global_library")
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "could not be read"):
            self.save(self.bridge_a, "Ryu", "Ree-yoo", scope="Global library")
        self.assertEqual("{broken", path.read_text(encoding="utf-8"))


    def test_effective_synthesis_rules_merge_scopes_with_book_series_global_precedence(self):
        settings = self.root / "settings"
        settings.mkdir(exist_ok=True)
        with patch.object(host, "settings_root", return_value=settings):
            host._write_pronunciation_store(host._pronunciation_scope_path("global_library"), [
                {"written_form": "NYC", "spoken_form": "Global City"},
                {"written_form": "Mira", "spoken_form": "Global Mira"},
                {"written_form": "GlobalOnly", "spoken_form": "Global Reading"},
                {"written_form": "Disabled", "spoken_form": "Global Reading"},
            ])
            host._write_pronunciation_store(host._pronunciation_scope_path("series", "Slime"), [
                {"written_form": "NYC", "spoken_form": "Series City"},
                {"written_form": "Mira", "spoken_form": "Series Mira"},
                {"written_form": "SeriesOnly", "spoken_form": "Series Reading"},
                {"written_form": "Disabled", "spoken_form": "Series Reading"},
            ])
            effective = host._effective_pronunciation_dictionary({
                "series": "Slime",
                "pronunciation_dictionary": [
                    {"written_form": "NYC", "spoken_form": "Book City", "enabled": True},
                    {"written_form": "Disabled", "spoken_form": "Ignored", "enabled": False},
                    {"written_form": "BookOnly", "spoken_form": "Book Reading", "enabled": True},
                ],
            })
        self.assertEqual(
            apply_pronunciation_dictionary("NYC Mira SeriesOnly GlobalOnly BookOnly Disabled", effective),
            "Book City Series Mira Series Reading Global Reading Book Reading Disabled",
        )

if __name__ == "__main__":
    unittest.main()
