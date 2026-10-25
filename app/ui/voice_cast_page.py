from __future__ import annotations

from pathlib import Path
import tempfile
import uuid

from PySide6.QtCore import QThread, Signal, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget, QLineEdit, QTextEdit, QScrollArea,
    QInputDialog,
)

from app.chapters.characters import Character, analyze_book, _is_plausible_name
from app.chapters.dialogue import dialogue_segments
from app.chapters.character_learning import load_learning_examples, rank_speaker_suggestions
from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state
from app.core.character_library import sync_characters, list_characters as list_reusable_characters
from app.ui.voice_page import VoicePreviewWorker


class VoiceCastAnalysisWorker(QThread):
    finished_ok = Signal(object, object, bool)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, chapters, source_path=None, series_name: str = "", known_characters=None):
        super().__init__()
        self.chapters = list(chapters or [])
        self.source_path = source_path
        self.series_name = str(series_name or "").strip()
        self.known_characters = [dict(row) for row in (known_characters or []) if isinstance(row, dict)]

    def _apply_series_learning(self, chapters, analysis):
        """Blend explicit source evidence and saved corrections into the native cast view."""
        feedback = load_learning_examples(self.series_name) if self.series_name else []
        try:
            shared = list_reusable_characters(self.series_name) if self.series_name else []
        except Exception:
            shared = []
        rows = [*self.known_characters, *shared]
        for item in analysis.characters:
            rows.append({
                "name": item.name, "aliases": list(item.aliases or []),
                "role": item.role, "confidence": item.confidence,
            })
        for example in feedback:
            rows.append({"name": example.get("speaker"), "aliases": example.get("aliases") or []})
        cast_map = {}
        for row in rows:
            name = str(row.get("name") or row.get("primary_name") or "").strip()
            if not name or not _is_plausible_name(name):
                continue
            aliases = row.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            aliases = list(dict.fromkeys(str(value).strip() for value in aliases
                                         if str(value or "").strip()))
            key = name.casefold()
            existing = cast_map.get(key)
            if existing is None:
                cast_map[key] = {**row, "name": name, "aliases": aliases}
            else:
                existing["aliases"] = list(dict.fromkeys([*existing.get("aliases", []), *aliases]))
        cast_rows = list(cast_map.values())
        alias_lookup = {}
        for row in cast_rows:
            alias_lookup[row["name"].casefold()] = row["name"]
            for alias in row.get("aliases", []):
                alias_lookup.setdefault(str(alias).casefold(), row["name"])

        counts, examples, confidences = {}, {}, {}
        last_by_name = {}
        for chapter in chapters:
            source = str(chapter.text or "")
            last_speaker = ""
            assignments = [row for row in (getattr(chapter, "dialogue_assignments", []) or []) if isinstance(row, dict)]
            try:
                segments = dialogue_segments(chapter)
            except Exception:
                self.progress.emit(f"Learning pass skipped a malformed dialogue segment in Chapter {chapter.number}.")
                continue
            for segment in segments:
                start, end = int(segment.start), int(segment.end)
                if start < 0 or end <= start or end > len(source):
                    continue
                exact = source[start:end]
                manual = next((row for row in assignments
                    if int(row.get("start", -1)) == start and int(row.get("end", -1)) == end
                    and source[start:end] == str(row.get("text") or exact)), None)
                speakers = []
                confidence = 0.0
                evidence = ""
                if manual:
                    raw_speakers = manual.get("speakers") if isinstance(manual.get("speakers"), list) else (
                        [manual.get("speaker")] if manual.get("speaker") else []
                    )
                    if len(raw_speakers) == 1:
                        canonical = alias_lookup.get(str(raw_speakers[0]).strip().casefold(), str(raw_speakers[0]).strip())
                        if canonical:
                            speakers, confidence, evidence = [canonical], 1.0, "Explicit saved speaker assignment."
                if not speakers:
                    detected = [
                        {"name": str(name), "confidence": float(score), "evidence": str(reason)}
                        for name, score, reason in (segment.suggestions or [])
                    ]
                    ranked = rank_speaker_suggestions(
                        chapter_text=source, start=start, end=end,
                        detected=detected, known_characters=cast_rows,
                        learning_examples=feedback, last_speaker=last_speaker,
                    )
                    if ranked and float(ranked[0].get("confidence") or 0.0) >= 0.78:
                        best = ranked[0]
                        speakers = [str(best.get("name") or "")]
                        confidence = float(best.get("confidence") or 0.0)
                        evidence = str(best.get("evidence") or "")
                if not speakers or not speakers[0]:
                    continue
                name = alias_lookup.get(speakers[0].casefold(), speakers[0])
                counts[name] = counts.get(name, 0) + 1
                examples.setdefault(name, [])
                if exact and exact not in examples[name] and len(examples[name]) < 8:
                    examples[name].append(exact)
                confidences[name] = max(confidences.get(name, 0.0), confidence)
                if confidence >= 0.85:
                    last_speaker = name
                elif not last_speaker:
                    last_speaker = ""
        existing = {str(item.name).casefold(): item for item in analysis.characters}
        for row in cast_rows:
            name = row["name"]
            key = name.casefold()
            if key not in existing:
                analysis.characters.append(Character(
                    name=name, role=str(row.get("role") or "Series character"),
                    dialogue_count=counts.get(name, 0), examples=examples.get(name, []),
                    confidence=max(float(row.get("confidence") or 0.0), confidences.get(name, 0.0)),
                    aliases=list(row.get("aliases") or []),
                ))
                existing[key] = analysis.characters[-1]
        for item in analysis.characters:
            name = alias_lookup.get(str(item.name).casefold(), item.name)
            if name in counts:
                item.dialogue_count = counts[name]
                item.examples = examples.get(name, []) or item.examples
                item.confidence = max(float(item.confidence or 0.0), confidences.get(name, 0.0))
            canonical_row = cast_map.get(str(name).casefold())
            if canonical_row:
                item.aliases = list(dict.fromkeys([*(item.aliases or []), *(canonical_row.get("aliases") or [])]))
        return analysis

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
            if self.series_name:
                self.progress.emit(f"Applying confirmed speaker corrections for {self.series_name}…")
            analysis = self._apply_series_learning(chapters, analysis)
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
        self._test_voice_worker: VoicePreviewWorker | None = None
        self._test_player = QMediaPlayer(self)
        self._test_audio_output = QAudioOutput(self)
        self._test_audio_output.setVolume(0.9)
        self._test_player.setAudioOutput(self._test_audio_output)

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
        self.series_edit = QComboBox()
        self.series_edit.setObjectName("characterSeriesName")
        self.series_edit.setEditable(True)
        self.series_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.series_edit.lineEdit().setPlaceholderText("Choose an existing series or type a new one")
        self.series_edit.lineEdit().setClearButtonEnabled(True)
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
        self.test_voice_button = QPushButton("Test Selected Voice")
        self.test_voice_button.setToolTip("Generate and play a short preview of the selected saved profile using a real dialogue passage for this character.")
        self.test_voice_button.clicked.connect(self.test_assigned_voice)
        assignment_actions.addWidget(self.test_voice_button)
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

    def _series_name(self) -> str:
        entered = str(self.series_edit.currentText() or "").strip() if hasattr(self, "series_edit") else ""
        project = getattr(self.window(), "project", None)
        return entered or str(getattr(project, "title", "") or "").strip()

    def _refresh_series_options(self, selected: str = "") -> None:
        if not hasattr(self, "series_edit"):
            return
        current = str(selected or self.series_edit.currentText() or "").strip()
        try:
            records = list_reusable_characters()
        except Exception:
            records = []
        names = {str(row.get("series") or "").strip() for row in records
                 if isinstance(row, dict) and str(row.get("series") or "").strip()}
        project = getattr(self.window(), "project", None)
        if project and str(getattr(project, "title", "") or "").strip():
            names.add(str(getattr(project, "title")).strip())
        if current:
            names.add(current)
        self.series_edit.blockSignals(True)
        try:
            self.series_edit.clear()
            self.series_edit.addItems(sorted(names, key=str.casefold))
            self.series_edit.setEditText(current)
        finally:
            self.series_edit.blockSignals(False)

    def save_series(self) -> None:
        folder = self._project_folder()
        series = self._series_name()
        if not folder or not series:
            self.summary.setText("Open a book and enter a shared series name first.")
            return
        state = load_state(folder)
        state["series_name"] = series
        save_state(folder, state)
        self._refresh_series_options(series)
        self._sync_character_library()
        self.summary.setText(
            f"Series '{series}' saved. Characters added or analyzed in this book can now be reused across its volumes."
        )

    def _sync_character_library(self, *, update_names: bool = False, update_voice: bool = False) -> None:
        folder = self._project_folder()
        project = getattr(self.window(), "project", None)
        series = self._series_name()
        if not folder or not series or not self.rows:
            return
        try:
            sync_characters(
                series,
                self.rows,
                source_project_folder=str(folder),
                source_project_title=str(getattr(project, "title", "") or ""),
                update_names=update_names,
                update_voice=update_voice,
            )
        except Exception as exc:
            # A shared registry write must not break local Character Studio work.
            self.summary.setText(f"Cast saved to this book; Character Library sync failed: {exc}")

    def load_current_project(self) -> None:
        folder = self._project_folder()
        key = str(folder) if folder else ""
        self.series_edit.setEnabled(folder is not None)
        self.save_series_button.setEnabled(folder is not None)
        if key == self._loaded_project_folder:
            return
        self._loaded_project_folder = key
        self.rows = []
        self.series_edit.blockSignals(True)
        if not folder:
            self.series_edit.clear()
            self.series_edit.blockSignals(False)
            self._refresh_series_options("")
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
        self.series_edit.setEditText(series)
        self.series_edit.blockSignals(False)
        self._refresh_series_options(series)
        self._load_saved_cast()
        count = len([row for row in self.rows if row.get("name", "").casefold() != "narrator"])
        self.summary.setText(
            f"Loaded {count} saved character(s) for '{series}'. Analyze the original book to refresh the detected cast."
            if count else f"No saved cast yet for '{series}'. Analyze the original book or add a character manually."
        )

    def select_character_name(self, name: str) -> None:
        query = str(name or "").strip()
        if not query:
            return
        self.search.setText(query)
        visible = self._visible_rows()
        index = next(
            (i for i, row in enumerate(visible)
             if str(row.get("name") or "").casefold() == query.casefold()
             or query.casefold() in [str(alias).casefold() for alias in (row.get("aliases") or [])]),
            -1,
        )
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
        self.analysis_worker = VoiceCastAnalysisWorker(
            chapters, source, series_name=self._series_name(), known_characters=self.rows
        )
        self.analysis_worker.progress.connect(self.summary.setText)
        self.analysis_worker.finished_ok.connect(self._analysis_finished)
        self.analysis_worker.failed.connect(self._analysis_failed)
        self.analysis_worker.finished.connect(self._analysis_worker_finished)
        self.analysis_worker.start()

    def _analysis_finished(self, chapters, analysis, source_used):
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

        # Preserve user-created cast members that automated analysis cannot
        # rediscover (for example, characters with no explicit speech tags).
        folder = self._project_folder()
        roster = load_state(folder).get("voice_cast_character_roster", []) if folder else []
        known = {row["name"].casefold() for row in rows}
        for saved_row in roster if isinstance(roster, list) else []:
            if not isinstance(saved_row, dict):
                continue
            name = str(saved_row.get("name") or "").strip()
            if not name or name.casefold() in known or name.casefold() == "narrator":
                continue
            rows.append({
                "name": name,
                "role": str(saved_row.get("role") or "Manually Added Character"),
                "dialogue_count": int(saved_row.get("dialogue_count") or 0),
                "examples": list(saved_row.get("examples") or []),
                "voice": saved.get(name.casefold()),
                "confidence": float(saved_row.get("confidence", 1.0)),
                "aliases": list(saved_row.get("aliases") or []),
            })
            known.add(name.casefold())

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
            f"Role: {row['role']}<br>"
            f"Dialogue cues: {row['dialogue_count']}<br>"
            f"Confidence: {confidence:.0%} • {confidence_band(confidence)}<br>"
            f"Aliases: {', '.join(aliases) if aliases else 'None'}<br>"
            f"Series: {self._series_name() or 'Unassigned series'}<br>"
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
    def test_assigned_voice(self) -> None:
        row = self._row_for_visible_index(self.list.currentRow())
        profile_name = str(self.profile.currentData() or "").strip()
        if not row:
            self.summary.setText("Select a character before testing a voice.")
            return
        if not profile_name:
            self.summary.setText("Select a saved audio profile first.")
            return
        if self._test_voice_worker is not None and self._test_voice_worker.isRunning():
            self.summary.setText("A character voice preview is already running.")
            return
        profile = next((item for item in self.profiles if item.name == profile_name), None)
        if profile is None:
            self.refresh_profiles()
            self.summary.setText(f"Saved voice profile '{profile_name}' is no longer available. Refresh and choose it again.")
            return

        canonical = str(row.get("name") or "").strip()
        aliases = {canonical.casefold(), *(str(value).casefold() for value in (row.get("aliases") or []))}
        sample = ""
        # Prefer a source span already assigned to this character, so the
        # test reflects the real project dialogue rather than fabricated text.
        for chapter in self.get_chapters() or []:
            source = str(getattr(chapter, "text", "") or "")
            for assignment in getattr(chapter, "dialogue_assignments", []) or []:
                if not isinstance(assignment, dict):
                    continue
                raw = assignment.get("speakers") if isinstance(assignment.get("speakers"), list) else (
                    [assignment.get("speaker")] if assignment.get("speaker") else []
                )
                if not any(str(name or "").strip().casefold() in aliases for name in raw):
                    continue
                try:
                    start, end = int(assignment.get("start", -1)), int(assignment.get("end", -1))
                except (TypeError, ValueError):
                    continue
                if 0 <= start < end <= len(source):
                    sample = source[start:end].strip()
                    if sample:
                        break
            if sample:
                break
        if not sample:
            examples = row.get("examples") or []
            sample = str(examples[0] if examples else "").strip()
        if not sample:
            self.summary.setText("No real dialogue example is available for this character yet. Select and assign a sentence in Chapter Studio, or analyze the original book first.")
            return

        output = Path(tempfile.gettempdir()) / f"ryu-native-cast-test-{uuid.uuid4().hex}.wav"
        worker = VoicePreviewWorker(profile, sample, output, target_seconds=10)
        self._test_voice_worker = worker
        self.test_voice_button.setEnabled(False)
        self.summary.setText(f"Generating a real preview for {canonical} with {profile_name}…")
        worker.status.connect(self.summary.setText)
        worker.finished_ok.connect(self._play_test_voice)
        worker.failed.connect(self._test_voice_failed)
        worker.cancelled.connect(self._test_voice_cancelled)
        worker.finished.connect(self._test_voice_finished)
        worker.start()

    def _play_test_voice(self, output_path: str, elapsed_seconds: float) -> None:
        try:
            self._test_player.stop()
            self._test_player.setSource(QUrl.fromLocalFile(str(Path(output_path).resolve())))
            self._test_player.play()
            self.summary.setText(f"Playing character voice preview • generated in {max(0.0, float(elapsed_seconds)):.1f}s.")
        except Exception as exc:
            self.summary.setText(f"The preview was generated but could not be played: {exc}")

    def _test_voice_failed(self, error: str) -> None:
        self.summary.setText(f"Character voice preview failed: {error}")

    def _test_voice_cancelled(self) -> None:
        self.summary.setText("Character voice preview cancelled.")

    def _test_voice_finished(self) -> None:
        self.test_voice_button.setEnabled(True)
        self._test_voice_worker = None

    def shutdown(self) -> None:
        """Stop the small character-test player before the Qt page is destroyed."""
        self._test_player.stop()
        worker = self._test_voice_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(1500)
        self._test_voice_worker = None

    def assign_voice(self):
        row = self._row_for_visible_index(self.list.currentRow())
        voice = self.profile.currentData()
        if not row or not voice:
            return

        row["voice"] = voice
        self._save_cast(update_voice=True)
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
        self._save_cast(update_voice=True)
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
        folder = self._project_folder()
        state = load_state(folder) if folder else {}
        saved = {
            str(k).casefold(): str(v)
            for k, v in self._saved_assignments().items()
            if v and str(k).casefold() != "narrator"
        }
        roster = state.get("voice_cast_character_roster", [])
        if isinstance(roster, list):
            existing = {str(row.get("name") or "").casefold() for row in self.rows}
            for item in roster:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name or name.casefold() in existing or name.casefold() == "narrator":
                    continue
                self.rows.append({
                    "name": name,
                    "role": str(item.get("role") or "Manually Added Character"),
                    "dialogue_count": int(item.get("dialogue_count") or 0),
                    "examples": list(item.get("examples") or []),
                    "voice": saved.get(name.casefold()),
                    "confidence": float(item.get("confidence", 1.0)),
                    "aliases": list(item.get("aliases") or []),
                })
                existing.add(name.casefold())
        for row in self.rows:
            row["voice"] = saved.get(row["name"].casefold())
        self._refresh_labels()

    def add_character(self):
        name, ok = QInputDialog.getText(self, "Add Character", "Character name:")
        name = str(name or "").strip()
        if not ok or not name:
            return
        if name.casefold() == "narrator" or any(
            row["name"].casefold() == name.casefold() for row in self.rows
        ):
            self.summary.setText("That character name already exists or is reserved for the narrator.")
            return
        self.rows.append({
            "name": name, "role": "Manually Added Character",
            "dialogue_count": 0, "examples": [], "voice": None,
            "confidence": 1.0, "aliases": [],
        })
        self._save_cast()
        self._refresh_labels()
        self.summary.setText(f"Added '{name}' to this book's cast.")

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
        if name.casefold() == "narrator" or any(
            item is not row and item["name"].casefold() == name.casefold()
            for item in self.rows
        ):
            self.summary.setText("That character name already exists or is reserved for the narrator.")
            return
        row["name"] = name
        aliases = list(row.get("aliases") or [])
        if old_name not in aliases:
            aliases.append(old_name)
        row["aliases"] = aliases
        folder = self._project_folder()
        if folder:
            state = load_state(folder)
            assignments = state.get("voice_cast", {})
            if isinstance(assignments, dict) and old_name in assignments:
                assignments = dict(assignments)
                assignments[name] = assignments.pop(old_name)
                state["voice_cast"] = assignments
            if state.get("voice_cast_narrating_character") == old_name:
                state["voice_cast_narrating_character"] = name
            save_state(folder, state)
        self._save_cast(update_names=True)
        self._refresh_labels()
        self.summary.setText(f"Renamed '{old_name}' to '{name}'.")


    def _refresh_labels(self):
        # Retain the selected identity from the existing widget, not from the
        # newly filtered data (the filter may already have changed).
        current_item = self.list.currentItem()
        current_name = ""
        if current_item is not None:
            current_name = str(
                current_item.data(Qt.ItemDataRole.UserRole)
                or current_item.text().split("  ·  ", 1)[0]
            ).strip()

        visible = self._visible_rows()
        desired_names = [str(row.get("name") or "") for row in visible]
        desired_labels = []
        for row in visible:
            assignment = "✓ assigned" if row.get("voice") else "· unassigned"
            confidence = float(row.get("confidence", 0.0))
            band = confidence_band(confidence)
            desired_labels.append(
                f"{row['name']}  ·  {row['dialogue_count']} cues  ·  "
                f"{band}  ·  {assignment}"
            )

        current_names = [
            str(
                self.list.item(index).data(Qt.ItemDataRole.UserRole)
                or self.list.item(index).text().split("  ·  ", 1)[0]
            ).strip()
            for index in range(self.list.count())
        ]
        stable_order = current_names == desired_names
        was_blocked = self.list.blockSignals(True)
        updates_were_enabled = self.list.updatesEnabled()
        if not stable_order and updates_were_enabled:
            self.list.setUpdatesEnabled(False)
        try:
            if stable_order:
                # Typical assignment/analysis updates only change row metadata.
                # Update the existing items without clearing the visible list.
                for index, (name, label) in enumerate(zip(desired_names, desired_labels)):
                    item = self.list.item(index)
                    if item.text() != label:
                        item.setText(label)
                    if item.data(Qt.ItemDataRole.UserRole) != name:
                        item.setData(Qt.ItemDataRole.UserRole, name)
            else:
                # Rebuild only when filtering, renaming, adding or reordering
                # actually changes which characters appear in the list.
                self.list.clear()
                for name, label in zip(desired_names, desired_labels):
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, name)
                    self.list.addItem(item)
        finally:
            self.list.blockSignals(was_blocked)
            if not stable_order and updates_were_enabled:
                self.list.setUpdatesEnabled(True)
                self.list.viewport().update()

        if visible:
            target = 0
            if current_name:
                target = next(
                    (i for i, row in enumerate(visible) if row.get("name") == current_name),
                    0,
                )
            if self.list.currentRow() != target:
                self.list.setCurrentRow(target)
            else:
                # Refresh side details after an in-place label change even if
                # the selected row itself did not move.
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
        series = self._series_name()
        if series:
            state["series_name"] = series
        # Keep the full cast roster, including manually added characters
        # without an assigned voice, so it survives restarts and re-analysis.
        state["voice_cast_character_roster"] = [
            {
                "name": row["name"],
                "role": row.get("role") or "Possible Character",
                "dialogue_count": int(row.get("dialogue_count") or 0),
                "examples": list(row.get("examples") or []),
                "confidence": float(row.get("confidence", 0.0)),
                "aliases": list(row.get("aliases") or []),
            }
            for row in self.rows if row.get("name") and row["name"].casefold() != "narrator"
        ]
        narrator_assignment = state.get("voice_cast", {}).get("Narrator") if isinstance(state.get("voice_cast"), dict) else None
        state["voice_cast"] = {
            row["name"]: row["voice"] for row in self.rows if row.get("voice")
        }
        if narrator_assignment:
            state["voice_cast"]["Narrator"] = narrator_assignment

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
        self._sync_character_library(update_names=update_names, update_voice=update_voice)
