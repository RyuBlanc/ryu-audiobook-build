from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.chapters.characters import analyze_chapter
from app.tts.voice_profile import load_profiles


class VoiceCastPage(QWidget):
    """Reviewable narrator/character cast for the current book."""

    def __init__(self, get_chapters, parent=None):
        super().__init__(parent)
        self.get_chapters = get_chapters
        self.profiles = []
        self.rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        root.addWidget(QLabel("<h1>Voice Cast</h1>"))
        intro = QLabel(
            "Analyze the book, review likely narrator/story/background characters, "
            "then assign a saved voice profile. Nothing is changed until you generate."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        actions = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze Book Characters")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        actions.addWidget(self.analyze_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.summary = QLabel("No character analysis yet.")
        self.summary.setObjectName("muted")
        root.addWidget(self.summary)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_details)
        body.addWidget(self.list, 2)

        details = QVBoxLayout()
        self.details = QLabel("Select a cast member.")
        self.details.setWordWrap(True)
        details.addWidget(self.details)

        form_box = QGroupBox("Voice assignment")
        form = QFormLayout(form_box)
        self.profile = QComboBox()
        form.addRow("Saved voice profile", self.profile)
        self.apply_button = QPushButton("Assign Voice")
        self.apply_button.clicked.connect(self.assign_voice)
        form.addRow(self.apply_button)
        details.addWidget(form_box)
        details.addStretch(1)
        body.addLayout(details, 3)
        root.addLayout(body, 1)

        self.refresh_profiles()

    def refresh_profiles(self):
        self.profiles = load_profiles()
        self.profile.clear()
        for profile in self.profiles:
            self.profile.addItem(profile.name, profile.name)
        if not self.profiles:
            self.profile.addItem("No saved voice profiles", None)

    def analyze(self):
        chapters = self.get_chapters() or []
        self.list.clear()
        self.rows = []
        self.rows.append({
            "name": "Narrator",
            "role": "Narrator",
            "dialogue_count": 0,
            "examples": [],
            "chapters": "All chapters",
        })

        for chapter in chapters:
            result = analyze_chapter(chapter)
            for character in result.characters:
                existing = next(
                    (x for x in self.rows if x["name"].casefold() == character.name.casefold()),
                    None,
                )
                if existing:
                    existing["dialogue_count"] += character.dialogue_count
                    existing["examples"] = (existing["examples"] + (character.examples or []))[:5]
                    existing["chapters"] += f", {chapter.number}"
                else:
                    self.rows.append({
                        "name": character.name,
                        "role": character.role,
                        "dialogue_count": character.dialogue_count,
                        "examples": character.examples or [],
                        "chapters": str(chapter.number),
                    })

        self.rows[1:] = sorted(
            self.rows[1:],
            key=lambda x: (-x["dialogue_count"], x["name"].casefold()),
        )
        for row in self.rows:
            self.list.addItem(
                QListWidgetItem(
                    f"{row['name']}  ·  {row['role']}  ·  "
                    f"{row['dialogue_count']} dialogue cues"
                )
            )
        self.summary.setText(
            f"Detected {max(0, len(self.rows)-1)} possible story characters + narrator. "
            "Review before generation."
        )
        if self.rows:
            self.list.setCurrentRow(0)

    def show_details(self, index):
        if not (0 <= index < len(self.rows)):
            return
        row = self.rows[index]
        examples = row["examples"] or []
        text = (
            f"<b>{row['name']}</b><br>"
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Chapters: {row['chapters']}<br><br>"
            "<b>Dialogue examples</b><br>"
            + "<br>".join(f"• {x}" for x in examples)
        )
        self.details.setText(text)

    def assign_voice(self):
        index = self.list.currentRow()
        voice = self.profile.currentData()
        if index < 0 or not voice:
            return
        self.rows[index]["voice"] = voice
        self.details.setText(
            self.details.text() + f"<br><br><b>Assigned:</b> {voice}"
        )
