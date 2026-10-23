from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiStabilityRegressions(unittest.TestCase):
    def test_page_navigation_avoids_opacity_effects_and_keeps_handlers(self):
        source = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        transition = source.split("def _show_page", 1)[1].split("def _sidebar_item_clicked", 1)[0]
        self.assertIn("self.stack.setCurrentWidget(widget)", transition)
        self.assertNotIn("QGraphicsOpacityEffect", transition)
        self.assertNotIn("animation.start()", transition)
        self.assertIn("def _sidebar_item_clicked", source)
        self.assertIn("def _open_generation_feature", source)
        self.assertIn("def _refresh_generation_context(self) -> None:", source)
        self.assertIn("def _install_generation_feature_pages(", source)
        self.assertIn("def _save_sound_preset(", source)

    def test_library_search_is_debounced_and_status_is_cached_per_refresh(self):
        source = (ROOT / "app/ui/library.py").read_text(encoding="utf-8")
        self.assertIn("self._refresh_timer.setInterval(180)", source)
        self.assertIn("_project_data_cache", source)
        self.assertIn("_file_signature", source)
        self.assertIn("_resolve_output_path", source)
        self.assertIn("self.refresh(force_catalog=False)", source)
        self.assertIn("self.status_filter.blockSignals(True)", source)
        self.assertIn("previous_folder = str(previous_item.data", source)
        self.assertIn("self._state_cache =", source)
        self.assertIn("self._status_cache =", source)
        self.assertNotIn("completed = sum(project_status(project)", source)

    def test_import_studio_reports_real_worker_stages_and_resets_preview_on_new_source(self):
        source = (ROOT / "app/ui/import_page.py").read_text(encoding="utf-8")
        worker = source.split("class ImportPreviewWorker", 1)[1].split("class BookDropZone", 1)[0]
        page = source.split("class ImportPage", 1)[1]
        self.assertIn("self.progress.emit(-1)", worker)
        self.assertIn("Reading {self.source_path.name}", worker)
        self.assertIn("Detecting chapters in {self.source_path.name}", worker)
        self.assertIn("self.progress.setVisible(False)", page)
        self.assertIn("self.progress.setRange(0, 0)", page)
        self.assertIn("def project_created(", page)
        self.assertIn("def clear_if_source_deleted(", page)
        self.assertNotIn("self.progress.emit(10)", worker)
        self.assertNotIn("self.progress.emit(55)", worker)
        self.assertNotIn("self.progress.emit(90)", worker)
        self.assertNotIn("Continuing … characters", page)

    def test_failed_audio_playback_does_not_toggle_shell_or_hide_the_error(self):
        workflow = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        player_page = (ROOT / "app/ui/audiobooks_page.py").read_text(encoding="utf-8")
        source_changed = workflow.split("def _mini_source_changed", 1)[1].split("def _mini_playback_error", 1)[0]
        state_changed = workflow.split("def _mini_playback_state_changed", 1)[1].split("def _toggle_mini_playback", 1)[0]
        error_handler = workflow.split("def _mini_playback_error", 1)[1].split("def _hide_mini_player", 1)[0]
        self.assertNotIn("setVisible(True)", source_changed)
        self.assertIn("if playing:", state_changed)
        self.assertIn("self._set_mini_player_visible(True)", state_changed)
        self.assertNotIn("if not self.audiobooks_page.player.source().isEmpty():", state_changed)
        self.assertIn("self._set_mini_player_visible(False)", error_handler)
        self.assertIn("player.errorOccurred.connect(self._mini_playback_error)", workflow)
        self.assertIn("self.player.errorOccurred.connect(self._playback_error)", player_page)
        self.assertIn("Try in Default Player", player_page)
        self.assertIn("self.external_play_button.setVisible(True)", player_page)
        player_error = player_page.split("def _playback_error", 1)[1].split("def _open_in_default_player", 1)[0]
        self.assertNotIn("setVisible(", player_error)
        self.assertIn("QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))", player_page)

    def test_library_status_resolves_project_relative_output_paths(self):
        from app.ui.library import project_status

        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            output = folder / "exports" / "legacy-book.m4b"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"valid non-empty fixture")
            project = SimpleNamespace(
                title="Legacy Book",
                folder=folder,
                chapters=[object()],
                source_path=None,
            )
            status, resolved = project_status(
                project,
                {"status": "completed", "output_path": "exports/legacy-book.m4b"},
            )
            self.assertEqual(status, "Completed")
            self.assertEqual(Path(resolved), output.resolve())

    def test_playback_state_machine_does_not_show_mini_player_until_playing(self):
        from app.ui.workflow import ProjectWorkflow

        source = Mock()
        source.isEmpty.return_value = False
        source.toLocalFile.return_value = r"C:\\Audiobooks\\old.m4b"
        workflow = SimpleNamespace(
            audiobooks_page=SimpleNamespace(now_playing=SimpleNamespace(text=lambda: "Old audiobook")),
            mini_title=Mock(),
            mini_player_bar=Mock(),
            mini_play_button=Mock(),
            _mini_player_dismissed=True,
            _set_mini_player_visible=Mock(),
        )
        ProjectWorkflow._mini_source_changed(workflow, source)
        workflow._set_mini_player_visible.assert_not_called()
        self.assertFalse(workflow._mini_player_dismissed)

        # Stopped is the common terminal state for an unsupported/corrupt file.
        ProjectWorkflow._mini_playback_state_changed(workflow, object())
        workflow._set_mini_player_visible.assert_not_called()

        ProjectWorkflow._mini_playback_error(workflow, object(), "decoder failed")
        workflow._set_mini_player_visible.assert_called_once_with(False)

    def test_import_progress_uses_indeterminate_real_stages_and_clears_deleted_latest_source(self):
        page = (ROOT / "app/ui/import_page.py").read_text(encoding="utf-8")
        self.assertIn("self.progress.setRange(0, 0)", page)
        self.assertIn("self.progress.setVisible(False)", page)
        self.assertIn('self.info.setText(f"Latest import: {path.name}")', page)
        self.assertIn("def project_created(", page)
        self.assertIn("def project_creation_failed(", page)
        self.assertIn("def clear_if_source_deleted(", page)

    def test_character_library_is_live_series_data_with_edit_and_recovery(self):
        workflow = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        page = (ROOT / "app/ui/character_library.py").read_text(encoding="utf-8")
        store = (ROOT / "app/core/character_library.py").read_text(encoding="utf-8")
        cast = (ROOT / "app/ui/voice_cast_page.py").read_text(encoding="utf-8")
        self.assertIn("CharacterLibraryPage", workflow)
        self.assertIn('elif name == "Character Library":', workflow)
        self.assertIn("def sync_characters(", store)
        self.assertIn("def soft_delete_character(", store)
        self.assertIn("def restore_character(", store)
        self.assertIn("self.series_edit = QLineEdit()", cast)
        self.assertIn("self._sync_character_library()", cast)
        self.assertIn("QLineEdit(value)", page)
        self.assertIn("def preview_voice(", page)
        self.assertIn("def _save_row(", page)
        self.assertIn("Recovery Bin", page)

    def test_library_deletion_keeps_history_pronunciations_and_shared_characters(self):
        project = (ROOT / "app/core/project.py").read_text(encoding="utf-8")
        history = (ROOT / "app/core/project_history.py").read_text(encoding="utf-8")
        library = (ROOT / "app/ui/library.py").read_text(encoding="utf-8")
        self.assertIn("record_project_deletion(", project)
        self.assertIn("_preserve_project_pronunciations(state)", project)
        self.assertIn("output_path.unlink()", project)
        self.assertIn("shutil.rmtree(folder)", project)
        self.assertIn("def load_deleted_project_records(", history)
        self.assertIn("load_deleted_project_records()", (ROOT / "app/ui/history_page.py").read_text(encoding="utf-8"))
        self.assertIn("QListWidget.SelectionMode.ExtendedSelection", library)
        self.assertIn("on_before_delete", library)
        self.assertIn("on_deleted", library)

    def test_application_version_remains_111(self):
        source = (ROOT / "app/version.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "1.1.1"', source)


if __name__ == "__main__":
    unittest.main()
