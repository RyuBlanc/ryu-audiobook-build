from __future__ import annotations

from pathlib import Path
import logging

from PySide6.QtCore import QEvent, QItemSelectionModel, QTimer, QThread, Signal, Qt, QPoint, QSize
from PySide6.QtGui import QColor, QIcon, QTextCharFormat, QTextCursor
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
    QToolTip,
    QScrollArea,
)
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.documents.parser import (
    remove_page_noise,
    detect_repeated_book_noise,
    clean_import_noise,
    reflow_source_text,
)
from app.ui.character_review import CharacterReviewDialog
from app.ui.dialogue_assignment import DialogueAssignmentDialog
from app.ui.dialogue_manager import DialogueAssignmentManagerDialog
from app.chapters.dialogue import dialogue_segment_for_selection
from app.chapters.assignment_utils import build_book_character_registry, normalize_assignment, format_character_registry_entry
from app.core.state import load_state
from app.ai.brain import AudiobookBrain, _numeric_score

log = logging.getLogger(__name__)




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
    def __init__(
        self,
        chapters: list[Chapter],
        on_save=None,
        on_rename_book=None,
        on_redetect=None,
        project_folder=None,
        project_title: str | None = None,
        on_autosave=None,
    ) -> None:
        super().__init__()
        cleaned = [
            Chapter(ch.number, ch.title, remove_page_noise(ch.text), list(getattr(ch, "dialogue_assignments", [])))
            for ch in chapters
        ]
        self.editor = ChapterEditor(cleaned)
        self.on_save = on_save
        self.on_autosave = on_autosave
        self.on_rename_book = on_rename_book
        self.on_redetect = on_redetect
        self.project_folder = project_folder
        self.project_title = str(project_title or "").strip()
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
        self._assignment_plus = QPushButton("", self.text.viewport())
        self._assignment_plus.setObjectName("assignmentPlus")
        dragon_assets = Path(__file__).resolve().parents[2] / "assets"
        # Use the supplied master PNG so this control preserves the actual
        # four-winged dragon silhouette. The build creates this asset from the master PNG; the circle is a UI
        # treatment around that artwork, not a separately redrawn approximation.
        dragon_plus_path = dragon_assets / "dragon_cross.png"
        if dragon_plus_path.is_file():
            self._assignment_plus.setIcon(QIcon(str(dragon_plus_path)))
            self._assignment_plus.setIconSize(QSize(22, 22))
        else:
            self._assignment_plus.setText("⊕")
        self._assignment_plus.setStyleSheet(
            "QPushButton#assignmentPlus {"
            " background: #170a11; border: 1px solid #9f2b4b;"
            " border-radius: 14px; padding: 1px;"
            "}"
            "QPushButton#assignmentPlus:hover {"
            " background: #321020; border: 1px solid #ed526e;"
            "}"
        )
        self.text.setViewportMargins(82, 0, 0, 0)
        self._assignment_plus.setFixedSize(28, 28)
        self._assignment_plus.setToolTip("Assign this sentence to a character")
        self._assignment_plus.hide()
        self._assignment_plus.clicked.connect(self._open_inline_assignment_dialog)
        self._assignment_hover_items: list[tuple[int, int, tuple[str, ...]]] = []
        self._assignment_tooltip_key: tuple[int, int, tuple[str, ...]] | None = None
        self._assignment_palette = (
            "#8EC5FF", "#F0C674", "#E8A7C7", "#8FD8A8",
            "#B8A2EE", "#F1B881", "#72C9C1", "#D7A5D6",
        )
        self.text.viewport().setMouseTracking(True)
        self.text.viewport().installEventFilter(self)
        self.text.selectionChanged.connect(self._update_assignment_plus)
        self.text.verticalScrollBar().valueChanged.connect(self._refresh_assignment_visuals)
        self.text.horizontalScrollBar().valueChanged.connect(self._refresh_assignment_visuals)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(900)
        self._autosave_timer.timeout.connect(self._autosave)
        # Keep the complete editor reachable on short displays and when the
        # user's interface scale is increased. The chapter list and text editor
        # retain their own internal scrolling; this scrolls the page controls.
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setObjectName("chapterEditorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 6, 8, 14)
        root.setSpacing(12)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
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
            ("Analyze Book with AI", self.analyze_with_ai),
            ("Clean Book Text", self.clean_book_text),
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
        hint = QLabel("Select a sentence • click ＋ to assign its speaker")
        hint.setObjectName("muted")
        chapter_text_header.addWidget(hint)
        chapter_text_header.addStretch(1)
        assignment_manager_button = QPushButton("Assignments")
        assignment_manager_button.setToolTip("Open the full dialogue assignment manager")
        assignment_manager_button.clicked.connect(self.open_dialogue_manager)
        chapter_text_header.addWidget(assignment_manager_button)
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
        self.title.textChanged.connect(self._update_current_chapter_list_label)
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
                self._clear_assignment_hover_state()
                self._refresh_assignment_visuals()
                self.save_status.setText("Auto-save enabled")
            else:
                self.title.clear()
                self.text.clear()
        finally:
            self._loading_fields = False

    def _update_current_chapter_list_label(self) -> None:
        if self._loading_fields:
            return
        index = self.list.currentRow()
        if not (0 <= index < len(self.editor.chapters)):
            return
        title = self.title.toPlainText().strip() or self.editor.chapters[index].title
        assigned = len(getattr(self.editor.chapters[index], "dialogue_assignments", []))
        suffix = f" · {assigned} assigned" if assigned else ""
        item = self.list.item(index)
        if item is not None:
            item.setText(f"{self.editor.chapters[index].number}. {title}{suffix}")

    def _selection_sentence_span(self) -> tuple[int, int]:
        cursor = self.text.textCursor()
        if not cursor.hasSelection():
            return (-1, -1)
        start = min(cursor.selectionStart(), cursor.selectionEnd())
        end = max(cursor.selectionStart(), cursor.selectionEnd())
        source = self.text.toPlainText()
        if not source or end <= start:
            return (-1, -1)

        left = start
        while left > 0:
            ch = source[left - 1]
            if ch in ".!?…":
                while left < len(source) and source[left].isspace():
                    left += 1
                break
            if ch in "\n\r":
                break
            left -= 1

        right = end
        while right < len(source):
            ch = source[right]
            if ch in ".!?…":
                right += 1
                while right < len(source) and source[right] in "\"”’»)]":
                    right += 1
                break
            if ch in "\n\r":
                break
            right += 1

        while left > 0 and source[left - 1].isspace() and source[left - 1] not in "\n\r":
            left -= 1
        while right < len(source) and source[right].isspace() and source[right] not in "\n\r":
            right += 1
        return left, right

    @staticmethod
    def _assignment_speakers(item: dict) -> list[str]:
        raw = item.get("speakers")
        if isinstance(raw, list):
            values = [str(value).strip() for value in raw if str(value).strip()]
            if values:
                return values
        speaker = str(item.get("speaker", "")).strip()
        return [speaker] if speaker else []

    def _clear_assignment_hover_state(self) -> None:
        self._assignment_hover_items.clear()
        self._assignment_tooltip_key = None
        QToolTip.hideText()

    def _assignment_color(self, speaker: str) -> QColor:
        # Saved character assignments use a consistent soft green. Amber is
        # reserved for unconfirmed analysis suggestions; native assignment
        # highlights should not look like AI-review warnings.
        return QColor("#29B773")

    def _refresh_assignment_visuals(self) -> None:
        if not hasattr(self, "text"):
            return
        self._clear_assignment_hover_state()
        selections: list[QTextEdit.ExtraSelection] = []
        chapter_index = self.list.currentRow()
        if not (0 <= chapter_index < len(self.editor.chapters)):
            self.text.setExtraSelections(selections)
            return

        chapter = self.editor.chapters[chapter_index]
        for assignment in getattr(chapter, "dialogue_assignments", []):
            try:
                start = int(assignment.get("start", -1))
                end = int(assignment.get("end", -1))
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start or start >= len(chapter.text):
                continue
            end = min(end, len(chapter.text))
            speakers = self._assignment_speakers(assignment)
            if not speakers:
                continue

            cursor = self.text.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

            # Colour the assigned range in-place. Permanent floating buttons covered
            # glyphs and made otherwise valid words look truncated.
            color = self._assignment_color(speakers[0])
            soft = QColor(color)
            soft.setAlpha(52)
            fmt = QTextCharFormat()
            fmt.setBackground(soft)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)
            self._assignment_hover_items.append((start, end, tuple(speakers)))

        self.text.setExtraSelections(selections)
        self._update_assignment_plus()

    def eventFilter(self, watched, event):
        # Qt can deliver final child/viewport events while the parent editor is
        # being destroyed. Do not dereference its deleted QTextEdit wrapper.
        try:
            text_widget = getattr(self, "text", None)
            viewport = text_widget.viewport() if text_widget is not None else None
        except RuntimeError:
            return False

        if watched is viewport:
            try:
                if event.type() == QEvent.Type.MouseMove:
                    point = event.position().toPoint()
                    position = text_widget.cursorForPosition(point).position()
                    hover_item = next(
                        (item for item in self._assignment_hover_items if item[0] <= position < item[1]),
                        None,
                    )
                    if hover_item is None:
                        if self._assignment_tooltip_key is not None:
                            QToolTip.hideText()
                            self._assignment_tooltip_key = None
                    else:
                        start, end, speakers = hover_item
                        key = (start, end, speakers)
                        if key != self._assignment_tooltip_key:
                            QToolTip.showText(
                                text_widget.viewport().mapToGlobal(point + QPoint(14, 18)),
                                "Assigned speaker: " + ", ".join(speakers),
                                text_widget,
                            )
                            self._assignment_tooltip_key = key
                elif event.type() == QEvent.Type.Leave:
                    QToolTip.hideText()
                    self._assignment_tooltip_key = None
            except RuntimeError:
                # The target may have been deleted between event dispatch and
                # Python callback teardown. Returning False lets Qt finish it.
                return False
        try:
            return super().eventFilter(watched, event)
        except RuntimeError:
            return False

    def _update_assignment_plus(self) -> None:
        if self._loading_fields or not self.text.isEnabled():
            self._assignment_plus.hide()
            return
        cursor = self.text.textCursor()
        if not cursor.hasSelection() or cursor.selectionStart() == cursor.selectionEnd():
            self._assignment_plus.hide()
            return
        start, end = self._selection_sentence_span()
        if start < 0 or end <= start:
            self._assignment_plus.hide()
            return
        probe = self.text.textCursor()
        probe.setPosition(end)
        rect = self.text.cursorRect(probe)
        button = self._assignment_plus
        button.show()
        button.raise_()
        x = 31
        y = min(max(3, rect.top()), max(3, self.text.viewport().height() - button.height() - 4))
        button.move(x, y)

    def _learning_series_and_aliases(self, speaker: str) -> tuple[str, list[str]]:
        """Resolve the active series and canonical saved aliases for explicit feedback."""
        if not self.project_folder:
            return self.project_title, []
        try:
            state = load_state(self.project_folder)
        except Exception:
            log.exception("Could not load project state for dialogue-learning feedback")
            return self.project_title, []
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        series = str(
            state.get("series_name") or state.get("series") or metadata.get("series")
            or self.project_title or ""
        ).strip()
        roster = state.get("voice_cast_character_roster") or []
        if not isinstance(roster, list):
            roster = []
        key = str(speaker or "").strip().casefold()
        row = next((item for item in roster if isinstance(item, dict) and (
            str(item.get("name") or "").strip().casefold() == key
            or key in {str(alias).strip().casefold() for alias in (item.get("aliases") or [])}
        )), None)
        aliases = row.get("aliases") or [] if isinstance(row, dict) else []
        if isinstance(row, dict):
            series = str(row.get("series") or series).strip()
        if isinstance(aliases, str):
            aliases = [aliases]
        return series, [str(value).strip() for value in aliases if str(value or "").strip()] if isinstance(aliases, (list, tuple)) else []

    def _record_native_assignment_feedback(self, chapter, assignment: dict) -> None:
        """Learn from a saved manual single-speaker assignment, never an AI guess."""
        if not self.project_folder or not isinstance(assignment, dict):
            return
        if str(assignment.get("source") or "").casefold() not in {"manual", "user", "explicit"}:
            return
        speakers = self._assignment_speakers(assignment)
        if len(speakers) != 1:
            return
        try:
            start, end = int(assignment.get("start", -1)), int(assignment.get("end", -1))
        except (TypeError, ValueError):
            return
        source = str(chapter.text or "")
        if start < 0 or end <= start or end > len(source):
            return
        series, aliases = self._learning_series_and_aliases(speakers[0])
        if not series:
            return
        try:
            from app.chapters.character_learning import record_assignment_feedback
            record_assignment_feedback(
                series=series, speaker=speakers[0], aliases=aliases,
                chapter_text=source, start=start, end=end, source_text=source[start:end],
                chapter_title=str(chapter.title or ""),
            )
        except Exception:
            # The chapter assignment is already saved; a learning cache failure
            # must be visible in logs without undoing the user's assignment.
            log.exception("Could not record native Chapter Studio speaker-learning feedback")

    def _remove_native_assignment_feedback(self, chapter, assignment: dict) -> None:
        if not self.project_folder or not isinstance(assignment, dict):
            return
        if str(assignment.get("source") or "").casefold() not in {"manual", "user", "explicit"}:
            return
        try:
            start, end = int(assignment.get("start", -1)), int(assignment.get("end", -1))
        except (TypeError, ValueError):
            return
        source = str(chapter.text or "")
        if start < 0 or end <= start or end > len(source):
            return
        series, _aliases = self._learning_series_and_aliases(
            (self._assignment_speakers(assignment) or [""])[0]
        )
        if not series:
            return
        try:
            from app.chapters.character_learning import remove_assignment_feedback
            remove_assignment_feedback(
                series=series, chapter_text=source, start=start, end=end,
                source_text=source[start:end],
            )
        except Exception:
            log.exception("Could not remove native Chapter Studio speaker-learning feedback")

    def _sync_native_learning_changes(self, before: dict[tuple[int, int], dict], chapter) -> None:
        """Apply feedback only to changed manual spans after the chapter save succeeds."""
        after_rows = {
            (int(row.get("start", -1)), int(row.get("end", -1))): dict(row)
            for row in (getattr(chapter, "dialogue_assignments", []) or [])
            if isinstance(row, dict)
        }
        for span, prior in before.items():
            current = after_rows.get(span)
            if current is None:
                self._remove_native_assignment_feedback(chapter, prior)
            elif current != prior:
                self._record_native_assignment_feedback(chapter, current)
        for span, current in after_rows.items():
            if span not in before:
                self._record_native_assignment_feedback(chapter, current)

    def _open_inline_assignment_dialog(self) -> None:
        chapter_index = self.list.currentRow()
        if chapter_index < 0:
            return
        start, end = self._selection_sentence_span()
        if start < 0 or end <= start:
            return
        cursor = self.text.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.text.setTextCursor(cursor)
        chapter = self.editor.chapters[chapter_index]
        before = {
            (int(item.get("start", -1)), int(item.get("end", -1))): dict(item)
            for item in (getattr(chapter, "dialogue_assignments", []) or [])
            if isinstance(item, dict)
        }
        dialog = DialogueAssignmentDialog(
            chapter=chapter,
            start=start,
            end=end,
            book_chapters=self.editor.chapters,
            project_folder=self.project_folder,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.assigned:
            if self._save_silently():
                self._sync_native_learning_changes(before, chapter)
            self._refresh_assignment_visuals()
            self.save_status.setText("✓ Speaker assignment saved for selected sentence")
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
            callback = self.on_autosave or self.on_save
            if callback:
                result = callback(self.editor.chapters)
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


    def clean_book_text(self) -> None:
        self.commit_current()
        chapters = self.editor.chapters
        if not chapters:
            return

        noise = detect_repeated_book_noise([chapter.text for chapter in chapters])
        preview_lines = []
        for line, count in sorted(noise.items(), key=lambda item: (-item[1], item[0])):
            preview_lines.append(f"• {line}  × {count} chapters")

        if preview_lines:
            message = (
                "Ryu found repeated page/website-style text in this book. "
                "It can remove those occurrences from all chapters and reflow obvious wrapped sentences.\n\n"
                "Detected text:\n" + "\n".join(preview_lines[:30])
            )
            if len(preview_lines) > 30:
                message += f"\n… and {len(preview_lines) - 30} more."
        else:
            message = (
                "No repeated page/website markers were detected. "
                "Ryu can still reflow obvious PDF line-wrapped sentences without changing paragraph boundaries."
            )

        answer = QMessageBox.question(
            self,
            "Clean Book Text",
            message + "\n\nApply this cleanup to every chapter?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        total_removed = 0
        changed_chapters = 0
        repeated = set(noise.keys())
        for chapter in chapters:
            cleaned, removed = clean_import_noise(chapter.text, repeated)
            cleaned = reflow_source_text(cleaned)
            if cleaned != chapter.text:
                self.editor.edit_text(chapters.index(chapter), cleaned)
                changed_chapters += 1
            total_removed += len(removed)

        self.refresh(self.list.currentRow())
        self._save_silently()
        self.save_status.setText(
            f"✓ Book cleaned • {changed_chapters} chapter(s) updated • {total_removed} noise line(s) removed"
        )

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
                f"Progress: {fraction * 100:.0f}% • "
                f"Elapsed {int(elapsed) // 60}:{int(elapsed) % 60:02d} • "
                f"ETA {remaining // 60}:{remaining % 60:02d}"
            )
        else:
            self.ai_eta_label.setText(
                f"Progress: {fraction * 100:.0f}% • "
                f"Elapsed {int(elapsed) // 60}:{int(elapsed) % 60:02d} • "
                "ETA calculating…"
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
        before = {}
        for chapter in self.editor.chapters:
            before[int(chapter.number)] = {
                (int(item.get("start", -1)), int(item.get("end", -1))): dict(item)
                for item in (getattr(chapter, "dialogue_assignments", []) or [])
                if isinstance(item, dict)
            }
        dialog = DialogueAssignmentManagerDialog(
            self.editor.chapters,
            project_folder=self.project_folder,
            on_save=self.on_save,
            parent=self,
        )
        dialog.exec()
        # Reconcile confirmed assignments/unassignments against the pre-dialog
        # snapshot only after the real project save has succeeded.
        saved = bool(self.on_save(self.editor.chapters)) if self.on_save else True
        if saved:
            for chapter in self.editor.chapters:
                self._sync_native_learning_changes(before.get(int(chapter.number), {}), chapter)
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
        chapter = self.editor.chapters[index]
        before = {
            (int(item.get("start", -1)), int(item.get("end", -1))): dict(item)
            for item in (getattr(chapter, "dialogue_assignments", []) or [])
            if isinstance(item, dict)
        }
        dialog = DialogueAssignmentDialog(
            chapter,
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
            if self._save_silently():
                self._sync_native_learning_changes(before, self.editor.chapters[index])
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
        current_title = self.project_title or "Untitled Book"
        value, ok = QInputDialog.getText(
            self,
            "Rename Audiobook",
            "Audiobook / project title:",
            text=current_title,
        )
        if not ok or not value.strip():
            return
        new_title = value.strip()
        if self.on_rename_book:
            self.on_rename_book(new_title)
            self.project_title = new_title
            QMessageBox.information(self, "Renamed", f"Audiobook renamed to '{new_title}'.")
        else:
            QMessageBox.information(
                self,
                "Rename Audiobook",
                "Open the project through the Library to rename its title.",
            )

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
