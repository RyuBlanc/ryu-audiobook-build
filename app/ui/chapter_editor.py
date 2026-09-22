from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QInputDialog
)

from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor

class ChapterEditorPage(QWidget):
    def __init__(self, chapters: list[Chapter], on_save=None) -> None:
        super().__init__()
        self.editor = ChapterEditor(chapters)
        self.on_save = on_save
        self.list = QListWidget()
        self.title = QTextEdit()
        self.title.setMaximumHeight(55)
        self.text = QTextEdit()

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Chapter Editor"))

        buttons = QHBoxLayout()
        for label, handler in [
            ("Rename", self.rename),
            ("Split", self.split),
            ("Merge Next", self.merge),
            ("Move Up", lambda: self.move(-1)),
            ("Move Down", lambda: self.move(1)),
            ("Delete", self.delete),
            ("Save", self.save),
        ]:
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

    def refresh(self) -> None:
        self.list.clear()
        for chapter in self.editor.chapters:
            item = QListWidgetItem(f"{chapter.number}. {chapter.title}")
            self.list.addItem(item)
        if self.editor.chapters:
            self.list.setCurrentRow(0)

    def load_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.editor.chapters):
            self.title.clear()
            self.text.clear()
            return
        chapter = self.editor.chapters[index]
        self.title.setPlainText(chapter.title)
        self.text.setPlainText(chapter.text)

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
            self.refresh()
            self.list.setCurrentRow(index)

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
            self.refresh()
            self.list.setCurrentRow(index + 1)

    def merge(self) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        try:
            self.editor.merge_with_next(index)
            self.refresh()
            self.list.setCurrentRow(min(index, len(self.editor.chapters) - 1))
        except IndexError:
            QMessageBox.information(self, "Merge Chapter", "There is no next chapter.")

    def move(self, direction: int) -> None:
        self.commit_current()
        index = self.list.currentRow()
        if index < 0:
            return
        self.editor.move(index, direction)
        self.refresh()
        self.list.setCurrentRow(max(0, min(index + direction, len(self.editor.chapters) - 1)))

    def delete(self) -> None:
        index = self.list.currentRow()
        if index < 0:
            return
        answer = QMessageBox.question(self, "Delete Chapter", "Delete this chapter?")
        if answer == QMessageBox.StandardButton.Yes:
            self.editor.delete(index)
            self.refresh()

    def save(self) -> None:
        self.commit_current()
        if self.on_save:
            self.on_save(self.editor.chapters)
        QMessageBox.information(self, "Saved", "Chapter changes saved for this session.")
