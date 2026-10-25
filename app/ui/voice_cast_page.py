from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit, QScrollArea,
    QInputDialog, QTabWidget, QDialog, QMessageBox,
)

from app.chapters.characters import analyze_book
from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state
from app.core.character_library import sync_characters
from app.core.character_identity import character_identity_key
from app.ui.native_character_studio import NativeCharacterDialoguePanel, NativeCharacterRecordDialog


class VoiceCastAnalysisWorker(QThread):
    finished_ok = Signal(object, object, bool)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, chapters, source_path=None):
        super().__init__()
        self.chapters = list(chapters or [])
        self.source_path = source_path

    def run(self) -> None:
        try:
            chapters = list(self.chapters)
            source_used = False
            if self.source_path:
                try:
                    path = Path(self.source_path)
                    if path.exists():
                        self.progress.emit("Extracting the original manuscript…")
                        fresh = detect_chapters(extract_text(path).text)
                        if fresh:
                            chapters = fresh
                            source_used = True
                except Exception:
                    # Source extraction is best-effort; the already-loaded
                    # chapter text remains a safe fallback.
                    pass

            if not chapters:
                raise RuntimeError("There are no chapters available to analyze.")

            self.progress.emit("Analyzing characters and dialogue cues…")
            analysis = analyze_book(chapters)
            self.finished_ok.emit(chapters, analysis, source_used)
        except Exception as exc:
            self.failed.emit(str(exc))


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
            str(row.get("series") or ""),
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
        self.analysis_worker: VoiceCastAnalysisWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("voiceCastScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root.addWidget(QLabel("<h1>Voice Cast</h1>"))

        intro = QLabel(
            "Analyze the original manuscript once, review the detected story characters, "
            "and assign a consistent local voice to each one. Ambiguous dialogue is left "
            "for review instead of being silently guessed."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        series_row = QHBoxLayout()
        series_label = QLabel("Shared series / novel name")
        series_label.setToolTip("Use the same series name across volumes to reuse character identities and assigned voices.")
        series_row.addWidget(series_label)
        self.series_edit = QLineEdit()
        self.series_edit.setObjectName("characterSeriesName")
        self.series_edit.setPlaceholderText("Enter the common series name for all volumes")
        series_row.addWidget(self.series_edit, 1)
        self.save_series_button = QPushButton("Save Series")
        self.save_series_button.clicked.connect(self.save_series)
        series_row.addWidget(self.save_series_button)
        root.addLayout(series_row)
        self._loaded_project_folder: str | None = None

        actions = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze Original Book")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        actions.addWidget(self.analyze_button)

        self.refresh_button = QPushButton("Refresh Voices")
        self.refresh_button.clicked.connect(self.refresh_profiles)
        actions.addWidget(self.refresh_button)

        self.add_character_button = QPushButton("Add Character")
        self.add_character_button.clicked.connect(self.add_character)
        actions.addWidget(self.add_character_button)
        self.rename_character_button = QPushButton("Rename Character")
        self.rename_character_button.clicked.connect(self.rename_character)
        actions.addWidget(self.rename_character_button)
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
        self.search.setPlaceholderText("Search character, series, role or alias")
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
        self.test_voice_button = QPushButton("Test assigned sentence")
        self.test_voice_button.clicked.connect(self.test_assigned_sentence)
        assignment_actions.addWidget(self.assign_button)
        assignment_actions.addWidget(self.unassign_button)
        assignment_actions.addWidget(self.test_voice_button)
        form.addRow(assignment_actions)

        right.addWidget(box)
        right.addStretch(1)
        body.addLayout(right, 3)

        self.view_tabs = QTabWidget()
        cast_tab = QWidget()
        cast_tab_layout = QVBoxLayout(cast_tab)
        cast_tab_layout.setContentsMargins(4, 4, 4, 4)
        cast_tab_layout.addLayout(body, 1)
        self.view_tabs.addTab(cast_tab, "Characters assigned")
        self.dialogue_panel = NativeCharacterDialoguePanel(self)
        self.view_tabs.addTab(self.dialogue_panel.manual_tab, "Character assigning")
        self.view_tabs.addTab(self.dialogue_panel.ai_tab, "Analyze Book (AI)")
        root.addWidget(self.view_tabs, 1)

        self.refresh_profiles()
        self.load_current_project()

    def _project_folder(self):
        project = getattr(self.window(), "project", None)
        return getattr(project, "folder", None)

    def _saved_assignments(self):
        folder = self._project_folder()
        if not folder:
            return {}
        value = load_state(folder).get("voice_cast", {})
        return value if isinstance(value, dict) else {}

    def _saved_identity_assignments(self):
        folder = self._project_folder()
        if not folder:
            return {}
        value = load_state(folder).get("voice_cast_identity_assignments", {})
        return value if isinstance(value, dict) else {}

    def _saved_voice_for_identity(self, name: str, series: str, *, state=None, rows=None):
        """Load a profile by (series, name); only use legacy name keys when unambiguous."""
        folder = self._project_folder()
        if state is None:
            state = load_state(folder) if folder else {}
        identity_assignments = state.get("voice_cast_identity_assignments", {})
        if not isinstance(identity_assignments, dict):
            identity_assignments = {}
        key = character_identity_key(name, series)
        if key in identity_assignments:
            return str(identity_assignments.get(key) or "").strip() or None

        legacy_assignments = state.get("voice_cast", {})
        if not isinstance(legacy_assignments, dict):
            legacy_assignments = {}
        wanted = str(name or "").strip().casefold()
        roster = state.get("voice_cast_character_roster", [])
        roster = roster if isinstance(roster, list) else []
        identity_rows = list(self.rows if rows is None else rows)
        candidates = [*identity_rows, *[item for item in roster if isinstance(item, dict)]]
        known_series = {
            str(item.get("series") or self._series_name()).strip().casefold()
            for item in candidates
            if isinstance(item, dict)
            and str(item.get("name") or "").strip().casefold() == wanted
            and str(item.get("series") or self._series_name()).strip()
        }
        # Legacy projects keyed voices by name alone. Migrate that value only
        # if it cannot refer to two distinct series identities.
        if len(known_series) <= 1:
            return str(legacy_assignments.get(wanted) or legacy_assignments.get(name) or "").strip() or None
        return None

    def _series_name(self) -> str:
        entered = str(self.series_edit.text() or "").strip() if hasattr(self, "series_edit") else ""
        project = getattr(self.window(), "project", None)
        return entered or str(getattr(project, "title", "") or "").strip()

    def find_character(self, name: str, series: str = "") -> dict | None:
        wanted = str(name or "").strip().casefold()
        wanted_series = str(series or self._series_name()).strip().casefold()
        for row in self.rows:
            keys = {str(row.get("name") or "").strip().casefold(),
                    *(str(value).strip().casefold() for value in (row.get("aliases") or []))}
            row_series = str(row.get("series") or self._series_name()).strip().casefold()
            if wanted and wanted in keys and (not wanted_series or row_series == wanted_series):
                return row
        return None

    def create_character_record(self, payload: dict) -> dict | None:
        name = str(payload.get("name") or "").strip()
        series = str(payload.get("series") or self._series_name()).strip()
        aliases = list(dict.fromkeys(str(value).strip() for value in (payload.get("aliases") or [])
            if str(value or "").strip() and str(value).strip().casefold() != name.casefold()))[:5]
        voice = str(payload.get("voice_profile") or "").strip()
        if not name or not series:
            QMessageBox.warning(self, "Character details required", "Enter a character name and series.")
            return None

        # Character identity is the name + series pair. The same display name
        # is valid in another series and must never overwrite this series' row.
        row = next((
            item for item in self.rows
            if str(item.get("name") or "").strip().casefold() == name.casefold()
            and str(item.get("series") or self._series_name()).strip().casefold() == series.casefold()
        ), None)
        if voice and not any(profile.name == voice for profile in self.profiles):
            self.refresh_profiles()
        if voice and not any(profile.name == voice for profile in self.profiles):
            QMessageBox.warning(self, "Audio profile unavailable", "Choose a voice profile saved in Voice Studio.")
            return None
        if row is None:
            row = {"name":name,"role":"Manually Added Character","series":series,
                   "dialogue_count":0,"examples":[],"voice":voice or None,
                   "confidence":1.0,"aliases":aliases}
            self.rows.append(row)
        else:
            row.update({"name":name,"series":series,"aliases":aliases or list(row.get("aliases") or [])})
            if "voice_profile" in payload:
                row["voice"] = voice or None
        if hasattr(self, "series_edit"):
            was_blocked = self.series_edit.blockSignals(True)
            try:
                self.series_edit.setText(series)
            finally:
                self.series_edit.blockSignals(was_blocked)
        self._save_cast(update_names=True, update_voice=("voice_profile" in payload))
        self._refresh_labels()
        self.select_character_name(name, series)
        return row

    def _refresh_character_counts(self) -> None:
        chapters = list(self.get_chapters() or [])
        active_series = self._series_name().strip().casefold()
        for row in self.rows:
            name = str(row.get("name") or "").strip().casefold()
            names = {name, *(str(value).strip().casefold() for value in (row.get("aliases") or []))}
            names.discard("")
            row_series = str(row.get("series") or self._series_name()).strip().casefold()
            if not names or name == "narrator":
                continue
            count, samples = 0, []
            for chapter in chapters:
                source = str(getattr(chapter, "text", "") or "")
                for assignment in list(getattr(chapter, "dialogue_assignments", []) or []):
                    if not isinstance(assignment, dict):
                        continue
                    assignment_series = str(assignment.get("series") or active_series).strip().casefold()
                    if row_series and assignment_series and row_series != assignment_series:
                        continue
                    speakers = assignment.get("speakers") if isinstance(assignment.get("speakers"), list) else [assignment.get("speaker")]
                    if not any(str(value or "").strip().casefold() in names for value in speakers):
                        continue
                    try:
                        start, end = int(assignment.get("start")), int(assignment.get("end"))
                    except (TypeError, ValueError):
                        continue
                    if 0 <= start < end <= len(source) and source[start:end] == str(assignment.get("text") or source[start:end]):
                        count += 1
                        if source[start:end] not in samples:
                            samples.append(source[start:end])
            row["dialogue_count"] = count
            row["examples"] = (samples + [x for x in (row.get("examples") or []) if x not in samples])[:12]

    def test_assigned_sentence(self) -> None:
        row = self._row_for_visible_index(self.list.currentRow())
        if not row:
            self.summary.setText("Select a character before testing its assigned sentence.")
            return
        profile_name = str(row.get("voice") or "").strip()
        if not profile_name:
            self.summary.setText("Assign a saved voice profile to this character first.")
            return
        sample = self.dialogue_panel.assigned_sample_for_character(row)
        if not sample:
            self.summary.setText("No dialogue is assigned to this character yet. Use Character assigning first.")
            return
        self.view_tabs.setCurrentWidget(self.dialogue_panel.manual_tab)
        self.dialogue_panel.test_voice_profile(profile_name, sample, self.summary)

    def save_series(self) -> None:
        folder = self._project_folder()
        series = self._series_name()
        if not folder or not series:
            self.summary.setText("Open a book and enter a shared series name first.")
            return
        state = load_state(folder)
        state["series_name"] = series
        save_state(folder, state)
        self._sync_character_library()
        self.summary.setText(
            f"Series '{series}' saved. Characters added or analyzed in this book can now be reused across its volumes."
        )

    def _sync_character_library(self, *, update_names: bool = False, update_voice: bool = False) -> None:
        folder = self._project_folder()
        project = getattr(self.window(), "project", None)
        default_series = self._series_name()
        if not folder or not default_series or not self.rows:
            return
        grouped: dict[str, list[dict]] = {}
        for row in self.rows:
            series = str(row.get("series") or default_series).strip() or default_series
            row["series"] = series
            grouped.setdefault(series, []).append(row)
        try:
            for series, rows in grouped.items():
                sync_characters(series, rows, source_project_folder=str(folder),
                    source_project_title=str(getattr(project, "title", "") or ""),
                    update_names=update_names, update_voice=update_voice)
        except Exception as exc:
            self.summary.setText(f"Cast saved to this book; Character Library sync failed: {exc}")

    def load_current_project(self) -> None:
        folder = self._project_folder()
        key = str(folder) if folder else ""
        self.series_edit.setEnabled(folder is not None)
        self.save_series_button.setEnabled(folder is not None)
        if key == self._loaded_project_folder:
            if hasattr(self, "dialogue_panel"):
                self.dialogue_panel.refresh_project_data()
            return
        self._loaded_project_folder = key
        self.rows = []
        self.series_edit.blockSignals(True)
        if not folder:
            self.series_edit.clear()
            self.series_edit.blockSignals(False)
            self._refresh_labels()
            self.summary.setText("Open a book to analyze or edit its character cast.")
            return
        state = load_state(folder)
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        series = str(
            state.get("series_name")
            or state.get("series")
            or metadata.get("series")
            or getattr(getattr(self.window(), "project", None), "title", "")
            or ""
        ).strip()
        self.series_edit.setText(series)
        self.series_edit.blockSignals(False)
        self._load_saved_cast()
        self._refresh_character_counts()
        count = len([row for row in self.rows if row.get("name", "").casefold() != "narrator"])
        self.summary.setText(
            f"Loaded {count} saved character(s) for '{series}'. Analyze the original book to refresh the detected cast."
            if count else f"No saved cast yet for '{series}'. Analyze the original book or add a character manually."
        )
        if hasattr(self, "dialogue_panel"):
            self.dialogue_panel.refresh_project_data()

    def select_character_name(self, name: str, series: str = "") -> None:
        query = str(name or "").strip()
        if not query:
            return
        wanted_series = str(series or self._series_name()).strip().casefold()
        self.search.setText(query)
        visible = self._visible_rows()
        matches = [
            i for i, row in enumerate(visible)
            if str(row.get("name") or "").casefold() == query.casefold()
            or query.casefold() in [str(alias).casefold() for alias in (row.get("aliases") or [])]
        ]
        index = next((
            i for i in matches
            if str(visible[i].get("series") or self._series_name()).strip().casefold() == wanted_series
        ), matches[0] if matches else -1)
        if index >= 0:
            self.list.setCurrentRow(index)

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
        if self.analysis_worker is not None and self.analysis_worker.isRunning():
            return

        chapters = list(self.get_chapters() or [])
        source = self.get_source()

        if not chapters and not source:
            self.summary.setText("No chapter text is available to analyze.")
            return

        self.analyze_button.setEnabled(False)
        self.summary.setText("Preparing character analysis… The interface remains responsive.")
        self.analysis_worker = VoiceCastAnalysisWorker(chapters, source)
        self.analysis_worker.progress.connect(self.summary.setText)
        self.analysis_worker.finished_ok.connect(self._analysis_finished)
        self.analysis_worker.failed.connect(self._analysis_failed)
        self.analysis_worker.finished.connect(self._analysis_worker_finished)
        self.analysis_worker.start()

    def _analysis_finished(self, chapters, analysis, source_used):
        folder = self._project_folder()
        state = load_state(folder) if folder else {}
        legacy_saved = state.get("voice_cast", {}) if isinstance(state, dict) else {}
        if not isinstance(legacy_saved, dict):
            legacy_saved = {}
        active_series = self._series_name()
        series_by_identity = {
            character_identity_key(
                str(row.get("name") or ""),
                str(row.get("series") or active_series),
            ): str(row.get("series") or active_series)
            for row in self.rows if isinstance(row, dict) and row.get("name")
        }
        rows = [{
            "name": "Narrator",
            "role": "Audiobook Narrator",
            "dialogue_count": 0,
            "examples": [],
            "voice": legacy_saved.get("Narrator") or legacy_saved.get("narrator"),
            "confidence": 1.0,
            "aliases": [],
            "series": active_series,
        }]

        for character in analysis.characters:
            character_series = series_by_identity.get(
                character_identity_key(character.name, active_series), active_series
            )
            rows.append({
                "name": character.name, "role": character.role,
                "dialogue_count": character.dialogue_count, "examples": character.examples,
                "voice": None, "confidence": character.confidence,
                "aliases": character.aliases, "series": character_series,
            })

        # Preserve user-created cast members that automatic analysis did not rediscover.
        # The roster is merged by the series-scoped (series, name) identity.
        roster = state.get("voice_cast_character_roster", []) if isinstance(state, dict) else []
        roster = roster if isinstance(roster, list) else []
        known = {
            character_identity_key(str(row.get("name") or ""), str(row.get("series") or active_series))
            for row in rows if row.get("name")
        }
        for saved_row in roster:
            if not isinstance(saved_row, dict):
                continue
            name = str(saved_row.get("name") or "").strip()
            series = str(saved_row.get("series") or active_series).strip()
            if not name or name.casefold() == "narrator":
                continue
            identity = character_identity_key(name, series)
            if identity in known:
                continue
            rows.append({
                "name": name,
                "role": str(saved_row.get("role") or "Manually Added Character"),
                "dialogue_count": int(saved_row.get("dialogue_count") or 0),
                "examples": list(saved_row.get("examples") or []),
                "voice": None,
                "confidence": float(saved_row.get("confidence", 1.0)),
                "aliases": list(saved_row.get("aliases") or []),
                "series": series,
            })
            known.add(identity)

        self.rows = rows
        for row in self.rows:
            row.setdefault("series", active_series)
            if str(row.get("name") or "").casefold() == "narrator":
                row["voice"] = legacy_saved.get("Narrator") or legacy_saved.get("narrator")
            else:
                row["voice"] = self._saved_voice_for_identity(
                    str(row.get("name") or ""),
                    str(row.get("series") or active_series),
                    state=state,
                    rows=self.rows,
                )
        self._refresh_character_counts()
        self._save_cast()
        if hasattr(self, "dialogue_panel"):
            self.dialogue_panel.refresh_project_data()
            self.dialogue_panel.analyze_dialogue()

        source_note = " from the original source" if source_used else " from the current chapters"
        self.summary.setText(
            f"Detected {len(rows)-1} story cast candidates + audiobook narrator{source_note}. "
            f"Dialogue cues: {analysis.dialogue_total}; "
            f"unassigned/ambiguous: {analysis.unassigned_dialogue}. Review before generation."
        )
        self._refresh_labels()
        if rows:
            self.list.setCurrentRow(0)

    def _analysis_failed(self, message: str):
        self.summary.setText(f"Character analysis failed: {message}")
        self.review_hint.setText(
            "The original chapter text is unchanged. You can retry the analysis."
        )

    def _analysis_worker_finished(self):
        self.analyze_button.setEnabled(True)
        self.analysis_worker = None

    def show_details(self, index):
        row = self._row_for_visible_index(index)
        if not row:
            if self.details.text() != "Select a cast member.":
                self.details.setText("Select a cast member.")
            if self.examples.toPlainText():
                self.examples.clear()
            return

        aliases = row.get("aliases") or []
        confidence = float(row.get("confidence", 0.0))
        assigned = row.get("voice") or "Not assigned"
        details_text = (
            f"<h3>{row['name']}</h3>"
            f"Series: {row.get('series') or self._series_name()}<br>"
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Confidence: {confidence:.0%} • {confidence_band(confidence)}<br>"
            f"Aliases: {', '.join(aliases) if aliases else 'None'}<br>"
            f"Assigned voice: {assigned}"
        )
        if self.details.text() != details_text:
            self.details.setText(details_text)

        examples = row.get("examples") or []
        example_text = (
            "\n".join(f"• {value}" for value in examples)
            if examples
            else "No confidently linked dialogue examples."
        )
        if self.examples.toPlainText() != example_text:
            self.examples.setPlainText(example_text)

        if assigned:
            voice_index = self.profile.findData(assigned)
            if voice_index >= 0 and self.profile.currentIndex() != voice_index:
                self.profile.setCurrentIndex(voice_index)
    def assign_voice(self):
        row = self._row_for_visible_index(self.list.currentRow())
        voice = self.profile.currentData()
        if not row or not voice:
            return

        row["voice"] = voice
        self._save_cast(update_voice=True)
        self._refresh_labels()

    def unassign_voice(self):
        row = self._row_for_visible_index(self.list.currentRow())
        if not row:
            return

        row["voice"] = None
        self._save_cast(update_voice=True)
        self._refresh_labels()

    def _load_saved_cast(self):
        folder = self._project_folder()
        state = load_state(folder) if folder else {}
        roster = state.get("voice_cast_character_roster", [])
        roster = roster if isinstance(roster, list) else []
        active_series = self._series_name()
        existing = {
            character_identity_key(
                str(row.get("name") or ""),
                str(row.get("series") or active_series),
            )
            for row in self.rows if row.get("name")
        }
        for item in roster:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            series = str(item.get("series") or active_series).strip()
            if not name or name.casefold() == "narrator":
                continue
            identity = character_identity_key(name, series)
            if identity in existing:
                continue
            self.rows.append({
                "name": name,
                "role": str(item.get("role") or "Manually Added Character"),
                "dialogue_count": int(item.get("dialogue_count") or 0),
                "examples": list(item.get("examples") or []),
                "voice": None,
                "confidence": float(item.get("confidence", 1.0)),
                "aliases": list(item.get("aliases") or []),
                "series": series,
            })
            existing.add(identity)
        for row in self.rows:
            row.setdefault("series", active_series)
            row["voice"] = self._saved_voice_for_identity(
                str(row.get("name") or ""),
                str(row.get("series") or active_series),
                state=state,
                rows=self.rows,
            )
        self._refresh_labels()

    def add_character(self):
        dialog = NativeCharacterRecordDialog(self,
            series_names=self.dialogue_panel.available_series(),
            profiles=load_profiles(), default_series=self._series_name())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.values()
        if payload["name"].casefold() == "narrator":
            self.summary.setText("The narrator is reserved and cannot be added as a story character.")
            return
        row = self.create_character_record(payload)
        if row:
            self.summary.setText(f"Added '{row['name']}' to the '{row['series']}' series and Character Library.")
            self.dialogue_panel.refresh_project_data()

    def rename_character(self):
        row = self._row_for_visible_index(self.list.currentRow())
        if not row:
            self.summary.setText("Select a character to rename.")
            return
        if row["name"].casefold() == "narrator":
            self.summary.setText("The audiobook narrator cannot be renamed as a story character.")
            return
        old_name = row["name"]
        name, ok = QInputDialog.getText(
            self, "Rename Character", "New character name:", text=old_name
        )
        name = str(name or "").strip()
        if not ok or not name or name == old_name:
            return
        row_series = str(row.get("series") or self._series_name()).strip().casefold()
        if name.casefold() == "narrator" or any(
            item is not row
            and str(item.get("name") or "").strip().casefold() == name.casefold()
            and str(item.get("series") or self._series_name()).strip().casefold() == row_series
            for item in self.rows
        ):
            self.summary.setText("That character name already exists in this series or is reserved for the narrator.")
            return
        row["name"] = name
        aliases = list(row.get("aliases") or [])
        if old_name not in aliases:
            aliases.append(old_name)
        row["aliases"] = aliases
        folder = self._project_folder()
        if folder:
            state = load_state(folder)
            # The series-scoped identity map is rebuilt by _save_cast below.
            # Do not rename a legacy name-only key that may belong to another series.
            if state.get("voice_cast_narrating_character") == old_name:
                state["voice_cast_narrating_character"] = name
            save_state(folder, state)
        self._save_cast(update_names=True)
        self._refresh_labels()
        self.select_character_name(name, row_series)
        self.summary.setText(f"Renamed '{old_name}' to '{name}'.")


    def _refresh_labels(self):
        current_item = self.list.currentItem()
        current_identity = ""
        current_name = ""
        if current_item is not None:
            current_name = str(
                current_item.data(Qt.ItemDataRole.UserRole)
                or current_item.text().split("  ·  ", 1)[0]
            ).strip()
            current_identity = str(current_item.data(Qt.ItemDataRole.UserRole + 1) or "")

        visible = self._visible_rows()
        identities = [
            character_identity_key(
                str(row.get("name") or ""),
                str(row.get("series") or self._series_name()),
            )
            for row in visible
        ]
        names = [str(row.get("name") or "") for row in visible]
        series_by_name = {}
        for row in visible:
            name_key = str(row.get("name") or "").strip().casefold()
            series_by_name.setdefault(name_key, set()).add(
                str(row.get("series") or self._series_name()).strip().casefold()
            )

        desired_labels = []
        for row in visible:
            name = str(row.get("name") or "")
            series = str(row.get("series") or self._series_name())
            label_name = f"{name}  ·  {series}" if len(series_by_name.get(name.casefold(), set())) > 1 else name
            assignment = "✓ assigned" if row.get("voice") else "· unassigned"
            confidence = float(row.get("confidence", 0.0))
            band = confidence_band(confidence)
            desired_labels.append(
                f"{label_name}  ·  {row['dialogue_count']} cues  ·  {band}  ·  {assignment}"
            )

        current_keys = [
            str(self.list.item(index).data(Qt.ItemDataRole.UserRole + 1) or "")
            for index in range(self.list.count())
        ]
        stable_order = current_keys == identities
        was_blocked = self.list.blockSignals(True)
        updates_were_enabled = self.list.updatesEnabled()
        if not stable_order and updates_were_enabled:
            self.list.setUpdatesEnabled(False)
        try:
            if stable_order:
                for index, (name, identity, label) in enumerate(zip(names, identities, desired_labels)):
                    item = self.list.item(index)
                    if item.text() != label:
                        item.setText(label)
                    item.setData(Qt.ItemDataRole.UserRole, name)
                    item.setData(Qt.ItemDataRole.UserRole + 1, identity)
            else:
                self.list.clear()
                for name, identity, label in zip(names, identities, desired_labels):
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, name)
                    item.setData(Qt.ItemDataRole.UserRole + 1, identity)
                    self.list.addItem(item)
        finally:
            self.list.blockSignals(was_blocked)
            if not stable_order and updates_were_enabled:
                self.list.setUpdatesEnabled(True)
                self.list.viewport().update()

        if visible:
            target = next((i for i, identity in enumerate(identities) if identity == current_identity), -1)
            if target < 0 and current_name:
                active_series = self._series_name().strip().casefold()
                target = next((
                    i for i, row in enumerate(visible)
                    if str(row.get("name") or "").casefold() == current_name.casefold()
                    and str(row.get("series") or active_series).strip().casefold() == active_series
                ), -1)
            if target < 0:
                target = 0
            if self.list.currentRow() != target:
                self.list.setCurrentRow(target)
            else:
                self.show_details(target)
        else:
            empty_text = "No cast members match the current filter."
            if self.details.text() != empty_text:
                self.details.setText(empty_text)
            if self.examples.toPlainText():
                self.examples.clear()

    def _save_cast(self, *, update_names: bool = False, update_voice: bool = False):
        folder = self._project_folder()
        if not folder:
            return

        state = load_state(folder)
        default_series = self._series_name()
        if default_series:
            state["series_name"] = default_series
        scoped_assignments = {}
        name_series = {}
        for row in self.rows:
            name = str(row.get("name") or "").strip()
            if not name or name.casefold() == "narrator":
                continue
            series = str(row.get("series") or default_series).strip() or default_series
            row["series"] = series
            identity = character_identity_key(name, series)
            scoped_assignments[identity] = str(row.get("voice") or "").strip()
            name_series.setdefault(name.casefold(), set()).add(series.casefold())

        state["voice_cast_character_roster"] = [
            {
                "name": str(row["name"]),
                "role": row.get("role") or "Possible Character",
                "series": str(row.get("series") or default_series),
                "dialogue_count": int(row.get("dialogue_count") or 0),
                "examples": list(row.get("examples") or []),
                "confidence": float(row.get("confidence", 0.0)),
                "aliases": list(row.get("aliases") or []),
            }
            for row in self.rows if row.get("name") and row["name"].casefold() != "narrator"
        ]
        # Persist every identity, including explicit unassigned entries, so a
        # profile from a same-named character in another series is never borrowed.
        state["voice_cast_identity_assignments"] = scoped_assignments

        legacy_assignments = {}
        for row in self.rows:
            name = str(row.get("name") or "").strip()
            if not name or name.casefold() == "narrator" or not row.get("voice"):
                continue
            if len(name_series.get(name.casefold(), set())) == 1:
                legacy_assignments[name] = row["voice"]

        previous_assignments = state.get("voice_cast", {})
        previous_assignments = previous_assignments if isinstance(previous_assignments, dict) else {}
        narrator_assignment = next(
            (row.get("voice") for row in self.rows if str(row.get("name") or "").casefold() == "narrator" and row.get("voice")),
            previous_assignments.get("Narrator") or previous_assignments.get("narrator"),
        )
        if narrator_assignment:
            legacy_assignments["Narrator"] = narrator_assignment
        state["voice_cast"] = legacy_assignments

        narrating = next(
            (
                row["name"] for row in self.rows
                if row.get("role") == "Narrating Character" and row.get("voice")
            ),
            None,
        )
        if narrating:
            state["voice_cast_narrating_character"] = narrating
        else:
            state.pop("voice_cast_narrating_character", None)

        save_state(folder, state)
        self._sync_character_library(update_names=update_names, update_voice=update_voice)
        if hasattr(self, "dialogue_panel"):
            self.dialogue_panel.rows = list(self.rows)
            self.dialogue_panel.refresh_project_data()
