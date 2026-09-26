from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from app.chapters.characters import analyze_book
from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state


class VoiceCastPage(QWidget):
    """Book-wide character casting review."""

    def __init__(self, get_chapters, get_source=None, parent=None):
        super().__init__(parent)
        self.get_chapters = get_chapters
        self.get_source = get_source or (lambda: None)
        self.rows: list[dict] = []
        self.profiles = []

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        root.addWidget(QLabel("<h1>Voice Cast</h1>"))
        intro = QLabel(
            "Analyze the original manuscript once, review the detected story characters, "
            "and assign a consistent local voice to each one. Ambiguous dialogue is left "
            "for review instead of being silently guessed."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        actions = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze Original Book")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        actions.addWidget(self.analyze_button)
        self.refresh_button = QPushButton("Refresh Voices")
        self.refresh_button.clicked.connect(self.refresh_profiles)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.summary = QLabel("No character analysis yet.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_details)
        body.addWidget(self.list, 2)

        right = QVBoxLayout()
        self.details = QLabel("Select a cast member.")
        self.details.setWordWrap(True)
        right.addWidget(self.details)

        box = QGroupBox("Voice assignment")
        form = QFormLayout(box)
        self.profile = QComboBox()
        form.addRow("Voice profile", self.profile)
        self.assign_button = QPushButton("Assign Voice")
        self.assign_button.clicked.connect(self.assign_voice)
        form.addRow(self.assign_button)
        right.addWidget(box)
        right.addStretch(1)
        body.addLayout(right, 3)
        root.addLayout(body, 1)

        self.refresh_profiles()
        self._load_saved_cast()

    def _project_folder(self):
        project = getattr(self.window(), "project", None)
        return getattr(project, "folder", None)

    def _saved_assignments(self):
        folder = self._project_folder()
        if not folder:
            return {}
        value = load_state(folder).get("voice_cast", {})
        return value if isinstance(value, dict) else {}

    def refresh_profiles(self):
        self.profiles = load_profiles()
        current = self.profile.currentData() if self.profile.count() else None
        self.profile.blockSignals(True)
        self.profile.clear()
        for item in self.profiles:
            self.profile.addItem(item.name, item.name)
        if current:
            index = self.profile.findData(current)
            if index >= 0:
                self.profile.setCurrentIndex(index)
        self.profile.blockSignals(False)

    def analyze(self):
        chapters = self.get_chapters() or []
        source = self.get_source()
        source_used = False

        if source:
            try:
                path = Path(source)
                if path.exists():
                    fresh = detect_chapters(extract_text(path).text)
                    if fresh:
                        chapters = fresh
                        source_used = True
            except Exception:
                pass

        analysis = analyze_book(chapters)
        saved = {
            str(k).casefold(): str(v)
            for k, v in self._saved_assignments().items()
            if v
        }

        rows = [{
            "name": "Narrator",
            "role": "Audiobook Narrator",
            "dialogue_count": 0,
            "examples": [],
            "voice": saved.get("narrator"),
            "confidence": 1.0,
            "aliases": [],
        }]

        for character in analysis.characters:
            # Keep plausible candidates visible even when attribution is weak so
            # the user can review and assign a voice instead of losing the character.
            rows.append({
                "name": character.name,
                "role": character.role,
                "dialogue_count": character.dialogue_count,
                "examples": character.examples,
                "voice": saved.get(character.name.casefold()),
                "confidence": character.confidence,
                "aliases": character.aliases,
            })

        self.rows = rows
        self._refresh_labels()
        self._save_cast()

        source_note = " from the original source" if source_used else " from the current chapters"
        self.summary.setText(
            f"Detected {len(rows)-1} story cast candidates + audiobook narrator{source_note}. "
            f"Dialogue cues: {analysis.dialogue_total}; "
            f"unassigned/ambiguous: {analysis.unassigned_dialogue}. Review before generation."
        )
        if rows:
            self.list.setCurrentRow(0)

    def show_details(self, index):
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        examples = row.get("examples") or []
        aliases = row.get("aliases") or []
        self.details.setText(
            f"<b>{row['name']}</b><br>"
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Confidence: {row.get('confidence', 0):.0%}<br>"
            f"Aliases: {', '.join(aliases) if aliases else 'None'}<br>"
            f"Assigned voice: {row.get('voice') or 'Not assigned'}<br><br>"
            f"<b>Real dialogue examples</b><br>"
            + (
                "<br>".join(f"• {x}" for x in examples)
                if examples
                else "No confidently linked dialogue example."
            )
        )

    def assign_voice(self):
        index = self.list.currentRow()
        voice = self.profile.currentData()
        if index < 0 or not voice:
            return
        self.rows[index]["voice"] = voice
        self._save_cast()
        self._refresh_labels()
        self.list.setCurrentRow(index)
        self.show_details(index)

    def _load_saved_cast(self):
        saved = {
            str(k).casefold(): str(v)
            for k, v in self._saved_assignments().items()
            if v
        }
        for row in self.rows:
            row["voice"] = saved.get(row["name"].casefold())
        self._refresh_labels()

    def _refresh_labels(self):
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for row in self.rows:
            voice = f"  → {row['voice']}" if row.get("voice") else "  · unassigned"
            self.list.addItem(
                QListWidgetItem(
                    f"{row['name']}  ·  {row['role']}  · "
                    f"{row['dialogue_count']} cues{voice}"
                )
            )
        self.list.blockSignals(False)
        if self.rows:
            self.list.setCurrentRow(
                max(0, min(current if current >= 0 else 0, len(self.rows) - 1))
            )

    def _save_cast(self):
        folder = self._project_folder()
        if not folder:
            return
        state = load_state(folder)
        state["voice_cast"] = {
            row["name"]: row["voice"] for row in self.rows if row.get("voice")
        }
        narrating = next(
            (
                row["name"] for row in self.rows
                if row["role"] == "Narrating Character" and row.get("voice")
            ),
            None,
        )
        if narrating:
            state["voice_cast_narrating_character"] = narrating
        else:
            state.pop("voice_cast_narrating_character", None)
        save_state(folder, state)
