from __future__ import annotations

from PySide6.QtWidgets import (
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
)
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.documents.parser import remove_page_noise
from app.ui.character_review import CharacterReviewDialog


class ChapterEditorPage(QWidget):
    def __init__(self, chapters: list[Chapter], on_save=None) -> None:
        super().__init__()
        cleaned = [Chapter(ch.number, ch.title, remove_page_noise(ch.text)) for ch in chapters]
        self.editor = ChapterEditor(cleaned)
        self.on_save = on_save
        self.list = QListWidget()
        self.title = QTextEdit()
        self.title.setMaximumHeight(55)
        self.text = QTextEdit()
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Chapter Editor"))
        buttons = QHBoxLayout()
        actions = [
            ("Rename", self.rename),
            ("Split", self.split),
            ("Mark Selection as Chapter", self.mark_selection_as_chapter),
            ("View Characters & Dialogue", self.view_characters),
            ("Merge Next", self.merge),
            ("Move Up", lambda: self.move(-1)),
            ("Move Down", lambda: self.move(1)),
            ("Delete", self.delete),
            ("Save", self.save),
        ]
        for label, handler in actions:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        root.addLayout(buttons)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(QLabel("Chapter Title"))
        editor_layout.addWidget(self.title)
        editor_layout.addWidget(QLabel("Chapter Text"))
        editor_layout.addWidget(self.text)
        body.addLayout(editor_layout, 3)
        root.addLayout(body)
        self.list.currentRowChanged.connect(self.load_selected)
        self.refresh()

    def refresh(self, selected: int | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for chapter in self.editor.chapters:
            self.list.addItem(QListWidgetItem(f"{chapter.number}. {chapter.title}"))
        self.list.blockSignals(False)
        if self.editor.chapters:
            self.list.setCurrentRow(
                max(0, min(selected if selected is not None else 0, len(self.editor.chapters) - 1))
            )

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
        value, ok = QInputDialog.getText(
            self,
            "Rename Chapter",
            "Title:",
            text=self.editor.chapters[index].title,
        )
        if ok:
            self.editor.rename(index, value)
            self.refresh(index)

    def mark_selection_as_chapter(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return

        cursor = self.text.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(
                self,
                "Mark as Chapter",
                "Select the chapter title in the Chapter Text first.",
            )
            return

        selected = cursor.selectedText().replace("\u2029", " ").strip()
        if not selected:
            return

        self.commit_current()
        index = self.list.currentRow()

        try:
            self.editor.split_at_selection(
                index,
                cursor.selectionStart(),
                cursor.selectionEnd(),
                selected,
            )
            self.refresh(index if index == 0 and len(self.editor.chapters) == 1 else index + 1)
        except ValueError as exc:
            QMessageBox.information(self, "Mark as Chapter", str(exc))

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
        paragraphs = [
            p.strip()
            for p in self.editor.chapters[index].text.split("\n\n")
            if p.strip()
        ]
        if len(paragraphs) < 2:
            QMessageBox.information(
                self,
                "Split Chapter",
                "The chapter needs at least two paragraphs.",
            )
            return
        point, ok = QInputDialog.getInt(
            self,
            "Split Chapter",
            f"Split before paragraph (2-{len(paragraphs)}):",
            2,
            2,
            len(paragraphs),
        )
        if not ok:
            return
        title, ok = QInputDialog.getText(
            self,
            "New Chapter",
            "New chapter title:",
            text="New Chapter",
        )
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
            QMessageBox.information(
                self,
                "Merge Chapter",
                "There is no next chapter.",
            )

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
        if (
            QMessageBox.question(self, "Delete Chapter", "Delete this chapter?")
            == QMessageBox.StandardButton.Yes
        ):
            self.editor.delete(index)
            self.refresh(
                min(index, len(self.editor.chapters) - 1)
                if self.editor.chapters
                else None
            )

    def save(self) -> None:
        self.commit_current()
        if self.on_save:
            self.on_save(self.editor.chapters)
        QMessageBox.information(self, "Saved", "Project changes have been saved.")
