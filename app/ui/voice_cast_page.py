from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit,
)

from app.chapters.characters import analyze_book
from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state


def confidence_band(value: float) -> str:
    value = max(0.0, min(1.0, float(value)))
    if value >= 0.85:
        return "High confidence"
    if value >= 0.65:
        return "Medium confidence"
    return "Needs review"


def cast_row_matches(row: dict, filter_mode: str, query: str) -> bool:
    query = (query or "").strip().casefold()
    searchable = " ".join(
        [
            str(row.get("name") or ""),
            str(row.get("role") or ""),
            " ".join(str(value) for value in (row.get("aliases") or [])),
        ]
    ).casefold()
    if query and query not in searchable:
        return False

    has_voice = bool(row.get("voice"))
    confidence = float(row.get("confidence", 0.0))
    if filter_mode == "Assigned":
        return has_voice
    if filter_mode == "Needs Voice":
        return not has_voice
    if filter_mode == "Needs Review":
        return confidence < 0.65
    return True


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

        self.review_hint = QLabel(
            "Assignments are saved automatically. Low-confidence entries stay visible for manual review."
        )
        self.review_hint.setObjectName("muted")
        self.review_hint.setWordWrap(True)
        root.addWidget(self.review_hint)

        body = QHBoxLayout()

        left = QVBoxLayout()
        filters = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("All cast", "All")
        self.filter.addItem("Assigned", "Assigned")
        self.filter.addItem("Needs Voice", "Needs Voice")
        self.filter.addItem("Needs Review", "Needs Review")
        self.filter.currentIndexChanged.connect(self._refresh_labels)
        filters.addWidget(self.filter)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search character, role or alias…")
        self.search.textChanged.connect(self._refresh_labels)
        filters.addWidget(self.search, 1)
        left.addLayout(filters)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_details)
        left.addWidget(self.list, 1)
        body.addLayout(left, 2)

        right = QVBoxLayout()
        self.details = QLabel("Select a cast member.")
        self.details.setWordWrap(True)
        right.addWidget(self.details)

        self.examples = QTextEdit()
        self.examples.setReadOnly(True)
        self.examples.setMinimumHeight(180)
        self.examples.setPlaceholderText("Real dialogue examples will appear here.")
        right.addWidget(self.examples)

        box = QGroupBox("Voice assignment")
        form = QFormLayout(box)

        self.profile = QComboBox()
        form.addRow("Voice profile", self.profile)

        assignment_actions = QHBoxLayout()
        self.assign_button = QPushButton("Assign Voice")
        self.assign_button.clicked.connect(self.assign_voice)
        self.unassign_button = QPushButton("Unassign")
        self.unassign_button.clicked.connect(self.unassign_voice)
        assignment_actions.addWidget(self.assign_button)
        assignment_actions.addWidget(self.unassign_button)
        form.addRow(assignment_actions)

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
            provider = str(item.provider or "").replace("-", " ").title()
            self.profile.addItem(f"{item.name}  ·  {provider}", item.name)

        if current:
            index = self.profile.findData(current)
            if index >= 0:
                self.profile.setCurrentIndex(index)
        self.profile.blockSignals(False)

        self.show_details(self.list.currentRow())

    def _visible_rows(self) -> list[dict]:
        mode = self.filter.currentData() or "All"
        query = self.search.text() if hasattr(self, "search") else ""
        return [
            row for row in self.rows
            if cast_row_matches(row, mode, query)
        ]

    def _row_for_visible_index(self, index: int) -> dict | None:
        visible = self._visible_rows()
        if 0 <= index < len(visible):
            return visible[index]
        return None

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
        self._save_cast()

        source_note = " from the original source" if source_used else " from the current chapters"
        self.summary.setText(
            f"Detected {len(rows)-1} story cast candidates + audiobook narrator{source_note}. "
            f"Dialogue cues: {analysis.dialogue_total}; "
            f"unassigned/ambiguous: {analysis.unassigned_dialogue}. Review before generation."
        )
        self._refresh_labels()
        if rows:
            self.list.setCurrentRow(0)

    def show_details(self, index):
        row = self._row_for_visible_index(index)
        if not row:
            self.details.setText("Select a cast member.")
            self.examples.clear()
            return

        aliases = row.get("aliases") or []
        confidence = float(row.get("confidence", 0.0))
        assigned = row.get("voice") or "Not assigned"

        self.details.setText(
            f"<h3>{row['name']}</h3>"
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Confidence: {confidence:.0%} • {confidence_band(confidence)}<br>"
            f"Aliases: {', '.join(aliases) if aliases else 'None'}<br>"
            f"Assigned voice: {assigned}"
        )

        examples = row.get("examples") or []
        self.examples.setPlainText(
            "\n".join(f"• {value}" for value in examples)
            if examples
            else "No confidently linked dialogue examples."
        )

        if assigned:
            voice_index = self.profile.findData(assigned)
            if voice_index >= 0:
                self.profile.setCurrentIndex(voice_index)

    def assign_voice(self):
        row = self._row_for_visible_index(self.list.currentRow())
        voice = self.profile.currentData()
        if not row or not voice:
            return

        row["voice"] = voice
        self._save_cast()
        self._refresh_labels()

        new_index = next(
            (
                i for i, candidate in enumerate(self._visible_rows())
                if candidate.get("name") == row.get("name")
            ),
            0,
        )
        self.list.setCurrentRow(new_index)

    def unassign_voice(self):
        row = self._row_for_visible_index(self.list.currentRow())
        if not row:
            return

        row["voice"] = None
        self._save_cast()
        self._refresh_labels()

        visible = self._visible_rows()
        if visible:
            new_index = next(
                (
                    i for i, candidate in enumerate(visible)
                    if candidate.get("name") == row.get("name")
                ),
                0,
            )
            self.list.setCurrentRow(new_index)

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
        current_row = self.list.currentRow()
        visible_before = self._visible_rows()
        current_name = (
            visible_before[current_row].get("name")
            if 0 <= current_row < len(visible_before)
            else None
        )

        visible = self._visible_rows()
        self.list.blockSignals(True)
        self.list.clear()

        for row in visible:
            assignment = "✓ assigned" if row.get("voice") else "· unassigned"
            confidence = float(row.get("confidence", 0.0))
            band = confidence_band(confidence)
            self.list.addItem(
                QListWidgetItem(
                    f"{row['name']}  ·  {row['dialogue_count']} cues  ·  "
                    f"{band}  ·  {assignment}"
                )
            )

        self.list.blockSignals(False)

        if visible:
            target = 0
            if current_name:
                target = next(
                    (
                        i for i, row in enumerate(visible)
                        if row.get("name") == current_name
                    ),
                    0,
                )
            self.list.setCurrentRow(target)
        else:
            self.details.setText("No cast members match the current filter.")
            self.examples.clear()

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
