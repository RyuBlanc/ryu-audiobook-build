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


    def test_local_ai_worker_returns_only_high_confidence_source_grounded_drafts(self):
        from unittest.mock import Mock, patch
        project = SimpleNamespace(
            folder=self.project_a,
            title="Series A",
            chapters=[SimpleNamespace(number=1,title="Chapter 1",text="Mira met Yamato. The common word is very.")],
        )
        bridge = self.bridge_a
        bridge._job_update = Mock()
        fake_brain = Mock()
        fake_brain.analyze_book.return_value = {"pronunciation":[
            {"written":"Yamato","spoken":"Yah-mah-toh","source_language":"Japanese","script":"Latin","ipa":"","reason":"Japanese name used repeatedly","confidence":0.94,"alternatives":["Yah-mah-toe"]},
            {"written":"Mira","spoken":"Mee-rah","source_language":"Japanese","script":"Latin","ipa":"","reason":"Already saved","confidence":0.98,"alternatives":[]},
            {"written":"very","spoken":"veh-ree","source_language":"Japanese","script":"Latin","ipa":"","reason":"ordinary English word","confidence":0.99,"alternatives":[]},
            {"written":"NotInBook","spoken":"Not-in-book","source_language":"Japanese","script":"Latin","ipa":"","reason":"Not present","confidence":0.99,"alternatives":[]},
            {"written":"LowConfidence","spoken":"Low","source_language":"Japanese","script":"Latin","ipa":"","reason":"Weak evidence","confidence":0.55,"alternatives":[]},
        ]}
        self.save(bridge,"Mira","Mee-rah")
        with patch("app.ai.brain.AudiobookBrain",return_value=fake_brain):
            host.PremiumV2Bridge._pronunciation_analysis_worker(bridge,"job-ai",project,{ "mira" })
        fake_brain.close.assert_called_once_with()
        update = bridge._job_update.call_args.kwargs
        self.assertEqual("completed",update["state"])
        self.assertEqual(1,len(update["result"]["suggestions"]))
        suggestion = update["result"]["suggestions"][0]
        self.assertEqual("Yamato",suggestion["written_form"])
        self.assertEqual("ai",suggestion["origin"])
        self.assertFalse(suggestion["enabled"])
        self.assertEqual("Japanese",suggestion["language"])
        self.assertEqual(0.94,suggestion["confidence"])
        self.assertEqual(["Yah-mah-toe"],suggestion["alternatives"])

    def test_manual_origin_is_persisted_and_preserved_during_enable_toggle(self):
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", origin="manual", enabled=False)
        row = self.list(self.bridge_a)[0]
        self.assertEqual("manual", row["origin"])
        self.assertFalse(row["enabled"])
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", origin=row["origin"], enabled=True)
        row = self.list(self.bridge_a)[0]
        self.assertEqual("manual", row["origin"])
        self.assertTrue(row["enabled"])

    def test_ai_origin_and_review_evidence_survive_edit_and_remain_disabled(self):
        self.save(self.bridge_a, "Rimuru", "Rimuru", origin="ai", enabled=False,
                  confidence=0.94, ipa="/ɾimɯɾɯ/", script="Latin",
                  reason="Japanese proper name", alternatives=["Rim-oo-roo"])
        self.save(self.bridge_a, "Rimuru Tempest", "Rimuru Tem-pest",
                  original_written_form="Rimuru", original_scope="Current book",
                  origin="ai", enabled=False)
        rows = self.list(self.bridge_a)
        self.assertEqual(1, len(rows))
        self.assertEqual("Rimuru Tempest", rows[0]["written_form"])
        self.assertEqual("ai", rows[0]["origin"])
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(0.94, rows[0]["confidence"])
        self.assertEqual("/ɾimɯɾɯ/", rows[0]["ipa"])
        self.assertEqual(["Rim-oo-roo"], rows[0]["alternatives"])

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

    def test_ai_suggestion_cannot_overwrite_or_reclassify_a_manual_entry(self):
        self.save(self.bridge_a,"Mira","Mee-rah",origin="manual",enabled=True)
        with self.assertRaisesRegex(ValueError,"AI suggestion cannot overwrite or reclassify"):
            self.save(self.bridge_a,"Mira","My-rah",origin="ai",enabled=False,confidence=0.99)
        rows=self.list(self.bridge_a)
        self.assertEqual(1,len(rows))
        self.assertEqual("manual",rows[0]["origin"])
        self.assertTrue(rows[0]["enabled"])
        self.assertEqual("Mee-rah",rows[0]["spoken_form"])

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

    def test_export_is_versioned_and_preserves_scope_origin_and_enabled_state(self):
        self.save(self.bridge_a, "Mira", "Mee-rah", origin="manual", enabled=True)
        self.save(self.bridge_a, "Yamato", "Yah-mah-toh", scope="Global library",
                  origin="ai", enabled=False, confidence=0.94, reason="Japanese name",
                  alternatives=["Yah-mah-toe"])
        self.save(self.bridge_a, "Rimuru", "Ree-moo-roo", scope="Series · Slime",
                  origin="manual", enabled=True)
        state = host.load_state(self.project_a)
        state["series"] = "Slime"
        host.save_state(self.project_a, state)
        exported = host.PremiumV2Bridge._pronunciation_export(self.bridge_a, {})
        self.assertEqual("ryu.pronunciation-dictionary", exported["schema"])
        self.assertEqual(1, exported["version"])
        entries = {(row["scope_type"], row["scope_id"], row["written_form"]): row
                   for row in exported["entries"]}
        self.assertIn(("current_book", "", "Mira"), entries)
        self.assertEqual(("global_library", ""), (
            entries[("global_library", "", "Yamato")]["scope_type"],
            entries[("global_library", "", "Yamato")]["scope_id"],
        ))
        self.assertEqual("ai", entries[("global_library", "", "Yamato")]["origin"])
        self.assertFalse(entries[("global_library", "", "Yamato")]["enabled"])
        self.assertEqual("Series · Slime", entries[("series", "Slime", "Rimuru")]["scope"])

    def test_import_preview_reports_conflicts_and_never_overwrites_until_confirmed(self):
        self.save(self.bridge_a, "Mira", "Mee-rah", origin="manual", enabled=True)
        document = {
            "schema": "ryu.pronunciation-dictionary",
            "version": 1,
            "entries": [
                {"written_form": "Mira", "spoken_form": "My-rah", "scope_type": "current_book",
                 "scope_id": "", "origin": "manual", "enabled": True},
                {"written_form": "Yamato", "spoken_form": "Yah-mah-toh", "scope_type": "current_book",
                 "scope_id": "", "origin": "ai", "enabled": False, "confidence": 0.94},
            ],
        }
        preview = host.PremiumV2Bridge._pronunciation_import(self.bridge_a, {"document": document})
        self.assertEqual(1, preview["conflict_count"])
        self.assertEqual(1, preview["new_count"])
        self.assertEqual(0, preview["imported"])
        self.assertEqual("Mee-rah", self.list(self.bridge_a)[0]["spoken_form"])
        applied = host.PremiumV2Bridge._pronunciation_import(
            self.bridge_a, {"document": document, "apply": True, "replace_conflicts": True}
        )
        rows = {row["written_form"]: row for row in self.list(self.bridge_a)}
        self.assertEqual(1, applied["imported"])
        self.assertEqual(1, applied["updated"])
        self.assertEqual("My-rah", rows["Mira"]["spoken_form"])
        self.assertEqual("manual", rows["Mira"]["origin"])
        self.assertEqual("Yah-mah-toh", rows["Yamato"]["spoken_form"])
        self.assertFalse(rows["Yamato"]["enabled"])

    def test_import_rejects_foreign_series_and_malformed_dictionary_without_mutation(self):
        self.save(self.bridge_a, "Mira", "Mee-rah")
        foreign_series = {
            "schema": "ryu.pronunciation-dictionary", "version": 1,
            "entries": [{"written_form": "Rimuru", "spoken_form": "Ree-moo-roo",
                         "scope_type": "series", "scope_id": "Other Series"}],
        }
        with self.assertRaisesRegex(ValueError, "active project series"):
            host.PremiumV2Bridge._pronunciation_import(self.bridge_a, {"document": foreign_series})
        malformed = {"schema": "unknown", "version": 1, "entries": []}
        with self.assertRaisesRegex(ValueError, "schema"):
            host.PremiumV2Bridge._pronunciation_import(self.bridge_a, {"document": malformed})
        self.assertEqual(["Mira"], [row["written_form"] for row in self.list(self.bridge_a)])


    def test_per_profile_pronunciation_matrix_results_are_persisted_and_scoped(self):
        results = [
            {"profile_name": "Narrator A", "provider": "piper", "status": "passed",
             "actual_duration_seconds": 9.8, "synthesis_seconds": 2.4, "total_seconds": 2.9,
             "real_time_factor": 0.245, "pronunciation_replacements": 1},
            {"profile_name": "Qwen Voice", "provider": "qwen", "status": "failed",
             "error": "Provider temporarily unavailable"},
        ]
        saved = host.PremiumV2Bridge._pronunciation_test_results_save(
            self.bridge_a,
            {"written_form": "Yamato", "scope": "Current book", "results": results},
        )
        self.assertEqual(2, saved["saved"])
        loaded = host.PremiumV2Bridge._pronunciation_test_results_get(
            self.bridge_a, {"written_form": "Yamato", "scope": "Current book"}
        )
        self.assertEqual(2, len(loaded["results"]))
        by_profile = {row["profile_name"]: row for row in loaded["results"]}
        self.assertEqual("passed", by_profile["Narrator A"]["status"])
        self.assertEqual(9.8, by_profile["Narrator A"]["actual_duration_seconds"])
        self.assertEqual(1, by_profile["Narrator A"]["pronunciation_replacements"])
        self.assertEqual("failed", by_profile["Qwen Voice"]["status"])
        self.assertEqual([], host.PremiumV2Bridge._pronunciation_test_results_get(
            self.bridge_b, {"written_form": "Yamato", "scope": "Current book"}
        )["results"])

    def test_per_profile_pronunciation_matrix_rejects_invalid_results(self):
        with self.assertRaisesRegex(ValueError, "profile"):
            host.PremiumV2Bridge._pronunciation_test_results_save(
                self.bridge_a,
                {"written_form": "Mira", "scope": "Current book",
                 "results": [{"profile_name": "", "provider": "piper", "status": "passed"}]},
            )
        with self.assertRaisesRegex(ValueError, "duration"):
            host.PremiumV2Bridge._pronunciation_test_results_save(
                self.bridge_a,
                {"written_form": "Mira", "scope": "Current book",
                 "results": [{"profile_name": "Narrator", "provider": "piper",
                              "status": "passed", "actual_duration_seconds": -1}]},
            )


if __name__ == "__main__":
    unittest.main()
