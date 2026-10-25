from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiStabilityRegressions(unittest.TestCase):
    def test_dashboard_refresh_preserves_recent_row_identity_selection_and_scroll(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from app.ui.dashboard_page import DashboardPage

        app = QApplication.instance()
        self.assertIsNotNone(app)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = []
            for index, title in enumerate(("Alpha Recent Book", "Beta Recent Book")):
                folder = root / f"project-{index}"
                folder.mkdir()
                projects.append(
                    SimpleNamespace(
                        title=title,
                        folder=folder,
                        chapters=[object(), object()],
                        source_path=None,
                    )
                )

            with (
                patch("app.ui.dashboard_page.list_projects", return_value=projects),
                patch("app.ui.dashboard_page.load_state", return_value={}) as load_state_mock,
                patch("app.ui.dashboard_page.project_status", return_value=("Ready", "")),
            ):
                page = DashboardPage()
                page.resize(1040, 590)
                page.show()
                app.processEvents()
                page.refresh()
                app.processEvents()
                self.assertEqual(page.recent_list.count(), 2)

                selected_item = page.recent_list.item(1)
                selected_folder = str(selected_item.data(Qt.ItemDataRole.UserRole))
                selected_item.setData(Qt.ItemDataRole.UserRole + 1, "retain-this-row")
                page.recent_list.setCurrentRow(1)
                app.processEvents()

                scroll = page.scroll_area.verticalScrollBar()
                scroll.setValue(min(48, scroll.maximum()))
                previous_scroll = scroll.value()
                selected_project = next(p for p in projects if str(p.folder) == selected_folder)
                selected_project.title = "Renamed Selected Recent Book"

                page.refresh()
                app.processEvents()

                row = next(
                    i for i in range(page.recent_list.count())
                    if str(page.recent_list.item(i).data(Qt.ItemDataRole.UserRole)) == selected_folder
                )
                self.assertEqual(
                    page.recent_list.item(row).data(Qt.ItemDataRole.UserRole + 1),
                    "retain-this-row",
                    "the unchanged project list should update the existing QListWidgetItem in place",
                )
                self.assertEqual(
                    str(page.recent_list.currentItem().data(Qt.ItemDataRole.UserRole)),
                    selected_folder,
                )
                self.assertIn("Renamed Selected Recent Book", page.recent_list.item(row).text())
                self.assertEqual(scroll.value(), min(previous_scroll, scroll.maximum()))
                source = (ROOT / "app/ui/dashboard_page.py").read_text(encoding="utf-8")
                self.assertNotIn("self.recent_list.clear()", source)
                self.assertNotIn("self.recent_list.setCurrentRow(0)", source)
                page.close()

    def test_native_catalog_refresh_guard_restores_paint_and_scroll_after_failure(self):
        from app.ui.stable_refresh import stable_view_refresh
        from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QListWidget

        class RefreshWidget(QWidget):
            def __init__(self):
                super().__init__()
                layout = QVBoxLayout(self)
                self.rows = QListWidget()
                layout.addWidget(self.rows)
                self.calls = 0

            @stable_view_refresh
            def refresh(self):
                self.calls += 1
                self.rows.clear()
                for i in range(30):
                    self.rows.addItem(f"row {i}")
                raise RuntimeError("test refresh failure")

        app = QApplication.instance()
        self.assertIsNotNone(app)
        widget = RefreshWidget()
        widget.resize(340, 180)
        widget.show()
        for i in range(30):
            widget.rows.addItem(f"old row {i}")
        app.processEvents()
        scroll = widget.rows.verticalScrollBar()
        scroll.setValue(min(24, scroll.maximum()))
        expected_scroll = scroll.value()

        with self.assertRaisesRegex(RuntimeError, "test refresh failure"):
            widget.refresh()

        self.assertTrue(widget.updatesEnabled())
        self.assertEqual(widget.calls, 1)
        self.assertEqual(scroll.value(), min(expected_scroll, scroll.maximum()))
        widget.close()

    def test_native_catalog_refreshes_use_stable_view_guard(self):
        refresh_methods = (
            ("app/ui/dashboard_page.py", "refresh"),
            ("app/ui/library.py", "refresh"),
            ("app/ui/history_page.py", "refresh"),
            ("app/ui/audiobooks_page.py", "refresh"),
            ("app/ui/character_library.py", "refresh"),
            ("app/ui/voice_cast_page.py", "load_current_project"),
            ("app/ui/voice_cast_page.py", "refresh_profiles"),
            ("app/ui/models_page.py", "refresh"),
        )
        for relative_path, method in refresh_methods:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("from app.ui.stable_refresh import stable_view_refresh", source)
            self.assertRegex(
                source,
                r"@stable_view_refresh\s+def " + method + r"\(",
                f"{relative_path}.{method} is missing the stable-view guard",
            )

    def test_chapter_refresh_updates_rows_in_place_and_preserves_selection_and_scroll(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from app.chapters.detector import Chapter
        from app.ui.chapter_editor import ChapterEditorPage

        app = QApplication.instance()
        self.assertIsNotNone(app)
        chapters = [
            Chapter(index + 1, f"Chapter {index + 1}", f"Text for chapter {index + 1}")
            for index in range(30)
        ]
        page = ChapterEditorPage(chapters)
        page.resize(520, 260)
        page.show()
        app.processEvents()

        page.list.setCurrentRow(12)
        app.processEvents()
        item = page.list.item(12)
        item.setData(Qt.ItemDataRole.UserRole + 1, "retain-this-row")
        scroll = page.list.verticalScrollBar()
        scroll.setValue(min(32, scroll.maximum()))
        previous_scroll = scroll.value()

        page.editor.chapters[12].title = "Renamed Chapter 13"
        page.refresh()
        app.processEvents()

        self.assertEqual(page.list.currentRow(), 12)
        self.assertEqual(
            page.list.item(12).data(Qt.ItemDataRole.UserRole + 1),
            "retain-this-row",
            "refresh should update existing row items instead of clearing the list",
        )
        self.assertIn("Renamed Chapter 13", page.list.item(12).text())
        self.assertEqual(scroll.value(), min(previous_scroll, scroll.maximum()))
        page.close()

    def test_chapter_refresh_restores_signals_and_paint_state_after_bad_record(self):
        from PySide6.QtWidgets import QApplication
        from app.chapters.detector import Chapter
        from app.ui.chapter_editor import ChapterEditorPage

        class BrokenChapter:
            @property
            def number(self):
                raise RuntimeError("invalid chapter record")

        app = QApplication.instance()
        self.assertIsNotNone(app)
        page = ChapterEditorPage([Chapter(1, "Valid", "Valid chapter text")])
        page.show()
        app.processEvents()
        page.editor.chapters = [BrokenChapter()]

        with self.assertRaisesRegex(RuntimeError, "invalid chapter record"):
            page.refresh()

        self.assertTrue(page.list.updatesEnabled())
        self.assertFalse(page.list.signalsBlocked())
        self.assertTrue(page.updatesEnabled())
        page.close()

    def test_voice_profile_combo_refresh_preserves_rows_and_selection_without_clearing(self):
        from PySide6.QtCore import Qt, QEvent
        from PySide6.QtWidgets import QApplication, QComboBox
        from app.ui.stable_refresh import sync_combo_items_in_place

        app = QApplication.instance() or QApplication([])
        combo = QComboBox()
        combo.addItem("Alpha • Local", "alpha")
        combo.addItem("Beta • Qwen", "beta")
        combo.setItemData(1, "preserve-extra-role", Qt.ItemDataRole.UserRole + 1)
        combo.setCurrentIndex(1)

        sync_combo_items_in_place(
            combo,
            [("Alpha • Local", "alpha"), ("Beta • Qwen", "beta")],
            "beta",
        )

        self.assertEqual(combo.count(), 2)
        self.assertEqual(combo.currentData(), "beta")
        self.assertEqual(
            combo.itemData(1, Qt.ItemDataRole.UserRole + 1),
            "preserve-extra-role",
            "unchanged rows must not be destroyed/recreated during refresh",
        )
        self.assertFalse(combo.signalsBlocked())
        self.assertTrue(combo.updatesEnabled())
        combo.close()
        combo.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_voice_profile_combo_refresh_restores_state_when_an_item_update_fails(self):
        from PySide6.QtWidgets import QApplication, QComboBox
        from PySide6.QtCore import QEvent
        from app.ui.stable_refresh import sync_combo_items_in_place

        class FailingComboBox(QComboBox):
            def setItemText(self, index, text):
                raise TypeError("simulated item label update failure")

        app = QApplication.instance() or QApplication([])
        combo = FailingComboBox()
        combo.addItem("Existing", "existing")
        combo.show()
        app.processEvents()

        with self.assertRaisesRegex(TypeError, "simulated item label update failure"):
            sync_combo_items_in_place(combo, [(object(), "existing")], "existing")

        self.assertFalse(combo.signalsBlocked())
        self.assertTrue(combo.updatesEnabled())
        self.assertEqual(combo.count(), 1)
        combo.close()
        combo.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_generation_dropdown_refreshes_avoid_clear_and_use_shared_sync(self):
        generation = (ROOT / "app/ui/generation_page.py").read_text(encoding="utf-8")
        profiles = generation.split("def _load_profiles(", 1)[1].split(
            "def _metadata_history(", 1
        )[0]
        chapters = generation.split("def refresh_chapter_sources(", 1)[1].split(
            "def _update_overview(", 1
        )[0]

        self.assertIn("sync_combo_items_in_place(self.voice_profile", profiles)
        self.assertIn("sync_combo_items_in_place(self.preview_chapter", chapters)
        self.assertNotIn("self.voice_profile.clear()", profiles)
        self.assertNotIn("self.preview_chapter.clear()", chapters)
        self.assertIn("self._refresh_readiness()", profiles)
        self.assertIn("self._update_overview()", profiles)

    def test_native_character_studio_chapter_refresh_preserves_items_selection_and_scroll(self):
        from PySide6.QtCore import Qt, QEvent
        from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
        from app.chapters.detector import Chapter
        from app.ui.native_character_studio import NativeCharacterDialoguePanel

        app = QApplication.instance()
        if app is None:
            self.__class__._qt_app = QApplication([])
            app = self.__class__._qt_app
        host = QWidget()
        layout = QVBoxLayout(host)
        widget = QListWidget()
        layout.addWidget(widget)
        chapters = [Chapter(index + 1, f"Chapter {index + 1}", "Sample text") for index in range(40)]
        for chapter in chapters:
            item = QListWidgetItem(f"Chapter {chapter.number} · Old title")
            item.setData(Qt.ItemDataRole.UserRole, chapter.number)
            widget.addItem(item)
        widget.resize(240, 240)
        host.show()
        app.processEvents()
        widget.setCurrentRow(30)
        widget.item(30).setData(Qt.ItemDataRole.UserRole + 1, "keep-this-item")
        widget.verticalScrollBar().setValue(min(30, widget.verticalScrollBar().maximum()))
        previous_scroll = widget.verticalScrollBar().value()
        chapters[30].title = "Updated character chapter"
        harness = type("Harness", (), {"_rows_for_chapter": lambda _self, _number: []})()

        NativeCharacterDialoguePanel._fill_chapter_list(harness, widget, chapters, 31)
        app.processEvents()

        self.assertEqual(widget.count(), 40)
        self.assertEqual(widget.currentRow(), 30)
        self.assertIn("Updated character chapter", widget.item(30).text())
        self.assertEqual(widget.item(30).data(Qt.ItemDataRole.UserRole + 1), "keep-this-item")
        self.assertEqual(widget.verticalScrollBar().value(), min(previous_scroll, widget.verticalScrollBar().maximum()))
        self.assertTrue(widget.updatesEnabled())
        self.assertFalse(widget.signalsBlocked())
        host.close()
        host.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_native_character_story_renderer_skips_identical_html_and_keeps_same_chapter_scroll(self):
        from app.ui.native_character_studio import NativeCharacterDialoguePanel

        class FakeScrollBar:
            def __init__(self):
                self._value = 0
                self._maximum = 100

            def value(self):
                return self._value

            def maximum(self):
                return self._maximum

            def setValue(self, value):
                self._value = max(0, min(int(value), self._maximum))

        class CountingBrowser:
            def __init__(self):
                self.html_write_count = 0
                self.html = ""
                self._vertical = FakeScrollBar()
                self._horizontal = FakeScrollBar()

            def setHtml(self, html):
                self.html_write_count += 1
                self.html = html

            def verticalScrollBar(self):
                return self._vertical

            def horizontalScrollBar(self):
                return self._horizontal

        browser = CountingBrowser()
        harness = type("Harness", (), {"_story_render_hashes": {}})()
        long_html = "<html><body>" + ("story line<br>" * 300) + "</body></html>"
        NativeCharacterDialoguePanel._set_story_html(harness, browser, False, long_html, 1)
        browser.verticalScrollBar().setValue(40)
        previous_scroll = browser.verticalScrollBar().value()
        NativeCharacterDialoguePanel._set_story_html(harness, browser, False, long_html, 1)
        self.assertEqual(browser.html_write_count, 1, "identical story content should not reset the story document")
        changed_html = "<html><body>" + ("revised story line<br>" * 300) + "</body></html>"
        NativeCharacterDialoguePanel._set_story_html(harness, browser, False, changed_html, 1)
        self.assertEqual(browser.html_write_count, 2)
        self.assertEqual(browser.verticalScrollBar().value(), min(previous_scroll, browser.verticalScrollBar().maximum()))

    def test_chapter_refresh_does_not_overwrite_pending_unsaved_editor_text(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from app.chapters.detector import Chapter
        from app.ui.chapter_editor import ChapterEditorPage

        app = QApplication.instance()
        if app is None:
            self.__class__._qt_app = QApplication([])
            app = self.__class__._qt_app
        page = ChapterEditorPage([
            Chapter(1, "First", "Original first text"),
            Chapter(2, "Second", "Original second text"),
        ])
        page._autosave_timer.stop()
        page.text.setPlainText("Edited first text before auto-save fires")

        page.refresh()

        self.assertEqual(page.text.toPlainText(), "Edited first text before auto-save fires")
        self.assertEqual(page.editor.chapters[0].text, "Original first text")
        self.assertTrue(page._fields_dirty)
        page._autosave_timer.stop()
        page.close()
        page.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_switching_chapters_persists_previous_editor_buffer_before_loading_next(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from app.chapters.detector import Chapter
        from app.ui.chapter_editor import ChapterEditorPage

        app = QApplication.instance()
        if app is None:
            self.__class__._qt_app = QApplication([])
            app = self.__class__._qt_app
        persisted = []

        def on_autosave(chapters):
            persisted.append([chapter.text for chapter in chapters])
            return True

        page = ChapterEditorPage(
            [
                Chapter(1, "First", "Original first text"),
                Chapter(2, "Second", "Original second text"),
            ],
            on_autosave=on_autosave,
        )
        page._autosave_timer.stop()
        page.text.setPlainText("Edited first text before selection changes")
        page._autosave_timer.stop()
        page.list.setCurrentRow(1)

        self.assertEqual(page.editor.chapters[0].text, "Edited first text before selection changes")
        self.assertEqual(page.text.toPlainText(), "Original second text")
        self.assertTrue(persisted)
        self.assertEqual(persisted[0][0], "Edited first text before selection changes")
        self.assertFalse(page._fields_dirty)
        page._autosave_timer.stop()
        page.close()
        page.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

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

    def test_voice_studio_prototype_actions_are_removed_before_backend_binding(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        helper = source.split("function suppressLegacyVoicePreviewHandlers()", 1)[1].split(
            "function ensureStableStudioLayout()", 1
        )[0]
        # Cloning preserves the approved HTML markup but drops listeners added by
        # the prototype. Removing inline handlers prevents fake status/step changes.
        self.assertIn("original.cloneNode(true)", helper)
        self.assertIn("replacement.removeAttribute('onclick')", helper)
        self.assertIn("original.replaceWith(replacement)", helper)
        self.assertIn("replacement.addEventListener('click'", helper)
        self.assertIn("event.stopPropagation()", helper)
        for control in (
            "generatePreview", "playPreview", "stopPreview", "saveProfile",
            "saveOnly", "useNarrator", "assignCharacter",
        ):
            self.assertIn("'" + control + "'", helper)

        # The shield must run synchronously before the first await in wire().
        wire_start = source.split("async function wire()", 1)[1].split(
            "await call('app.get_info')", 1
        )[0]
        self.assertIn("suppressLegacyVoicePreviewHandlers();", wire_start)
        self.assertEqual(source.count("suppressLegacyVoicePreviewHandlers();"), 1)

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
