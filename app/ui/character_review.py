from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
from app.chapters.characters import analyze_chapter


class CharacterReviewDialog(QDialog):
    def __init__(self, chapter, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Character & Dialogue Review — {chapter.title}")
        self.resize(900, 620)
        self.chapter = chapter
        self.analysis = analyze_chapter(chapter)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"<h2>{chapter.title}</h2>"))
        root.addWidget(QLabel(
            "Review the detected narrator and characters before assigning voices. "
            "Detection is a suggestion, not an automatic change to your book."
        ))

        body = QHBoxLayout()
        self.characters = QListWidget()
        self.characters.addItem(QListWidgetItem("Narrator  ·  Narrator"))
        for character in self.analysis.characters:
            self.characters.addItem(
                QListWidgetItem(
                    f"{character.name}  ·  {character.role}  ·  "
                    f"{character.dialogue_count} dialogue cues"
                )
            )
        body.addWidget(self.characters, 2)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        body.addWidget(self.details, 3)
        root.addLayout(body)

        self.characters.currentRowChanged.connect(self.show_character)
        if self.characters.count():
            self.characters.setCurrentRow(0)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close)

    def show_character(self, index: int) -> None:
        if index == 0:
            self.details.setPlainText(
                "Narrator\n\nAll non-dialogue/story text uses the Narrator voice "
                "unless a reviewed character dialogue assignment is applied."
            )
            return
        character = self.analysis.characters[index - 1]
        examples = character.examples or []
        manual = [
            item for item in getattr(self.chapter, "dialogue_assignments", [])
            if str(item.get("speaker", "")).strip().casefold() == character.name.casefold()
        ]
        text = [
            f"Name: {character.name}",
            f"Role: {character.role}",
            f"Dialogue cues detected: {character.dialogue_count}",
            f"Manual assignments saved: {len(manual)}",
            "",
            "Detected dialogue examples:",
        ]
        text.extend(f"• {example}" for example in examples)
        if not examples:
            text.append("No quoted dialogue example was confidently linked.")
        if manual:
            text.extend(["", "Saved manual assignments:"])
            for item in manual[:8]:
                text.append(f"• {str(item.get('text', '')).strip()[:180]}")
        self.details.setPlainText("\n".join(text))
