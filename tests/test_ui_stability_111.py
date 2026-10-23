from __future__ import annotations

from pathlib import Path
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
        self.assertIn("self._refresh_timer.setInterval(120)", source)
        self.assertIn("self._state_cache =", source)
        self.assertIn("self._status_cache =", source)
        self.assertNotIn("completed = sum(project_status(project)", source)

    def test_import_studio_reports_real_worker_stages_and_resets_preview_on_new_source(self):
        source = (ROOT / "app/ui/import_page.py").read_text(encoding="utf-8")
        worker = source.split("class ImportPreviewWorker", 1)[1].split("class BookDropZone", 1)[0]
        page = source.split("class ImportPage", 1)[1]
        self.assertIn("self.progress.emit(10)", worker)
        self.assertIn("self.progress.emit(55)", worker)
        self.assertIn("self.progress.emit(90)", worker)
        self.assertIn('self.status.setText("Preparing import…")', page)
        self.assertIn("self.summary.setText", page)
        self.assertIn("self.progress.setValue(0)", page)
        self.assertNotIn("Continuing … characters", page)

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
