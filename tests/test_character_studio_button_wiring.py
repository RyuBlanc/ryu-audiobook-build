import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow

from app.ui import premium_v2_host as host


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"


class CharacterStudioButtonWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")
        cls.host_source = HOST.read_text(encoding="utf-8")

    def test_character_library_toolbar_buttons_and_selection_change_are_live(self):
        start = self.adapter.index("function ensureCharacterLibraryBulkControls()")
        end = self.adapter.index("function ensureCharacterLibraryViewControls()", start)
        block = self.adapter[start:end]
        for button_id in (
            "selectVisibleLibraryCharacters",
            "clearLibraryCharacterSelection",
            "moveSelectedLibraryCharacters",
        ):
            self.assertIn('id="' + button_id + '"', block)
            self.assertIn("$('" + button_id + "')?.addEventListener('click'", block)
        self.assertIn("grid.addEventListener('change', event =>", block)
        self.assertIn("event.target.closest('[data-select-library]')", block)
        self.assertIn("moveSelectedLibraryCharacters().catch(error => message(error?.message || String(error), true))", block)
        refresh_start = self.adapter.index("async function refreshCharacterLibrary()")
        refresh_end = self.adapter.index("async function refreshCharacterIdentityViews()", refresh_start)
        refresh = self.adapter[refresh_start:refresh_end]
        self.assertIn("ensureCharacterRecoveryButton();", refresh)
        self.assertIn("ensureCharacterLibraryBulkControls();", refresh)
        self.assertIn("updateCharacterLibraryBulkControls();", refresh)

    def test_character_library_import_and_add_buttons_have_one_capture_phase_owner(self):
        marker = "const add=e.target.closest('#addLibraryCharacter'), imp=e.target.closest('#importCharacterLibrary')"
        marker_index = self.adapter.index(marker)
        listener_start = self.adapter.rfind("document.addEventListener('click'", 0, marker_index)
        listener_end = self.adapter.index("}, true);", marker_index) + len("}, true);")
        capture_handler = self.adapter[listener_start:listener_end]
        self.assertIn("if(add){e.preventDefault();e.stopImmediatePropagation();openLibraryEditor(null);return;}", capture_handler)
        self.assertIn("if(imp){e.preventDefault();e.stopImmediatePropagation();importCharacterLibraryFile();return;}", capture_handler)
        self.assertIn("if(save&&libraryEditorActive)", capture_handler)
        self.assertIn("if(del&&libraryEditorActive)", capture_handler)
        self.assertTrue(capture_handler.rstrip().endswith("}, true);"))

        primary_start = self.adapter.index("function installCharacterStudioHandlers()")
        primary_end = self.adapter.index("function ", primary_start + len("function installCharacterStudioHandlers()"))
        primary = self.adapter[primary_start:primary_end]
        self.assertIn("event.stopImmediatePropagation();", primary)
        self.assertIn("button.id === 'exportCharacterLibrary'", primary)
        self.assertIn("button.id === 'importCharacterLibrary'", primary)
        self.assertIn("button.id === 'addLibraryCharacter'", primary)
        self.assertIn("button.id === 'characterWorkbookHelp'", primary)

    def test_character_library_card_actions_are_connected_to_real_actions(self):
        marker = "const add=e.target.closest('#addLibraryCharacter')"
        marker_index = self.adapter.index(marker)
        listener_start = self.adapter.rfind("document.addEventListener('click'", 0, marker_index)
        listener_end = self.adapter.index("}, true);", marker_index) + len("}, true);")
        capture_handler = self.adapter[listener_start:listener_end]
        for selector in (
            "[data-edit-library]",
            "[data-delete-library]",
            "[data-test-library]",
            "[data-character-studio]",
        ):
            self.assertIn(selector, capture_handler)
        self.assertIn("openLibraryEditor(libraryCharacters.find", capture_handler)
        self.assertIn("call('character_library.delete'", capture_handler)
        self.assertIn("call('voice.preview'", capture_handler)
        self.assertIn("openProjectWithPreservedDraft", capture_handler)

    def test_recovery_bin_buttons_have_click_change_and_backend_routes(self):
        start = self.adapter.index("function ensureCharacterRecoveryButton()")
        end = self.adapter.index("function updateCharacterLibraryBulkControls()", start)
        block = self.adapter[start:end]
        self.assertIn("button.id = 'openCharacterRecoveryBin'", block)
        self.assertIn("button.addEventListener('click', () => openCharacterRecoveryBin()", block)
        for selector in (
            "[data-close-character-recovery]",
            "[data-select-all-deleted-characters]",
            "[data-clear-deleted-selection]",
            "[data-purge-selected-characters]",
            "[data-purge-all-characters]",
            "[data-restore-character]",
        ):
            self.assertIn(selector, block)
        self.assertIn("modal.addEventListener('change', event =>", block)
        self.assertIn("event.target.closest('[data-select-deleted-character]')", block)
        for command in (
            "character_library.deleted.list",
            "character_library.restore",
            "character_library.deleted.purge_many",
            "character_library.deleted.clear_all",
        ):
            self.assertIn("call('" + command + "'", block)
        self.assertIn("showCharacterRecoveryError(error)", block)
        self.assertIn("feedback.textContent = reason", block)
        for command, handler in {
            "character_library.deleted.list": "_character_library_deleted_list",
            "character_library.restore": "_character_library_restore",
            "character_library.deleted.purge_many": "_character_library_deleted_purge_many",
            "character_library.deleted.clear_all": "_character_library_deleted_clear_all",
            "character_library.delete_many": "_character_library_delete_many",
        }.items():
            self.assertIn('"' + command + '": self.' + handler, self.host_source)
            self.assertIn('"' + command + '": True', self.host_source)

    def test_workbook_review_buttons_have_handlers_and_actionable_failure_feedback(self):
        start = self.adapter.index("function showCharacterWorkbookPreflightDialog(preview)")
        end = self.adapter.index("async function exportSelectedCharacterWorkbook()", start)
        block = self.adapter[start:end]
        for selector in (
            "[data-workbook-dialog-close]",
            "[data-workbook-import-partial]",
            "[data-workbook-review-confirm-speakers]",
            "[data-workbook-review-assign]",
            "[data-workbook-review-retry]",
        ):
            self.assertIn(selector, block)
        self.assertIn("call('character.workbook.import.commit'", block)
        self.assertIn("allow_partial:true", block)
        self.assertIn("call('chapter.dialogue.assign'", block)
        self.assertIn("speakerAssignmentSaved = true;", block)
        self.assertIn("Speaker saved; workbook recheck needs attention", block)
        self.assertIn("Workbook recheck failed", block)
        self.assertIn("No workbook changes were committed by this recheck.", block)

        confirmation_start = self.adapter.index("function confirmCharacterWorkbookImport(promptText)")
        confirmation_end = self.adapter.index("function showCharacterWorkbookPreflightDialog", confirmation_start)
        confirmation = self.adapter[confirmation_start:confirmation_end]
        self.assertIn("[data-workbook-confirm]", confirmation)
        self.assertIn("[data-workbook-cancel],[data-workbook-dialog-close]", confirmation)
        self.assertIn("finish(true)", confirmation)
        self.assertIn("finish(false)", confirmation)

    def test_workbook_header_and_character_library_buttons_are_present_and_routed(self):
        for button_id in (
            "exportCharacterWorkbook",
            "importCharacterWorkbook",
            "exportCharacterLibrary",
            "importCharacterLibrary",
            "addLibraryCharacter",
        ):
            self.assertIn('id="' + button_id + '"', self.html)
        primary_start = self.adapter.index("function installCharacterStudioHandlers()")
        primary_end = self.adapter.index("function ", primary_start + len("function installCharacterStudioHandlers()"))
        primary = self.adapter[primary_start:primary_end]
        for action in (
            "exportSelectedCharacterWorkbook()",
            "importCompletedCharacterWorkbook()",
            "exportCharacterLibraryFile()",
            "importCharacterLibraryFile()",
            "saveLibraryEditor()",
        ):
            self.assertIn(action, primary)


class CharacterRecoveryBridgeDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_bridge(self):
        window = QMainWindow()
        self.addCleanup(window.close)
        bridge = host.PremiumV2Bridge(window)
        self.addCleanup(bridge.deleteLater)
        bridge._character_library_bootstrap = lambda: None
        return bridge

    @staticmethod
    def recovery_record():
        return {
            "id": "recovery-ludivine",
            "series": "Silver Archive",
            "primary_name": "Ludivine Marie-Ange de la Tréfle",
            "aliases": ["Lady Ludivine"],
            "voice_name": "Saved Qwen Ludivine Voice",
            "notes": "Original character notes",
            "dialogue_sample": "I will protect the archive.",
            "deletion_reason": "Removed during cast cleanup",
            "deleted_at": "2026-11-20T10:00:00+00:00",
        }

    def dispatch(self, bridge, command, payload=None):
        response = json.loads(bridge.dispatch(command, json.dumps(payload or {})))
        self.assertTrue(response.get("success"), response)
        return response.get("data")

    def test_recovery_list_restore_and_purge_commands_execute_through_bridge(self):
        bridge = self.make_bridge()
        record = self.recovery_record()
        capabilities = bridge._capabilities({})
        for command in (
            "character_library.deleted.list",
            "character_library.restore",
            "character_library.deleted.purge_many",
            "character_library.deleted.clear_all",
        ):
            self.assertTrue(capabilities.get(command), command)

        with patch.object(host, "list_reusable_deleted_characters", return_value=[record]):
            listed = self.dispatch(bridge, "character_library.deleted.list")
        self.assertEqual(listed[0]["name"], "Ludivine Marie-Ange de la Tréfle")
        self.assertEqual(listed[0]["voice"], "Saved Qwen Ludivine Voice")
        self.assertEqual(listed[0]["deleted_at"], record["deleted_at"])

        restored_record = dict(record, _merged_from_recovery=False)
        with (
            patch.object(host, "restore_reusable_character", return_value=restored_record) as restore,
            patch.object(host, "list_reusable_characters", return_value=[record]),
        ):
            restored = self.dispatch(bridge, "character_library.restore", {"id":record["id"]})
        restore.assert_called_once_with(record["id"])
        self.assertTrue(restored["restored"])
        self.assertFalse(restored["merged"])
        self.assertEqual(restored["character"]["voice"], "Saved Qwen Ludivine Voice")

        with (
            patch.object(host, "purge_deleted_reusable_characters_many", return_value=[record]) as purge,
            patch.object(host, "list_reusable_deleted_characters", return_value=[]),
        ):
            purged = self.dispatch(bridge, "character_library.deleted.purge_many", {"ids":[record["id"]]})
        purge.assert_called_once_with([record["id"]])
        self.assertEqual(purged["purged"], 1)

        with (
            patch.object(host, "purge_deleted_reusable_characters_many", return_value=[record]) as clear_all,
            patch.object(host, "list_reusable_deleted_characters", return_value=[]),
        ):
            cleared = self.dispatch(bridge, "character_library.deleted.clear_all")
        clear_all.assert_called_once_with(None)
        self.assertEqual(cleared["purged"], 1)

    def test_bulk_move_to_recovery_executes_through_bridge(self):
        bridge = self.make_bridge()
        record = self.recovery_record()
        with (
            patch.object(host, "soft_delete_reusable_characters_many", return_value=[record]) as delete_many,
            patch.object(host, "list_reusable_characters", return_value=[]),
        ):
            moved = self.dispatch(bridge, "character_library.delete_many", {"ids":[record["id"]]})
        delete_many.assert_called_once_with([record["id"]])
        self.assertEqual(moved["deleted"], 1)

    def test_character_library_json_import_executes_through_bridge_and_preserves_voice_contract(self):
        bridge = self.make_bridge()
        record = self.recovery_record()
        with (
            patch.object(host, "import_reusable_character_records", return_value=[record]) as import_records,
            patch.object(host, "list_reusable_characters", return_value=[record]),
        ):
            imported = self.dispatch(
                bridge,
                "character_library.import",
                {"schema":"ryu.character-library", "version":1, "characters":[{"name":"Ludivine"}]},
            )
        import_records.assert_called_once()
        self.assertEqual(imported["imported"], 1)
        self.assertTrue(imported["local_voice_profiles_preserved"])


if __name__ == "__main__":
    unittest.main()
