import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow

from app.ui import premium_v2_host as host


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
REGISTRY = ROOT / "app" / "core" / "character_library.py"
WORKBOOK = ROOT / "app" / "core" / "character_workbook.py"
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
CHAPTER_EDITOR = ROOT / "app" / "ui" / "chapter_editor.py"
DIALOGUE_MANAGER = ROOT / "app" / "ui" / "dialogue_manager.py"


class CharacterWorkbookUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = HOST.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")
        cls.workbook = WORKBOOK.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")
        cls.chapter_editor = CHAPTER_EDITOR.read_text(encoding="utf-8")
        cls.dialogue_manager = DIALOGUE_MANAGER.read_text(encoding="utf-8")
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_workbook_commands_are_registered_and_advertised(self):
        for command, handler in {
            "character.workbook.prompt.copy": "_character_workbook_prompt_copy",
            "character.workbook.export": "_character_workbook_export",
            "character.workbook.import.preview": "_character_workbook_import_preview",
            "character.workbook.import.commit": "_character_workbook_import_commit",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', self.host)
            self.assertIn(f'"{command}": True', self.host)

    def test_gpt_prompt_copy_command_copies_the_same_complete_book_prompt(self):
        clipboard = SimpleNamespace(setText=unittest.mock.Mock())
        window = QMainWindow()
        self.addCleanup(window.close)
        bridge = host.PremiumV2Bridge(window)
        self.addCleanup(bridge.deleteLater)
        with patch.object(host.QApplication, "clipboard", return_value=clipboard):
            response = json.loads(bridge.dispatch("character.workbook.prompt.copy", "{}"))
        self.assertTrue(response.get("success"), response)
        self.assertTrue(response["data"]["copied"])
        self.assertEqual(response["data"]["prompt_version"], "2.2")
        clipboard.setText.assert_called_once_with(host.complete_book_gpt_prompt())

    def test_workbook_manual_assignment_endpoint_accepts_sequential_multi_voice_mode(self):
        self.assertIn('{"single", "chorus", "sequential", "alternating"}', self.host)
        from app.chapters.assignment_utils import normalize_assignment
        assignment = normalize_assignment(
            {"start": 0, "end": 5, "text": "Hello", "source": "manual"},
            ["Mira", "Rina"], "sequential",
        )
        self.assertEqual(assignment["speakers"], ["Mira", "Rina"])
        self.assertEqual(assignment["multi_speaker_mode"], "sequential")

    def test_export_import_controls_use_preview_then_explicit_commit(self):
        self.assertIn("Series Character Reference", self.workbook)
        self.assertIn("Known Alias", self.workbook)
        self.assertIn("reference_by_identity", self.workbook)
        self.assertIn("series_character_reference", self.host)
        self.assertIn("self._character_library_bootstrap()", self.host)
        self.assertIn("Export Complete-Book GPT Workbook", self.html)
        self.assertIn("Import Completed Workbook", self.html)
        self.assertIn("character.workbook.import.preview", self.adapter)
        self.assertIn("character.workbook.import.commit", self.adapter)
        self.assertIn("confirmCharacterWorkbookImport(prompt)", self.adapter)
        self.assertIn("showCharacterWorkbookPreflightDialog(preview || {})", self.adapter)
        self.assertIn("await openAiCharacterReview(item)", self.adapter)
        self.assertIn("source:'ai', confidence:topConfidence", self.adapter)

    def test_workbook_preflight_review_is_scrollable_contextual_and_locks_background(self):
        self.assertIn("function openCharacterWorkbookDialog(", self.adapter)
        self.assertIn("overflow-y:auto", self.adapter)
        self.assertIn("overscroll-behavior:contain", self.adapter)
        self.assertIn("document.documentElement.style.overflow = 'hidden'", self.adapter)
        self.assertIn("document.body.style.overflow = 'hidden'", self.adapter)
        self.assertIn("data-workbook-review-assign", self.adapter)
        self.assertIn("data-workbook-import-partial", self.adapter)
        self.assertIn("Import verified entries", self.adapter)
        self.assertIn("data-workbook-review-confirm-speakers", self.adapter)
        self.assertIn("data-workbook-review-speaker-set", self.adapter)
        self.assertIn("preserve_existing_manual", self.adapter)
        self.assertIn("preserve_existing_manual", self.host)
        self.assertIn("partial_allowed", self.host)
        self.assertIn('"partial_ready": bool(plan.get("partial_ready"))', self.host)
        self.assertIn("assignment.visual_source || assignment.source", self.adapter)
        self.assertIn(".ryu-assigned-dialogue-outsourced{background:rgba(238,242,248,.055)", self.adapter)
        self.assertIn("Recheck the same workbook", self.adapter)
        self.assertIn("importCompletedCharacterWorkbook(String(preview.path))", self.adapter)
        self.assertIn("context_before", self.host)
        self.assertIn("context_after", self.host)
        self.assertIn('"character_options": character_options', self.host)
        self.assertIn('"can_manual_assign":', self.host)
        self.assertIn('passage_id:String(item.passage_id || \'\')', self.adapter)
        self.assertIn('chapter_revision:String(item.chapter_revision || \'\')', self.adapter)
        self.assertIn('normalized["passage_id"] = passage_id', self.host)
        self.assertIn('normalized["chapter_revision"] = canonical_revision', self.host)
        self.assertIn("stale_ai_overlaps", self.host)
        self.assertIn("saved_assignment_matches_current_passage", self.host)
        self.assertIn("Exact manual assignments are preserved.", self.workbook)
        self.assertIn("def resolve_workbook_passage", self.workbook)
        self.assertIn('"passage_rebases": passage_rebases', self.workbook)
        self.assertIn('"passage_mappings": passage_mappings', self.workbook)
        self.assertIn("verified_mapping_by_source_id", self.host)
        self.assertIn('plan.get("passage_mappings")', self.host)
        self.assertIn("source_id_counts.get(source_id) != 1", self.host)
        self.assertIn("workbook_rows_by_current_id", self.host)
        self.assertIn("unmatched_workbook_speakers", self.host)
        self.assertIn("unmatched_workbook_review_rows", self.host)
        self.assertNotIn('"unmatched_workbook_rows": unmatched_workbook_review_rows[:300]', self.host)
        self.assertIn("GPT workbook rows needing source reconciliation", self.adapter)
        self.assertIn("GPT suggestion — NOT APPLIED", self.adapter)
        self.assertIn("data-workbook-dialog-close>Done", self.adapter)
        self.assertIn("item.unmatched_workbook_speakers", self.adapter)
        self.assertIn("selectedValue !== '' && Number.isInteger(optionIndex)", self.adapter)
        self.assertIn("pointer-events:auto!important", self.adapter)
        self.assertIn("GPT Proposed Source Text", self.workbook)
        self.assertIn("GPT Text Correction Reason", self.workbook)
        self.assertIn("GPT source-text corrections to apply after confirmation", self.adapter)
        self.assertIn("rebase_rows_for_text_corrections", self.host)
        self.assertIn("text_corrections_applied", self.host)
        self.assertIn('"unmatched_workbook_rows": unmatched_workbook_review_rows[:50000]', self.host)
        self.assertIn('"text_corrections": list(plan.get("text_corrections") or [])[:50000]', self.host)
        self.assertIn("_is_reserved_character_workbook_role", self.host)
        self.assertIn("_character_workbook_export_aliases", self.host)
        self.assertIn('"proposed_text": str(stale_row.get("GPT Proposed Source Text") or "")', self.host)
        self.assertIn('"correction_reason": str(stale_row.get("GPT Text Correction Reason") or "")', self.host)
        self.assertIn("for speaker in speaker_names:", self.host)
        self.assertIn("proposedCorrections.map(row =>", self.adapter)
        self.assertIn("characterPlan.map(row =>", self.adapter)
        self.assertIn("row.proposed_text", self.adapter)
        self.assertIn("preview.character_plan_truncated ||", self.adapter)
        self.assertIn("String(row.source_text || '')", self.adapter)
        self.assertIn("String(row.proposed_text || '')", self.adapter)
        self.assertNotIn("proposedCorrections.slice(0, 30)", self.adapter)
        self.assertIn("character_workbook_source_correction_history", self.host)
        self.assertIn("source_correction_history", self.workbook)
        self.assertIn("Source Correction History", self.workbook)
        self.assertIn('"source_correction_history": list(state.get("character_workbook_source_correction_history") or [])[-5000:]', self.host)
        self.assertIn("Third Person · needs user identification", self.dialogue_manager)
        self.assertIn("Third Person · needs user identification", self.adapter)
        self.assertIn("Third Person", self.workbook)
        self.assertIn("reserved_placeholder", self.host)
        self.assertIn("third_person_pending", self.host)
        self.assertIn("needs_user_identification", self.host)
        self.assertIn("Speaker Roles", self.workbook)
        self.assertIn("passage_reclassifications", self.host)
        self.assertIn("Exact source reclassifications", self.adapter)

    def test_native_chapter_studio_exposes_check_dialogues_action(self):
        self.assertIn('QPushButton("Check dialogues")', self.chapter_editor)
        self.assertIn("check_dialogues_button.clicked.connect(self.check_dialogues)", self.chapter_editor)
        self.assertIn("def check_dialogues(self) -> None:", self.chapter_editor)
        self.assertIn('dialog.setWindowTitle("Check dialogues — speaker review")', self.chapter_editor)

    def test_import_preview_does_not_truncate_preflight_at_twenty_issues(self):
        self.assertNotIn('"issues": plan["issues"][:20]', self.host)
        self.assertIn('"issues": review_issues[:1000]', self.host)
        self.assertIn('"issues_truncated": len(review_issues) > 1000', self.host)
        self.assertIn("All preflight messages", self.adapter)

    def test_workbook_actions_are_static_in_character_studio_header_and_delegated(self):
        page_start = self.html.index('<section class="page" id="characters">')
        metrics_start = self.html.index('<div class="grid metrics char-metrics">', page_start)
        header = self.html[page_start:metrics_start]
        self.assertIn('id="exportCharacterWorkbook"', header)
        self.assertIn('data-character-workbook-action="export"', header)
        self.assertIn('id="importCharacterWorkbook"', header)
        self.assertIn('data-character-workbook-action="import"', header)
        self.assertIn("function exportSelectedCharacterWorkbook()", self.adapter)
        self.assertIn("async function importCompletedCharacterWorkbook(selectedPath = '')", self.adapter)
        self.assertIn("function installCharacterWorkbookHelpButton()", self.adapter)
        self.assertIn("characterWorkbookHelpText()", self.adapter)
        self.assertIn("characterWorkbookHelp", self.adapter)
        self.assertIn("character.workbook.prompt.copy", self.adapter)
        self.assertIn("GPT Prompt sheet", self.adapter)
        self.assertIn("button.closest('#characters [data-character-workbook-action]')", self.adapter)
        self.assertIn("button.closest('#exportCharacterWorkbook, #importCharacterWorkbook')", self.adapter)
        self.assertNotIn("ensureCharacterWorkbookControls", self.adapter)
        self.assertLess(
            self.adapter.index("installCharacterStudioHandlers();"),
            self.adapter.index("await call('app.get_info')"),
        )


    def test_complete_book_workbook_is_v2_and_routes_all_chapters_through_one_safe_import(self):
        self.assertIn("def create_complete_book_character_workbook_bytes(", self.workbook)
        self.assertIn("def plan_complete_book_character_workbook_import(", self.workbook)
        self.assertIn('"Workbook Version", 2', self.workbook)
        self.assertIn('"Export Scope", "complete_book"', self.workbook)
        self.assertIn("Chapter Register", self.workbook)
        self.assertIn("Chapter Context", self.workbook)
        self.assertIn("Series Character Reference", self.workbook)
        self.assertIn("Included in This Book?", self.workbook)
        self.assertIn("context_sha256", self.workbook)
        self.assertIn("plan_complete_book_character_workbook_import(", self.host)
        self.assertIn("def _character_workbook_export_complete_book(", self.host)
        self.assertIn("def _character_workbook_book_snapshot(", self.host)
        self.assertIn("assignments_by_chapter", self.host)
        self.assertIn("target_chapter.dialogue_assignments = sorted(", self.host)
        self.assertIn("scope:'book'", self.adapter)
        self.assertIn("Complete book · ", self.adapter)
        self.assertIn("Existing character voice profiles will be preserved.", self.adapter)
        self.assertIn("voice needs assignment after import", self.adapter)
        self.assertIn("Chapter coverage:", self.adapter)
        self.assertIn("Speaker assignment summary:", self.adapter)
        self.assertIn('"assignment_summary": assignment_summary', self.host)
        self.assertIn('"chapters": chapter_preview', self.host)
        self.assertIn("Export Complete-Book GPT Workbook", self.html)
        self.assertIn("GPT Prompt Version", self.workbook)
        self.assertIn("complete_book_gpt_prompt()", self.workbook)
        self.assertIn('"character_register": character_register', self.host)
        self.assertIn('character.get("aliases")', self.host)
        self.assertIn('"full_name": canonical_name', self.host)
        self.assertIn('character_series.casefold() != series.casefold()', self.host)



    def test_character_library_has_portable_export_and_add_character_uses_a_valid_series(self):
        library_start = self.html.index('<section class="character-library-zone" id="characterLibraryZone">')
        library_end = self.html.index('<section class="page" id="import">', library_start)
        library_header = self.html[library_start:library_end]
        self.assertIn('id="exportCharacterLibrary"', library_header)
        self.assertIn('id="importCharacterLibrary"', library_header)
        self.assertIn('id="addLibraryCharacter"', library_header)
        self.assertIn("voice model files, local profile ids and hardware-specific settings stay on this pc", library_header.lower())
        self.assertIn('"character_library.export": self._character_library_export', self.host)
        self.assertIn('"character_library.export": True', self.host)
        self.assertIn("def _character_library_export_document(", self.host)
        self.assertIn("voice_assets_included", self.host)
        self.assertIn("function exportCharacterLibraryFile()", self.adapter)
        self.assertIn("character_library.export", self.adapter)
        self.assertIn("reservedFilters", self.adapter)
        self.assertIn("seriesSelect.value = '__new_series__'", self.adapter)
        self.assertIn("Character Library editor could not be opened", self.adapter)
        self.assertIn("button.id === 'addLibraryCharacter'", self.adapter)
        self.assertIn("button.id === 'exportCharacterLibrary'", self.adapter)
        self.assertIn("button.id === 'importCharacterLibrary'", self.adapter)
        self.assertIn("button.id === 'saveCharacterProfile' && libraryEditorActive", self.adapter)
        self.assertIn("const payload=Array.isArray(data)?{characters:data}:data", self.adapter)
        self.assertIn("This Ryu Character Library export version is not supported.", self.host)
        self.assertIn("import_reusable_character_records(incoming)", self.host)
        self.assertIn("def import_character_library_records(", self.registry)
        self.assertIn("All series are applied to a staged copy", self.registry)
        self.assertIn("Deliberately do not update voice_name here", self.registry)
        self.assertIn('"local_voice_profiles_preserved": True', self.host)


    def test_character_editor_modal_is_hoisted_out_of_hidden_character_studio_page(self):
        character_page_start = self.html.index('<section class="page" id="characters">')
        pronunciation_page_start = self.html.index('<section class="page" id="pronunciation">', character_page_start)
        modal_start = self.html.index('id="characterEditorModal"')
        library_start = self.html.index('id="characterLibraryZone"')
        library_end = self.html.index('<section class="page" id="import">', library_start)
        self.assertLess(character_page_start, modal_start)
        self.assertLess(modal_start, pronunciation_page_start)
        self.assertLess(library_start, self.html.index('id="addLibraryCharacter"', library_start))
        self.assertLess(self.html.index('id="addLibraryCharacter"', library_start), library_end)
        self.assertIn("function ensureCharacterEditorModalHost()", self.adapter)
        self.assertIn("document.body.appendChild(modal)", self.adapter)
        self.assertIn("const modal = ensureCharacterEditorModalHost();", self.adapter)
        editor_start = self.adapter.index("function openLibraryEditor(c)")
        editor_end = self.adapter.index("async function saveLibraryEditor()", editor_start)
        self.assertIn("ensureCharacterEditorModalHost();", self.adapter[editor_start:editor_end])
        self.assertIn("button.id === 'addLibraryCharacter'", self.adapter)



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
        self.assertIn("def resolve_workbook_passage", self.workbook)
        self.assertIn("no current passage has the same exact source text and offsets", self.workbook)
        self.assertIn('"passage_rebases": passage_rebases', self.workbook)
        self.assertIn("not listed in Character Register", self.workbook)
        self.assertIn("protected Narrator assignment", self.workbook)
        self.assertIn("Passage ID", self.workbook)
        self.assertIn("Alias 31, Alias 32", self.workbook)
        self.assertIn("plan_character_workbook_import", self.host)







    def test_workbook_export_dispatch_uses_window_parent_and_writes_selected_file(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-export-dialog-") as temp:
            destination = Path(temp) / "GPT_Completed_Book.xlsx"
            window = QMainWindow()
            self.addCleanup(window.close)
            bridge = host.PremiumV2Bridge(window)
            self.addCleanup(bridge.deleteLater)
            project = SimpleNamespace(title="GPT Workbook Test")
            book_chapters = [{
                "chapter_id": "chapter-001",
                "chapter_number": 1,
                "chapter_title": "Chapter 1",
                "chapter_revision": "revision-1",
                "current_passages": [],
                "current_assignments": [],
            }]
            bridge._active_project = lambda: project
            bridge._character_workbook_book_snapshot = lambda _project: ({}, "Test Series", book_chapters)
            bridge._character_library_bootstrap = lambda: None
            with (
                patch.object(host, "list_reusable_characters", return_value=[]),
                patch.object(host, "create_complete_book_character_workbook_bytes", return_value=b"workbook-fixture"),
                patch.object(
                    host.QFileDialog, "getSaveFileName",
                    return_value=(str(destination), "Excel Workbook (*.xlsx)"),
                ) as save_dialog,
            ):
                response = json.loads(bridge.dispatch("character.workbook.export", '{"scope":"book"}'))

            self.assertTrue(response.get("success"), response)
            self.assertEqual(Path(response["data"]["path"]), destination.resolve())
            self.assertEqual(destination.read_bytes(), b"workbook-fixture")
            self.assertIs(save_dialog.call_args.args[0], window)
            self.assertIsInstance(save_dialog.call_args.args[0], QMainWindow)

    def test_workbook_import_preview_dispatch_uses_window_parent_and_returns_review_plan(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-import-dialog-") as temp:
            source = Path(temp) / "GPT_Completed_Book.xlsx"
            source.write_bytes(b"workbook-fixture")
            window = QMainWindow()
            self.addCleanup(window.close)
            bridge = host.PremiumV2Bridge(window)
            self.addCleanup(bridge.deleteLater)
            project = SimpleNamespace(folder=Path(temp), title="GPT Workbook Test")
            chapter = SimpleNamespace(number=1, title="Chapter 1")
            document = {
                "sha256": "fixture-sha256",
                "info": {"Export ID": "fixture-export-id"},
                "dialogue_rows": [],
            }
            plan = {
                "ready": True,
                "issues": [],
                "summary": {"matched_characters": 1, "dialogue_assignments": 1},
                "assignments": [{"speaker": "Mira", "chapter_number": 1}],
                "characters": [{
                    "canonical_name": "Mira",
                    "identity_variant": "",
                    "action": "merge",
                    "aliases_to_add": ["Captain Mira"],
                    "existing_voice_name": "Mira Voice",
                }],
                "scope": "book",
                "book_revision": "book-revision-1",
                "chapters": [{"chapter_id": "chapter-001"}],
                "chapter_assignments": [],
            }
            bridge._active_project = lambda: project
            bridge._character_workbook_import_plan = lambda _project, _document: ({}, "Test Series", chapter, plan)
            with (
                patch.object(
                    host.QFileDialog, "getOpenFileName",
                    return_value=(str(source), "Excel Workbook (*.xlsx)"),
                ) as open_dialog,
                patch.object(host, "read_character_workbook", return_value=document),
            ):
                response = json.loads(bridge.dispatch("character.workbook.import.preview", "{}"))

            self.assertTrue(response.get("success"), response)
            self.assertTrue(response["data"]["ready"])
            self.assertEqual(response["data"]["scope"], "book")
            self.assertEqual(response["data"]["assignment_summary"][0]["canonical_name"], "Mira")
            self.assertIs(open_dialog.call_args.args[0], window)
            self.assertIsInstance(open_dialog.call_args.args[0], QMainWindow)

    def test_workbook_dialog_parent_falls_back_to_none_for_non_widget_parent(self):
        owner = object()
        bridge_like = SimpleNamespace(parent=lambda: owner)

        self.assertIsNone(host.PremiumV2Bridge._character_workbook_dialog_parent(bridge_like))

    def test_complete_book_workbook_uses_reliable_qt_file_dialogs_and_routes_by_button_id(self):
        self.assertIn("options=QFileDialog.Option.DontUseNativeDialog", self.host)
        self.assertIn("def _character_workbook_dialog_parent(self) -> QWidget | None:", self.host)
        self.assertEqual(self.host.count("self._character_workbook_dialog_parent()"), 3)
        self.assertNotIn('QFileDialog.getSaveFileName(\n            self, "Export Complete-Book', self.host)
        self.assertNotIn('QFileDialog.getOpenFileName(\n            self, "Import GPT Character', self.host)
        self.assertIn("original_resolved = original.resolve()", self.host)
        self.assertIn("destination_resolved = destination.resolve()", self.host)
        self.assertIn("will not be overwritten", self.host)
        self.assertIn("#exportCharacterWorkbook, #importCharacterWorkbook", self.adapter)
        self.assertIn("Workbook export failed.", self.adapter)
        self.assertIn("Workbook import failed.", self.adapter)
        self.assertIn("showCharacterWorkbookMessageDialog('Workbook imported successfully', confirmation)", self.adapter)
        self.assertNotIn("window.alert(confirmation)", self.adapter)
        self.assertIn("Complete-book workbook saved", self.adapter)
        self.assertIn("character.workbook.import.preview", self.adapter)
        self.assertIn("character.workbook.import.commit", self.adapter)

    def test_character_studio_and_analyze_book_ai_refresh_from_active_library_only(self):
        self.assertIn("reconcile_project_character_cast", self.host)
        self.assertIn("character_library_exclusion_keys", self.host)
        self.assertIn('state["character_library_exclusions"] = exclusions', self.host)
        self.assertIn("hydrate_existing_projects = not path.is_file()", self.host)
        self.assertIn("if hydrate_existing_projects:", self.host)
        self.assertIn("async function refreshCharacterIdentityViews()", self.adapter)
        self.assertIn("await refreshCharacterIdentityViews()", self.adapter)
        self.assertIn("character_library_exclusions", self.host)



    def test_chapter_studio_dialogue_check_is_source_backed_and_supports_exact_narrator_splits(self):
        self.assertIn("Check dialogues", self.adapter)
        self.assertIn("fetchChapterDialogueCheck", self.adapter)
        self.assertIn("character.dialogue.index.get", self.adapter)
        self.assertIn("data-chapter-check-selection-narrator", self.adapter)
        self.assertIn("data-chapter-check-selection-speaker", self.adapter)
        self.assertIn("Mark as Narrator", self.adapter)
        self.assertIn("No overlapping offsets", self.adapter)
        self.assertIn("passage_id:String(window.ryuPremiumPendingDialogueCanonicalId || '')", self.adapter)
        self.assertIn("chapter_revision:String(window.ryuPremiumPendingDialogueRevision || '')", self.adapter)
        self.assertIn("narrator_only", self.host)
        self.assertIn("Narrator classification is an explicit manual review action.", self.host)
        self.assertIn("thirdPersonPending", self.adapter)
        self.assertIn("needs user identification", self.adapter)
        self.assertIn("third_person_pending", self.dialogue_manager)
        self.assertIn("Third Person · needs user identification", self.dialogue_manager)
        self.assertIn('if key == "third person":', self.host)
        self.assertIn('"third_person_pending"] = True', self.host)
        self.assertIn('speakers[0].casefold() not in {"narrator", "third person"}', self.host)

    def test_workbook_preflight_options_include_register_only_characters_and_keep_aliases(self):
        self.assertIn('plan.get("characters") or []', self.host)
        self.assertIn("pending_workbook_entry", self.host)
        self.assertIn("from this workbook’s Character Register", self.adapter)
        self.assertIn("selected.aliases || []", self.adapter)
        self.assertIn("preferredAliases = []", self.adapter)


if __name__ == "__main__":
    unittest.main()
