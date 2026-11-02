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

    def test_series_list_exposes_only_the_active_projects_matching_series(self):
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", scope="Series · Slime")
        self.save(self.bridge_a, "Rimuru", "Rim-oo-roo", scope="Series · Other")
        state_path = self.project_b / "state.json"
        state_path.write_text(json.dumps({"series":"Slime"}), encoding="utf-8")
        rows = self.list(self.bridge_b)
        self.assertEqual({"Slime"}, {row["scope_id"] for row in rows if row["scope_type"] == "series"})
        self.assertEqual("Ree-moo-roo", next(row["spoken_form"] for row in rows if row["scope_type"] == "series"))
        self.delete(self.bridge_b, "Rimuru", scope="Series · Slime")
        rows = self.list(self.bridge_b)
        self.assertEqual(set(), {row["scope_id"] for row in rows if row["scope_type"] == "series"})

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


    def test_manual_origin_is_persisted_and_preserved_during_enable_toggle(self):
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", origin="manual", enabled=False)
        row = self.list(self.bridge_a)[0]
        self.assertEqual("manual", row["origin"])
        self.assertFalse(row["enabled"])
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", origin=row["origin"], enabled=True)
        row = self.list(self.bridge_a)[0]
        self.assertEqual("manual", row["origin"])
        self.assertTrue(row["enabled"])

    def test_ai_origin_survives_edit_and_remains_disabled_until_enabled(self):
        self.save(self.bridge_a, "Rimuru", "Rimuru", origin="ai", enabled=False)
        self.save(self.bridge_a, "Rimuru Tempest", "Rimuru Tem-pest",
                  original_written_form="Rimuru", original_scope="Current book",
                  origin="ai", enabled=False)
        rows = self.list(self.bridge_a)
        self.assertEqual(1, len(rows))
        self.assertEqual("Rimuru Tempest", rows[0]["written_form"])
        self.assertEqual("ai", rows[0]["origin"])
        self.assertFalse(rows[0]["enabled"])

    def test_global_pronunciation_switch_bypasses_rules_without_deleting_them(self):
        with patch.object(host, "settings_root", return_value=self.settings):
            self.save(self.bridge_a, "Mira", "Mee-rah", enabled=True)
            before = host._effective_pronunciation_dictionary({"pronunciation_dictionary":[
                {"written_form":"Mira","spoken_form":"Mee-rah","enabled":True}
            ]})
            self.assertEqual("Mee-rah", apply_pronunciation_dictionary("Mira", before))
            result = host.PremiumV2Bridge._pronunciation_settings_save(self.bridge_a, {"enabled":False})
            self.assertFalse(result["enabled"])
            state = host.load_state(self.project_a)
            effective = host._effective_pronunciation_dictionary({
                **state, "pronunciation_dictionary":[
                    {"written_form":"Mira","spoken_form":"Mee-rah","enabled":True}
                ]
            })
            self.assertEqual([], effective)
            self.assertEqual("Mira", apply_pronunciation_dictionary("Mira", effective))
            listed = self.list(self.bridge_a)
            self.assertEqual("Mee-rah", listed[0]["spoken_form"])

    def test_edit_rejects_a_stale_original_identity_without_creating_a_new_row(self):
        self.save(self.bridge_a, "Mira", "Mee-rah")
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.save(
                self.bridge_a, "Mira Vale", "My-rah Vail",
                original_written_form="Missing original", original_scope="Current book"
            )
        self.assertEqual(["Mira"], [row["written_form"] for row in self.list(self.bridge_a)])

    def test_bulk_delete_removes_only_explicit_selected_scope_identities(self):
        self.save(self.bridge_a, "Mira", "Mee-rah")
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", scope="Global library")
        self.save(self.bridge_a, "Rimuru", "Series reading", scope="Series · Slime")
        state_path = self.project_a / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["series"] = "Slime"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = host.PremiumV2Bridge._pronunciation_delete_many(self.bridge_a, {"entries":[
            {"written_form":"Mira","scope":"Current book"},
            {"written_form":"Rimuru","scope":"Global library"}
        ]})
        self.assertEqual(2, result["deleted"])
        remaining = self.list(self.bridge_a)
        self.assertEqual({("Rimuru","series","Slime")}, {
            (row["written_form"],row["scope_type"],row["scope_id"])
            for row in remaining
        })

if __name__ == "__main__":
    unittest.main()
