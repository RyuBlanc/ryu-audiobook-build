from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QMenu,
    QWidget,
    QProgressBar,
    QInputDialog,
    QSizePolicy,
)
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.documents.parser import remove_page_noise
from app.ui.character_review import CharacterReviewDialog
from app.ui.dialogue_assignment import DialogueAssignmentDialog
from app.ui.dialogue_manager import DialogueAssignmentManagerDialog
from app.chapters.dialogue import dialogue_segment_for_selection
from app.chapters.assignment_utils import build_book_character_registry, normalize_assignment, format_character_registry_entry
from app.ai.brain import AudiobookBrain, _numeric_score



class AudiobookAIWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)

    def __init__(self, project_folder, chapters):
        super().__init__()
        self.project_folder = project_folder
        self.chapters = chapters

    def run(self):
        brain = None
        try:
            brain = AudiobookBrain(self.project_folder)
            def update(fraction, message):
                self.progress.emit(float(fraction), message)
            self.finished_ok.emit(brain.analyze_book(self.chapters, progress=update))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if brain is not None:
                brain.close()

class ChapterEditorPage(QWidget):
    def __init__(self, chapters: list[Chapter], on_save=None, on_rename_book=None, on_redetect=None, project_folder=None) -> None:
        super().__init__()
        cleaned = [
            Chapter(ch.number, ch.title, remove_page_noise(ch.text), list(getattr(ch, "dialogue_assignments", [])))
            for ch in chapters
        ]
        self.editor = ChapterEditor(cleaned)
        self.on_save = on_save
        self.on_rename_book = on_rename_book
        self.on_redetect = on_redetect
        self.project_folder = project_folder
        self.ai_worker: AudiobookAIWorker | None = None
        self.ai_started_at: float | None = None
        self.ai_last_fraction = 0.0
        self.ai_stats_timer = QTimer(self)
        self.ai_stats_timer.setInterval(1000)
        self.ai_stats_timer.timeout.connect(self._update_ai_stats)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.title = QTextEdit()
        self.title.setMaximumHeight(55)
        self.text = QTextEdit()
        self._loading_fields = False
        self.quick_assign_button = QPushButton("＋ Quick Assign Speaker")
        self.quick_assign_button.setObjectName("primary")
        self.quick_assign_button.setToolTip("Quickly assign the selected dialogue to a saved book character")
        self.quick_assign_button.setVisible(False)
        self.quick_assign_button.clicked.connect(self.quick_assign_dialogue)
        self.text.selectionChanged.connect(self._update_quick_assign_button)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(900)
        self._autosave_timer.timeout.connect(self._autosave)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Chapter Editor"))

        primary = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save)
        primary.addWidget(save_button)
        redetect_button = QPushButton("Re-detect Chapters")
        redetect_button.setObjectName("primary")
        redetect_button.clicked.connect(self.redetect)
        primary.addWidget(redetect_button)
        primary.addStretch(1)
        self.save_status = QLabel("Auto-save enabled")
        self.save_status.setStyleSheet("color:#9aa0a6;")
        primary.addWidget(self.save_status)
        root.addLayout(primary)

        buttons = QGridLayout()
        buttons.setHorizontalSpacing(6)
        buttons.setVerticalSpacing(6)
        actions = [
            ("Rename", self.rename),
            ("Split", self.split),
            ("Mark Selection as Chapter", self.mark_selection_as_chapter),
            ("Assign Selected Dialogue", self.assign_selected_dialogue),
            ("Dialogue Assignment Manager", self.open_dialogue_manager),
            ("Analyze Book with AI", self.analyze_with_ai),
            ("View Characters & Dialogue", self.view_characters),
            ("Merge Next", self.merge),
            ("Move Up", lambda: self.move(-1)),
            ("Move Down", lambda: self.move(1)),
            ("Delete", self.delete),
            ("Delete Selected Chapters", self.delete_selected),
            ("Rename Book / Project", self.rename_book),
        ]
        for index, (label, handler) in enumerate(actions):
            button = QPushButton(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(handler)
            row, column = divmod(index, 3)
            buttons.addWidget(button, row, column)
        for column in range(3):
            buttons.setColumnStretch(column, 1)
        root.addLayout(buttons)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(QLabel("Chapter Title"))
        editor_layout.addWidget(self.title)
        chapter_text_header = QHBoxLayout()
        chapter_text_header.addWidget(QLabel("Chapter Text"))
        chapter_text_header.addStretch(1)
        chapter_text_header.addWidget(self.quick_assign_button)
        editor_layout.addLayout(chapter_text_header)
        editor_layout.addWidget(self.text, 1)
        body.addLayout(editor_layout, 3)
        root.addLayout(body, 1)

        ai_status = QVBoxLayout()
        self.ai_status_label = QLabel("Audiobook AI: idle")
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 100)
        self.ai_progress.setValue(0)
        self.ai_eta_label = QLabel("")
        self.ai_eta_label.setStyleSheet("color:#9aa0a6;")
        ai_status.addWidget(self.ai_status_label)
        ai_status.addWidget(self.ai_progress)
        ai_status.addWidget(self.ai_eta_label)
        root.addLayout(ai_status)

        self.list.currentRowChanged.connect(self.load_selected)
        self.title.textChanged.connect(self._schedule_autosave)
        self.text.textChanged.connect(self._schedule_autosave)
        self.refresh()

    def refresh(self, selected: int | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for chapter in self.editor.chapters:
            assigned = len(getattr(chapter, "dialogue_assignments", []))
            suffix = f" · {assigned} assigned" if assigned else ""
            self.list.addItem(QListWidgetItem(f"{chapter.number}. {chapter.title}{suffix}"))
        self.list.blockSignals(False)
        if self.editor.chapters:
            self.list.setCurrentRow(max(0, min(selected if selected is not None else 0, len(self.editor.chapters) - 1)))

    def load_selected(self, index: int) -> None:
        self._loading_fields = True
        try:
            if 0 <= index < len(self.editor.chapters):
                chapter = self.editor.chapters[index]
                self.title.setPlainText(chapter.title)
                self.text.setPlainText(chapter.text)
                self.save_status.setText("Auto-save enabled")
            else:
                self.title.clear()
                self.text.clear()
        finally:
            self._loading_fields = False

    def _update_quick_assign_button(self) -> None:
        cursor = self.text.textCursor()
        has_selection = cursor.hasSelection() and cursor.selectionStart() < cursor.selectionEnd()
        self.quick_assign_button.setVisible(has_selection and not self._loading_fields)

    def quick_assign_dialogue(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        cursor = self.text.textCursor()
        if not cursor.hasSelection() or cursor.selectionStart() >= cursor.selectionEnd():
            return

        chapter = self.editor.chapters[index]
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        segment = dialogue_segment_for_selection(chapter, start, end)
        registry = build_book_character_registry(self.editor.chapters, self.project_folder)

        menu = QMenu(self)
        menu.setMinimumWidth(420)

        if segment and segment.suggestions:
            suggested_added = set()
            header = menu.addAction("Suggested speakers")
            header.setEnabled(False)
            for name, confidence, evidence in segment.suggestions:
                entry = registry.get(name.casefold())
                if not entry:
                    continue
                suggested_added.add(name.casefold())
                action = menu.addAction(
                    f"✓ {name}  ·  {confidence:.0%}\n"
                    f"   {format_character_registry_entry(entry)}"
                )
                action.setToolTip(evidence)
                action.triggered.connect(
                    lambda _checked=False, speaker=name, s=start, e=end: self._quick_assign_character(index, s, e, speaker)
                )

        saved_header = menu.addAction("Saved characters in this book")
        saved_header.setEnabled(False)
        for key, entry in registry.items():
            if key in suggested_added:
                continue
            action = menu.addAction(format_character_registry_entry(entry))
            action.triggered.connect(
                lambda _checked=False, speaker=entry["name"], s=start, e=end: self._quick_assign_character(index, s, e, speaker)
            )

        if menu.isEmpty():
            empty = menu.addAction("No saved characters yet — add one below.")
            empty.setEnabled(False)

        menu.addSeparator()
        add_action = menu.addAction("＋ Add New Character…")
        add_action.triggered.connect(lambda _checked=False: self.assign_selected_dialogue())
        multi_action = menu.addAction("Assign multiple speakers / advanced…")
        multi_action.triggered.connect(lambda _checked=False: self.assign_selected_dialogue())

        menu.exec(self.quick_assign_button.mapToGlobal(self.quick_assign_button.rect().bottomLeft()))

    def _quick_assign_character(self, chapter_index: int, start: int, end: int, speaker: str) -> None:
        if not (0 <= chapter_index < len(self.editor.chapters)):
            return
        chapter = self.editor.chapters[chapter_index]
        selected_text = chapter.text[start:end].strip()
        if not selected_text:
            return

        assignment = normalize_assignment(
            {
                "start": int(start),
                "end": int(end),
                "text": selected_text,
                "source": "manual",
            },
            [speaker],
            mode="chorus",
        )
        chapter.dialogue_assignments = [
            item
            for item in getattr(chapter, "dialogue_assignments", [])
            if not (
                int(item.get("start", -1)) == start
                and int(item.get("end", -1)) == end
            )
        ]
        chapter.dialogue_assignments.append(assignment)
        self._save_silently()
        self.refresh(chapter_index)
        self.load_selected(chapter_index)
        self.save_status.setText(f"✓ Dialogue assigned to {speaker}")
    def _schedule_autosave(self) -> None:
        if self._loading_fields:
            return
        self.save_status.setText("Unsaved changes…")
        self._autosave_timer.start()

    def _autosave(self) -> None:
        if self._loading_fields:
            return
        try:
            self.commit_current()
            if self.on_save:
                result = self.on_save(self.editor.chapters)
                if result is False:
                    self.save_status.setText("Auto-save failed — use Save Now.")
                    return
            self.save_status.setText("✓ Auto-saved")
        except Exception as exc:
            self.save_status.setText(f"Auto-save failed: {exc}")

    def _save_silently(self) -> bool:
        try:
            self.commit_current()
            if self.on_save:
                result = self.on_save(self.editor.chapters)
                if result is False:
                    self.save_status.setText("Save failed.")
                    return False
            self.save_status.setText("✓ Saved")
            return True
        except Exception as exc:
            self.save_status.setText(f"Save failed: {exc}")
            return False

    def commit_current(self) -> bool:
        index = self.list.currentRow()
        if index < 0:
            return False
        chapter = self.editor.chapters[index]
        new_title = self.title.toPlainText()
        new_text = self.text.toPlainText()
        # Most editor actions do not change the chapter text. Avoid rebuilding
        # every dialogue-assignment offset on every click, especially on large
        # chapters with dozens of assigned dialogue spans.
        if new_title == chapter.title and new_text == chapter.text:
            return False
        if new_title != chapter.title:
            self.editor.rename(index, new_title)
        if new_text != chapter.text:
            self.editor.edit_text(index, new_text)
        return True

    def rename(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        value, ok = QInputDialog.getText(self, "Rename Chapter", "Title:", text=self.editor.chapters[index].title)
        if ok:
            self.editor.rename(index, value)
            self.refresh(index)

    def mark_selection_as_chapter(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        cursor = self.text.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(self, "Mark as Chapter", "Select the chapter title in the Chapter Text first.")
            return
        selected = cursor.selectedText().replace("\u2029", " ").strip()
        if not selected:
            return
        self.commit_current()
        try:
            self.editor.split_at_selection(index, cursor.selectionStart(), cursor.selectionEnd(), selected)
            self.refresh(index if index == 0 and len(self.editor.chapters) == 1 else index + 1)
        except ValueError as exc:
            QMessageBox.information(self, "Mark as Chapter", str(exc))


    def analyze_with_ai(self) -> None:
        if not self.project_folder:
            QMessageBox.information(self, "Audiobook AI", "Open the book through the Library first.")
            return
        if self.ai_worker and self.ai_worker.isRunning():
            return
        self.commit_current()
        answer = QMessageBox.question(
            self,
            "Analyze Book with Audiobook AI",
            "Ryu will analyze characters, dialogue speakers, scene mood, pacing, pronunciation, ambience, music and SFX locally. Your chapter text is not changed. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        import time
        self.ai_started_at = time.monotonic()
        self.ai_last_fraction = 0.0
        self.ai_progress.setValue(0)
        self.ai_status_label.setText("Starting local Audiobook AI…")
        self.ai_eta_label.setText("Elapsed: 0:00 • Estimated remaining: calculating…")
        self.ai_stats_timer.start()
        self._set_editor_busy(True)
        self.ai_worker = AudiobookAIWorker(self.project_folder, self.editor.chapters)
        self.ai_worker.progress.connect(self._ai_progress)
        self.ai_worker.finished_ok.connect(self._ai_finished)
        self.ai_worker.failed.connect(self._ai_failed)
        self.ai_worker.finished.connect(self._ai_worker_finished)
        self.ai_worker.start()

    def _set_editor_busy(self, busy: bool) -> None:
        # Keep the overall application responsive: only the chapter editing
        # controls are locked while the local model is analyzing.
        self.text.setEnabled(not busy)
        self.title.setEnabled(not busy)
        self.list.setEnabled(not busy)

    def _ai_progress(self, fraction: float, message: str) -> None:
        self.ai_last_fraction = max(0.0, min(1.0, float(fraction)))
        self.ai_progress.setValue(int(round(self.ai_last_fraction * 100)))
        self.ai_status_label.setText(message)
        self._update_ai_stats()

    def _update_ai_stats(self) -> None:
        started = self.ai_started_at
        if started is None or not (self.ai_worker and self.ai_worker.isRunning()):
            return
        import time
        elapsed = max(0.0, time.monotonic() - started)
        fraction = self.ai_last_fraction
        if fraction > 0.01:
            remaining = max(0, int(elapsed * (1.0 - fraction) / fraction))
            self.ai_eta_label.setText(
                f"Elapsed: {int(elapsed) // 60}:{int(elapsed) % 60:02d} • "
                f"Estimated remaining: {remaining // 60}:{remaining % 60:02d}"
            )
        else:
            self.ai_eta_label.setText(
                f"Elapsed: {int(elapsed) // 60}:{int(elapsed) % 60:02d} • "
                "Estimated remaining: calculating…"
            )

    def _ai_failed(self, message: str) -> None:
        self.ai_stats_timer.stop()
        self._set_editor_busy(False)
        self.ai_status_label.setText("Audiobook AI: failed")
        self.ai_eta_label.setText("The chapter text was not changed. You can retry the analysis.")
        QMessageBox.warning(self, "Audiobook AI Failed", message)
        self.save_status.setText("AI analysis failed — your chapter text is unchanged.")

    def _ai_finished(self, result) -> None:
        assignments_added = 0
        for chapter_result in result.get("chapters", []):
            number = int(chapter_result.get("chapter", 0) or 0)
            if not 1 <= number <= len(self.editor.chapters):
                continue
            chapter = self.editor.chapters[number - 1]
            text = chapter.text or ""
            for item in chapter_result.get("dialogue", []) or []:
                speaker = str(item.get("speaker") or "").strip()
                quote = str(item.get("quote") or "").strip()
                confidence = _numeric_score(item.get("confidence", 0.0))
                if not speaker or not quote or confidence < 0.88:
                    continue
                start = text.find(quote)
                if start < 0:
                    continue
                end = start + len(quote)
                overlaps_manual = any(
                    str(existing.get("source", "")).casefold() == "manual"
                    and int(existing.get("start", -1)) < end
                    and start < int(existing.get("end", -1))
                    for existing in getattr(chapter, "dialogue_assignments", [])
                )
                if overlaps_manual:
                    continue
                chapter.dialogue_assignments = [
                    existing for existing in getattr(chapter, "dialogue_assignments", [])
                    if not (
                        int(existing.get("start", -1)) == start
                        and int(existing.get("end", -1)) == end
                    )
                ]
                chapter.dialogue_assignments.append({
                    "start": start,
                    "end": end,
                    "text": quote,
                    "speaker": speaker,
                    "source": "ai",
                    "confidence": confidence,
                    "evidence": str(item.get("evidence", "")),
                })
                assignments_added += 1
        self.ai_stats_timer.stop()
        self.ai_last_fraction = 1.0
        self.ai_progress.setValue(100)
        self.ai_status_label.setText("Audiobook AI: analysis complete")
        import time
        elapsed = int(max(0.0, time.monotonic() - (self.ai_started_at or time.monotonic())))
        self.ai_eta_label.setText(
            f"Elapsed: {elapsed // 60}:{elapsed % 60:02d} • "
            f"High-confidence dialogue assignments: {assignments_added}"
        )
        self._set_editor_busy(False)
        self.refresh(self.list.currentRow())
        self._save_silently()
        self.save_status.setText(
            f"✓ Audiobook AI analysis saved • {assignments_added} high-confidence dialogue assignments"
        )

    def _ai_worker_finished(self) -> None:
        self.ai_worker = None
        self.ai_started_at = None

    def open_dialogue_manager(self) -> None:
        self.commit_current()
        dialog = DialogueAssignmentManagerDialog(
            self.editor.chapters,
            project_folder=self.project_folder,
            on_save=self.on_save,
            parent=self,
        )
        dialog.exec()
        self.refresh(self.list.currentRow())
        self.load_selected(self.list.currentRow())

    def assign_selected_dialogue(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        cursor = self.text.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(
                self,
                "Assign Dialogue",
                "Select a dialogue sentence or passage in the Chapter Text first. The assistant will suggest the most likely character.",
            )
            return
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        dialog = DialogueAssignmentDialog(
            self.editor.chapters[index],
            start,
            end,
            book_chapters=self.editor.chapters,
            project_folder=self.project_folder,
            parent=self,
        )
        if dialog.exec():
            self.refresh(index)
            self._loading_fields = True
            try:
                self.text.setPlainText(self.editor.chapters[index].text)
            finally:
                self._loading_fields = False
            self._save_silently()
            cursor = self.text.textCursor()
            cursor.setPosition(min(start, len(self.editor.chapters[index].text)))
            cursor.setPosition(min(end, len(self.editor.chapters[index].text)), cursor.MoveMode.KeepAnchor)
            self.text.setTextCursor(cursor)

    def view_characters(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        dialog = CharacterReviewDialog(self.editor.chapters[index], self)
        dialog.exec()

    def split(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        paragraphs = [p.strip() for p in self.editor.chapters[index].text.split("\n\n") if p.strip()]
        if len(paragraphs) < 2:
            QMessageBox.information(self, "Split Chapter", "The chapter needs at least two paragraphs.")
            return
        point, ok = QInputDialog.getInt(self, "Split Chapter", f"Split before paragraph (2-{len(paragraphs)}):", 2, 2, len(paragraphs))
        if not ok:
            return
        title, ok = QInputDialog.getText(self, "New Chapter", "New chapter title:", text="New Chapter")
        if ok:
            self.editor.split(index, point - 1, title)
            self.refresh(index + 1)
            self._save_silently()

    def merge(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        try:
            self.editor.merge_with_next(index)
            self.refresh(index)
            self._save_silently()
        except IndexError:
            QMessageBox.information(self, "Merge Chapter", "There is no next chapter.")

    def move(self, direction: int) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        self.editor.move(index, direction)
        self.refresh(index + direction)
        self._save_silently()

    def delete(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        if QMessageBox.question(self, "Delete Chapter", "Delete this chapter?") == QMessageBox.StandardButton.Yes:
            self.editor.delete(index)
            self.refresh(min(index, len(self.editor.chapters) - 1) if self.editor.chapters else None)
            self._save_silently()

    def delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.list.selectedIndexes()}, reverse=True)
        if not rows:
            index = self.list.currentRow()
            if index >= 0:
                rows = [index]
        if not rows:
            return
        answer = QMessageBox.question(
            self,
            "Delete Selected Chapters",
            f"Delete {len(rows)} selected chapter(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for index in rows:
            if 0 <= index < len(self.editor.chapters):
                self.editor.delete(index)
        self.refresh(min(rows[-1], len(self.editor.chapters) - 1) if self.editor.chapters else None)
        self._save_silently()

    def rename_book(self) -> None:
        value, ok = QInputDialog.getText(self, "Rename Audiobook", "Audiobook / project title:", text=self.window().windowTitle() if self.window() else "")
        if not ok or not value.strip():
            return
        if self.on_rename_book:
            self.on_rename_book(value.strip())
            QMessageBox.information(self, "Renamed", f"Audiobook renamed to '{value.strip()}'.")
        else:
            QMessageBox.information(self, "Rename Audiobook", "Open the project through the Library to rename its title.")

    def save(self) -> None:
        if self._save_silently():
            QMessageBox.information(self, "Saved", "Project changes have been saved.")

    def redetect(self) -> None:
        if not self.on_redetect:
            QMessageBox.information(self, "Re-detect Chapters", "The original source is not available for this project.")
            return
        answer = QMessageBox.question(
            self,
            "Re-detect Chapters",
            "Re-run chapter detection from the original imported book?\n\nThis replaces the current automatic chapter split. Your current manual chapter edits will be lost unless you save/export them separately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.on_redetect()
