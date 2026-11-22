from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
REGISTRY = ROOT / "app" / "core" / "character_library.py"
WORKBOOK = ROOT / "app" / "core" / "character_workbook.py"
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"


class CharacterWorkbookUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = HOST.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")
        cls.workbook = WORKBOOK.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_workbook_commands_are_registered_and_advertised(self):
        for command, handler in {
            "character.workbook.export": "_character_workbook_export",
            "character.workbook.import.preview": "_character_workbook_import_preview",
            "character.workbook.import.commit": "_character_workbook_import_commit",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', self.host)
            self.assertIn(f'"{command}": True', self.host)

    def test_export_import_controls_use_preview_then_explicit_commit(self):
        self.assertIn("Series Character Reference", self.workbook)
        self.assertIn("Known Alias", self.workbook)
        self.assertIn("reference_by_identity", self.workbook)
        self.assertIn("series_character_reference", self.host)
        self.assertIn("self._character_library_bootstrap()", self.host)
        self.assertIn("Export Chapter Workbook", self.html)
        self.assertIn("Import Completed Workbook", self.html)
        self.assertIn("character.workbook.import.preview", self.adapter)
        self.assertIn("character.workbook.import.commit", self.adapter)
        self.assertIn("window.confirm(prompt)", self.adapter)
        self.assertIn("await openAiCharacterReview(item)", self.adapter)
        self.assertIn("source:'ai', confidence:topConfidence", self.adapter)

    def test_workbook_actions_are_static_in_character_studio_header_and_delegated(self):
        page_start = self.html.index('<section class="page" id="characters">')
        metrics_start = self.html.index('<div class="grid metrics char-metrics">', page_start)
        header = self.html[page_start:metrics_start]
        self.assertIn('id="exportCharacterWorkbook"', header)
        self.assertIn('data-character-workbook-action="export"', header)
        self.assertIn('id="importCharacterWorkbook"', header)
        self.assertIn('data-character-workbook-action="import"', header)
        self.assertIn("function exportSelectedCharacterWorkbook()", self.adapter)
        self.assertIn("function importCompletedCharacterWorkbook()", self.adapter)
        self.assertIn("const workbookAction = button.closest('#characters [data-character-workbook-action]')", self.adapter)
        self.assertNotIn("ensureCharacterWorkbookControls", self.adapter)
        self.assertLess(
            self.adapter.index("installCharacterStudioHandlers();"),
            self.adapter.index("await call('app.get_info')"),
        )

    def test_outsourced_origin_is_supported_as_a_third_assignment_source(self):
        self.assertIn('{"manual", "ai", "outsourced"}', self.host)
        self.assertIn("assignment.source || '').trim().toLowerCase() === 'outsourced'", self.adapter)
        self.assertIn("confirmed-outsourced", self.adapter)
        self.assertIn("is-assigned-outsourced", self.adapter)

    def test_outsourced_visual_state_is_soft_white_without_replacing_existing_styles(self):
        self.assertIn("rgba(238,242,248,.055)", self.adapter)
        self.assertIn(".quick-character.outsourced", self.adapter)
        self.assertIn(".prediction-option.outsourced", self.adapter)
        self.assertIn(".ryu-assigned-dialogue-outsourced", self.adapter)
        self.assertIn(".ryu-assigned-dialogue-ai{background:rgba(236,160,45", self.adapter)
        self.assertIn(".ryu-assigned-dialogue-manual{background:rgba(36,190,122", self.adapter)

    def test_imported_characters_are_marked_in_both_assignment_pickers(self):
        self.assertIn('"character_origin": "outsourced"', self.host)
        self.assertIn('"imported_from_workbook": bool(record.get("imported_from_workbook"))', self.host)
        self.assertIn("item.item?.character_origin === 'outsourced'", self.adapter)
        self.assertIn("c.character_origin === 'outsourced'", self.adapter)

    def test_import_preview_lists_canonical_merge_and_create_changes(self):
        self.assertIn('"character_plan_total": len(plan.get("characters") or [])', self.host)
        self.assertIn('"plan_sha256": character_workbook_plan_fingerprint(plan)', self.host)
        self.assertIn('character_workbook_plan_fingerprint(plan) != session.get("plan_sha256")', self.host)
        self.assertIn("Review the updated merge plan before importing", self.host)
        self.assertIn('"plan_sha256": character_workbook_plan_fingerprint(plan)', self.host)
        self.assertIn('character_workbook_plan_fingerprint(plan) != session.get("plan_sha256")', self.host)
        self.assertIn("Review the updated merge plan before importing", self.host)
        self.assertIn("deleted_registry_rows=list_reusable_deleted_characters()", self.host)
        self.assertIn('book_title=str(getattr(project, "title", "") or "")', self.host)
        self.assertIn("Character identity plan", self.adapter)
        self.assertIn("remainingChanges", self.adapter)
        self.assertIn("only the first 24 are expanded above", self.adapter)

    def test_identity_variant_survives_cross_volume_sync_voice_assignment_and_import_commit(self):
        self.assertIn('"identity_variant": row.get("identity_variant") or ""', self.host)
        self.assertIn("registry_matches", self.host)
        self.assertIn("variant_conflicts", self.registry)
        self.assertIn("wrong_variant_matches", self.host)
        self.assertIn("cast_identity_candidates", self.host)
        self.assertIn("more than one series", self.host)

    def test_series_library_merge_and_aliases_are_not_limited_to_five(self):
        self.assertIn("def merge_imported_character_records(", self.registry)
        self.assertIn("merge_imported_character_records(series, plan[\"characters\"]", self.host)
        self.assertNotIn("if len(result) >= 5:", self.registry)
        self.assertNotIn('if str(alias).strip()][:5]', self.host)
        self.assertNotIn('str(item).strip()))[:5]', self.host)
        self.assertNotIn("if len(result) >= 5:", self.registry)
        self.assertIn('"imported_from_workbook": bool(record.get("imported_from_workbook"))', self.host)

    def test_failed_workbook_import_restores_live_project_and_file_snapshots(self):
        self.assertIn("chapter_memory_backup", self.host)
        self.assertIn("@_serialize_character_identity_state", self.host)
        transaction_tests = (ROOT / "tests" / "test_character_workbook_import_transaction.py").read_text(encoding="utf-8")
        self.assertIn("test_failed_save_rolls_back_library_files_and_live_chapter_assignments", transaction_tests)
        self.assertIn("test_commit_persists_character_identity_and_outsourced_dialogue", transaction_tests)
        self.assertIn("@_serialize_character_identity_state", self.host)
        transaction_tests = (ROOT / "tests" / "test_character_workbook_import_transaction.py").read_text(encoding="utf-8")
        self.assertIn("test_failed_save_rolls_back_library_files_and_live_chapter_assignments", transaction_tests)
        self.assertIn("test_commit_persists_character_identity_and_outsourced_dialogue", transaction_tests)
        self.assertIn("item.dialogue_assignments = assignments", self.host)
        self.assertIn("rollback_errors", self.host)
        self.assertIn("Could not restore Character Studio workbook import snapshot", self.host)

    def test_workbook_uses_standard_library_ooxml_and_revision_scoped_passages(self):
        self.assertIn("zipfile.ZipFile", self.workbook)
        self.assertIn("ryu.character-studio-workbook", self.workbook)
        self.assertIn("Chapter Revision", self.workbook)
        self.assertIn("Passage Count", self.workbook)
        self.assertIn("GPT Confidence (0–1)", self.workbook)
        self.assertIn("blank confidence is not accepted", self.workbook)
        self.assertIn("MAX_CHARACTER_NAME_LENGTH = 160", self.workbook)
        self.assertIn("MAX_CHARACTER_ALIAS_LENGTH = 160", self.workbook)
        self.assertIn("blank confidence is not accepted", self.workbook)
        self.assertIn("MAX_CHARACTER_NAME_LENGTH = 160", self.workbook)
        self.assertIn("MAX_CHARACTER_ALIAS_LENGTH = 160", self.workbook)
        self.assertIn("complete set of chapter passages", self.workbook)
        self.assertIn("not listed in Character Register", self.workbook)
        self.assertIn("protected Narrator assignment", self.workbook)
        self.assertIn("Passage ID", self.workbook)
        self.assertIn("Alias 31, Alias 32", self.workbook)
        self.assertIn("plan_character_workbook_import", self.host)


if __name__ == "__main__":
    unittest.main()
