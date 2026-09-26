from __future__ import annotations

from pathlib import Path

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
from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state


class VoiceCastPage(QWidget):
    """Reviewable narrator/character cast for the current book."""

    def __init__(self, get_chapters, get_source=None, parent=None):
        super().__init__(parent)
        self.get_chapters = get_chapters
        self.get_source = get_source or (lambda: None)
        self.profiles = []
        self.rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        root.addWidget(QLabel("<h1>Voice Cast</h1>"))
        intro = QLabel(
            "Analyze the original book, review likely narrator/story/background characters, "
            "then assign a saved voice profile. Nothing is changed until you generate."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        actions = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze Original Book")
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
        self._load_saved_cast()

    def _project_folder(self):
        project = getattr(self.window(), "project", None)
        return getattr(project, "folder", None)

    def _saved_assignments(self) -> dict[str, str]:
        folder = self._project_folder()
        if not folder:
            return {}
        state = load_state(folder)
        value = state.get("voice_cast", {})
        return value if isinstance(value, dict) else {}

    def refresh_profiles(self):
        self.profiles = load_profiles()
        self.profile.clear()
        for profile in self.profiles:
            self.profile.addItem(profile.name, profile.name)
        if not self.profiles:
            self.profile.addItem("No saved voice profiles", None)

    def analyze(self):
        chapters = self.get_chapters() or []
        source = self.get_source()

        # Existing projects can contain a chapter split created by an older
        # detector. Analyze the original source directly so Voice Cast does not
        # inherit that stale split and miss most dialogue/characters.
        source_used = False
        if source:
            try:
                source_path = Path(source)
                if source_path.exists():
                    book = extract_text(source_path)
                    fresh = detect_chapters(book.text)
                    if fresh:
                        chapters = fresh
                        source_used = True
            except Exception:
                # Character analysis must remain usable even when the original
                # source cannot be re-read; fall back to the current chapters.
                pass

        saved = self._saved_assignments()
        saved_by_name = {str(k).casefold(): str(v) for k, v in saved.items() if v}

        self.list.clear()
        self.rows = [{
            "name": "Narrator",
            "role": "Narrator",
            "dialogue_count": 0,
            "examples": [],
            "chapters": "All chapters",
            "voice": saved_by_name.get("narrator"),
        }]

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
                    name = character.name
                    self.rows.append({
                        "name": name,
                        "role": character.role,
                        "dialogue_count": character.dialogue_count,
                        "examples": character.examples or [],
                        "chapters": str(chapter.number),
                        "voice": saved_by_name.get(name.casefold()),
                    })

        self.rows[1:] = sorted(
            self.rows[1:],
            key=lambda x: (-x["dialogue_count"], x["name"].casefold()),
        )
        self._refresh_cast_labels()
        self._save_cast()

        source_note = " from the original source" if source_used else " from the current chapters"
        self.summary.setText(
            f"Detected {max(0, len(self.rows)-1)} possible story characters + narrator"
            f"{source_note}. Review before generation."
        )
        if self.rows:
            self.list.setCurrentRow(0)

    def show_details(self, index):
        if not (0 <= index < len(self.rows)):
            return
        row = self.rows[index]
        examples = row["examples"] or []
        assigned = row.get("voice")
        text = (
            f"<b>{row['name']}</b><br>"
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Chapters: {row['chapters']}<br>"
            f"Assigned voice: {assigned or 'Not assigned'}<br><br>"
            "<b>Dialogue examples</b><br>"
            + ("<br>".join(f"• {x}" for x in examples) if examples else "No confidently linked dialogue examples.")
        )
        self.details.setText(text)

    def assign_voice(self):
        index = self.list.currentRow()
        voice = self.profile.currentData()
        if index < 0 or not voice:
            return
        self.rows[index]["voice"] = voice
        self._save_cast()
        self._refresh_cast_labels()
        self.list.setCurrentRow(index)
        self.show_details(index)

    def _load_saved_cast(self):
        saved = self._saved_assignments()
        if not saved:
            return
        saved_by_name = {str(k).casefold(): str(v) for k, v in saved.items() if v}
        for row in self.rows:
            row["voice"] = saved_by_name.get(row["name"].casefold())
        self._refresh_cast_labels()

    def _refresh_cast_labels(self):
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for row in self.rows:
            assigned = f"  → {row.get('voice')}" if row.get("voice") else ""
            self.list.addItem(
                QListWidgetItem(
                    f"{row['name']}  ·  {row['role']}  ·  "
                    f"{row['dialogue_count']} dialogue cues{assigned}"
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
            row["name"]: row.get("voice")
            for row in self.rows
            if row.get("voice")
        }
        save_state(folder, state)
