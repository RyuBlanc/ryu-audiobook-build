from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel
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
    QWidget,
    QInputDialog,
    QSizePolicy,
)
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.documents.parser import remove_page_noise
from app.ui.character_review import CharacterReviewDialog
from app.ui.dialogue_assignment import DialogueAssignmentDialog


class ChapterEditorPage(QWidget):
    def __init__(self, chapters: list[Chapter], on_save=None, on_rename_book=None, on_redetect=None) -> None:
        super().__init__()
        cleaned = [
            Chapter(ch.number, ch.title, remove_page_noise(ch.text), list(getattr(ch, "dialogue_assignments", [])))
            for ch in chapters
        ]
        self.editor = ChapterEditor(cleaned)
        self.on_save = on_save
        self.on_rename_book = on_rename_book
        self.on_redetect = on_redetect
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.title = QTextEdit()
        self.title.setMaximumHeight(55)
        self.text = QTextEdit()
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
        root.addLayout(primary)

        buttons = QGridLayout()
        buttons.setHorizontalSpacing(6)
        buttons.setVerticalSpacing(6)
        actions = [
            ("Rename", self.rename),
            ("Split", self.split),
            ("Mark Selection as Chapter", self.mark_selection_as_chapter),
            ("Assign Selected Dialogue", self.assign_selected_dialogue),
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
        editor_layout.addWidget(QLabel("Chapter Text"))
        editor_layout.addWidget(self.text, 1)
        body.addLayout(editor_layout, 3)
        root.addLayout(body, 1)
        self.list.currentRowChanged.connect(self.load_selected)
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
        if 0 <= index < len(self.editor.chapters):
            chapter = self.editor.chapters[index]
            self.title.setPlainText(chapter.title)
            self.text.setPlainText(chapter.text)
        else:
            self.title.clear()
            self.text.clear()

    def commit_current(self) -> None:
        index = self.list.currentRow()
        if index >= 0:
            self.editor.rename(index, self.title.toPlainText())
            self.editor.edit_text(index, self.text.toPlainText())

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
        dialog = DialogueAssignmentDialog(self.editor.chapters[index], start, end, self)
        if dialog.exec():
            self.refresh(index)
            self.text.setPlainText(self.editor.chapters[index].text)
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

    def merge(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        try:
            self.editor.merge_with_next(index)
            self.refresh(index)
        except IndexError:
            QMessageBox.information(self, "Merge Chapter", "There is no next chapter.")

    def move(self, direction: int) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        self.editor.move(index, direction)
        self.refresh(index + direction)

    def delete(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        if QMessageBox.question(self, "Delete Chapter", "Delete this chapter?") == QMessageBox.StandardButton.Yes:
            self.editor.delete(index)
            self.refresh(min(index, len(self.editor.chapters) - 1) if self.editor.chapters else None)

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
        self.commit_current()
        if self.on_save:
            result = self.on_save(self.editor.chapters)
            if result is False:
                return
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
