from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QTextEdit

from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text

class ImportPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.info = QLabel("Choose a PDF, EPUB, TXT, or DOCX book.")
        self.button = QPushButton("Import Book")
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.layout.addWidget(self.info)
        self.layout.addWidget(self.button)
        self.layout.addWidget(self.preview)
        self.button.clicked.connect(self.choose_book)

    def choose_book(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Book",
            "",
            "Books (*.pdf *.epub *.txt *.docx);;PDF (*.pdf);;EPUB (*.epub);;Text (*.txt);;Word (*.docx)",
        )
        if not path:
            return
        try:
            book = extract_text(Path(path))
            chapters = detect_chapters(book.text)
            self.info.setText(f"{book.title} — {len(chapters)} chapter(s) detected")
            self.preview.setPlainText(
                "\n\n".join(f"## {chapter.title}\n{chapter.text[:1200]}" for chapter in chapters[:10])
            )
        except Exception as exc:
            self.info.setText(f"Import failed: {exc}")
