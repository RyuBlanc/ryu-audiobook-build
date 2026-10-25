from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from html import escape
from pathlib import Path
import re
import shutil
import tempfile
import traceback
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from app.chapters.assignment_utils import normalize_assignment
from app.chapters.character_learning import (
    load_learning_examples, prepare_learning_index, rank_speaker_suggestions,
    record_assignment_feedback, remove_assignment_feedback,
    source_grounded_speaker_for_continuity,
)
from app.chapters.dialogue import dialogue_segments
from app.core.character_library import list_characters
from app.core.state import load_state, save_state
from app.tts.qwen_character_runtime import best_voice_design_kind, model_installed, runtime_ready
from app.tts.voice_profile import load_profiles
from app.ui.voice_page import VoicePreviewWorker


_QUOTE_FALLBACK = re.compile(r"“[^”\n]{2,}”|「[^」\n]{2,}」|『[^』\n]{2,}』|\"[^\"\n]{2,}\"")


class NativeDialogueAnalysisWorker(QThread):
    """Analyze source dialogue off the UI thread and rank only series-scoped candidates."""

    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, chapters, character_rows: list[dict], series: str, parent=None):
        super().__init__(parent)
        self.chapters = deepcopy(list(chapters or []))
        self.character_rows = [dict(row) for row in (character_rows or []) if isinstance(row, dict)]
        self.series = str(series or "").strip()

    def run(self) -> None:
        try:
            known: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for row in self.character_rows:
                name = str(row.get("name") or row.get("primary_name") or "").strip()
                series = str(row.get("series") or self.series).strip()
                if not name or (series and self.series and series.casefold() != self.series.casefold()):
                    continue
                key = (series.casefold(), name.casefold())
                if key in seen:
                    continue
                seen.add(key)
                known.append({
                    "name": name, "series": series,
                    "aliases": list(row.get("aliases") or []),
                })
            try:
                for row in list_characters(series=self.series):
                    name = str(row.get("primary_name") or "").strip()
                    series = str(row.get("series") or self.series).strip()
                    key = (series.casefold(), name.casefold())
                    if name and key not in seen:
                        seen.add(key)
                        known.append({
                            "name": name, "series": series,
                            "aliases": list(row.get("aliases") or []),
                        })
            except Exception:
                # A temporarily unavailable reusable library must not prevent
                # analysis of the active book's cast and source text.
                pass

            examples = load_learning_examples(self.series) if self.series else []
            learning_index = prepare_learning_index(examples)
            all_rows: list[dict[str, Any]] = []
            continuity_speaker = ""
            continuity_series = self.series

            total = max(1, len(self.chapters))
            for chapter_index, chapter in enumerate(self.chapters, 1):
                chapter_number = int(getattr(chapter, "number", chapter_index) or chapter_index)
                chapter_title = str(getattr(chapter, "title", "") or "")
                source = str(getattr(chapter, "text", "") or "")
                self.progress.emit(
                    f"Analyzing chapter {chapter_index}/{len(self.chapters)} · "
                    f"{chapter_title or ('Chapter ' + str(chapter_number))}"
                )
                try:
                    segments = dialogue_segments(chapter)
                except Exception:
                    self.progress.emit(f"Could not analyze dialogue cues in chapter {chapter_number}; keeping source text available.")
                    segments = []

                assignments = list(getattr(chapter, "dialogue_assignments", []) or [])
                for segment in segments:
                    start, end = int(segment.start), int(segment.end)
                    if start < 0 or end <= start or end > len(source):
                        continue
                    exact = source[start:end]
                    if not exact.strip():
                        continue

                    detected = [
                        {"name": str(name), "confidence": float(confidence), "evidence": str(evidence),
                         "series": self.series}
                        for name, confidence, evidence in (getattr(segment, "suggestions", ()) or ())
                        if str(name or "").strip()
                    ]
                    ranked = rank_speaker_suggestions(
                        chapter_text=source,
                        start=start,
                        end=end,
                        detected=detected,
                        known_characters=known,
                        learning_examples=learning_index,
                        last_speaker=continuity_speaker,
                        last_speaker_series=continuity_series,
                    )
                    manual = next((
                        item for item in assignments
                        if isinstance(item, dict)
                        and int(item.get("start", -1)) == start
                        and int(item.get("end", -1)) == end
                        and source[start:end] == str(item.get("text") or exact)
                    ), None)
                    speakers = []
                    if manual:
                        values = manual.get("speakers")
                        if isinstance(values, list):
                            speakers = [str(value).strip() for value in values if str(value).strip()]
                        elif str(manual.get("speaker") or "").strip():
                            speakers = [str(manual.get("speaker")).strip()]
                    row_id = f"{chapter_number}:{start}:{end}"
                    result = {
                        "id": row_id, "chapter_number": chapter_number,
                        "chapter_title": chapter_title, "start": start, "end": end,
                        "text": exact, "source_text": exact,
                        "suggestions": ranked[:5],
                        "assigned_speakers": speakers,
                        "assigned": bool(speakers), "skipped": False,
                    }
                    all_rows.append(result)

                    # User-confirmed assignments outrank the model. Otherwise,
                    # only a direct name + nearby speech-tag pattern may anchor
                    # later pronoun continuity; learned similarity alone cannot.
                    if speakers:
                        continuity_speaker = speakers[0]
                        continuity_series = next(
                            (str(item.get("series") or self.series) for item in known
                             if str(item.get("name") or "").casefold() == continuity_speaker.casefold()),
                            self.series,
                        )
                    else:
                        explicit = source_grounded_speaker_for_continuity(ranked)
                        if explicit:
                            continuity_speaker = explicit
                            continuity_series = next(
                                (str(item.get("series") or self.series) for item in known
                                 if str(item.get("name") or "").casefold() == explicit.casefold()),
                                self.series,
                            )
                self.progress.emit(f"Analyzed {chapter_index}/{len(self.chapters)} chapters")
            self.completed.emit(all_rows)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc(limit=6)}")


class NativeCharacterPreviewCallbackRouter(QObject):
    """Deliver character-sentence preview callbacks safely on the GUI thread."""

    def __init__(self, panel, worker, status_label=None):
        super().__init__(panel)
        self.panel = panel
        self.worker = worker
        self.status_label = status_label

    @staticmethod
    def is_live_qt_object(widget) -> bool:
        if widget is None:
            return False
        try:
            import shiboken6
            return bool(shiboken6.isValid(widget))
        except Exception:
            try:
                widget.objectName()
                return True
            except RuntimeError:
                return False

    @staticmethod
    def set_label_text(label, message: str) -> None:
        if NativeCharacterPreviewCallbackRouter.is_live_qt_object(label):
            try:
                label.setText(str(message))
            except RuntimeError:
                # The dialog can close between a queued signal and this slot.
                pass

    @Slot(str)
    def on_status(self, message: str) -> None:
        self.set_label_text(self.status_label, message)

    @Slot(str, float)
    def on_success(self, path: str, _elapsed_seconds: float) -> None:
        if self.is_live_qt_object(self.panel):
            self.panel._play_character_preview(path, self.status_label)

    @Slot(str)
    def on_failure(self, message: str) -> None:
        self.set_label_text(self.status_label, f"Voice preview failed: {message}")

    @Slot()
    def on_finished(self) -> None:
        panel = self.panel
        if self.is_live_qt_object(panel):
            panel._clear_preview_worker(self.worker)
            if getattr(panel, "_preview_status_router", None) is self:
                panel._preview_status_router = None
        self.deleteLater()


class NativeCharacterRecordDialog(QDialog):
    """Native form for creating a reusable, series-scoped character record."""

    def __init__(
        self,
        parent=None,
        *,
        series_names=None,
        profiles=None,
        default_series: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Character")
        self.setMinimumWidth(500)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        heading = QLabel("Add character to your library")
        heading.setObjectName("pageHeading")
        root.addWidget(heading)
        intro = QLabel(
            "Save a reusable character identity for this series. Aliases help speaker "
            "analysis recognize alternate names; an audio profile can be assigned now or later."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("characterRecordName")
        self.name_edit.setPlaceholderText("Canonical character name")
        self.name_edit.setClearButtonEnabled(True)

        self.series_combo = QComboBox()
        self.series_combo.setObjectName("characterRecordSeries")
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        seen_series: set[str] = set()
        for raw in list(series_names or []) + [default_series]:
            value = str(raw or "").strip()
            key = value.casefold()
            if value and key not in seen_series:
                seen_series.add(key)
                self.series_combo.addItem(value, value)
        self.series_combo.setCurrentText(str(default_series or "").strip())
        self.series_combo.setToolTip(
            "Choose an existing series or enter a new name. Keep this name consistent across volumes."
        )

        self.aliases_edit = QLineEdit()
        self.aliases_edit.setObjectName("characterRecordAliases")
        self.aliases_edit.setPlaceholderText("Optional aliases, separated by commas")
        self.aliases_edit.setClearButtonEnabled(True)

        self.profile_combo = QComboBox()
        self.profile_combo.setObjectName("characterRecordVoiceProfile")
        self.profile_combo.addItem("Unassigned", "")
        for profile in list(profiles or []):
            profile_name = str(getattr(profile, "name", "") or "").strip()
            if not profile_name:
                continue
            provider = str(getattr(profile, "provider", "") or "Voice").replace("-", " ").title()
            self.profile_combo.addItem(f"{profile_name}  ·  {provider}", profile_name)

        form.addRow("Character name", self.name_edit)
        form.addRow("Series", self.series_combo)
        form.addRow("Aliases", self.aliases_edit)
        form.addRow("Audio profile", self.profile_combo)
        root.addLayout(form)

        self.status = QLabel("A character name and series are required.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.save_button = QPushButton("Save Character")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._accept_if_valid)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

    def _accept_if_valid(self) -> None:
        name = self.name_edit.text().strip()
        series = self.series_combo.currentText().strip()
        if not name:
            self.status.setText("Enter a character name before saving.")
            self.name_edit.setFocus()
            return
        if not series:
            self.status.setText("Choose an existing series or enter a new series name.")
            self.series_combo.setFocus()
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        name = self.name_edit.text().strip()
        aliases = []
        seen_aliases = {name.casefold()}
        for raw in re.split(r"[,;]", self.aliases_edit.text()):
            alias = raw.strip()
            if alias and alias.casefold() not in seen_aliases:
                seen_aliases.add(alias.casefold())
                aliases.append(alias)
        return {
            "name": name,
            "series": self.series_combo.currentText().strip(),
            "aliases": aliases[:5],
            "voice_profile": str(self.profile_combo.currentData() or "").strip(),
        }


class NativeCharacterAssignmentDialog(QDialog):
    """Native source-passage confirmation dialog; no HTML/WebEngine controls."""

    def __init__(
        self,
        panel: "NativeCharacterDialoguePanel",
        passage: dict,
        *,
        ai_mode: bool,
    ):
        super().__init__(panel)
        self.panel = panel
        self.passage = dict(passage)
        self.ai_mode = bool(ai_mode)
        self.action = ""
        self.character_result: dict[str, Any] | None = None
        self.setWindowTitle("Assign Character" if not ai_mode else "Review Character Suggestion")
        self.resize(690, 690)
        self.setMinimumSize(520, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        title = QLabel("Review selected dialogue")
        title.setObjectName("pageHeading")
        root.addWidget(title)
        chapter = QLabel(
            f"Chapter {self.passage.get('chapter_number', '?')} · "
            f"{self.passage.get('chapter_title') or 'Untitled chapter'}"
        )
        chapter.setObjectName("muted")
        root.addWidget(chapter)
        self.sentence = QTextEdit()
        self.sentence.setReadOnly(True)
        self.sentence.setMaximumHeight(110)
        self.sentence.setPlainText(str(self.passage.get("text") or ""))
        self.sentence.setStyleSheet(
            "QTextEdit{background:#10151e;border:1px solid #343c4b;"
            "border-left:3px solid #20c981;border-radius:8px;padding:10px;}"
        )
        root.addWidget(self.sentence)

        if ai_mode:
            ai_group = QGroupBox("AI-analyzed character suggestions")
            ai_layout = QVBoxLayout(ai_group)
            self.ai_candidates = QListWidget()
            self.ai_candidates.setMaximumHeight(118)
            for candidate in self.passage.get("suggestions", []) or []:
                name = str(candidate.get("name") or "").strip()
                if not name:
                    continue
                confidence = float(candidate.get("confidence") or 0)
                series = str(candidate.get("series") or panel.default_series())
                evidence = str(candidate.get("evidence") or "Ranked from source and confirmed examples")
                item = QListWidgetItem(
                    f"{name}  ·  {series}  ·  {confidence:.0%}\n{evidence}"
                )
                item.setData(Qt.ItemDataRole.UserRole, {
                    "name": name, "series": series,
                    "aliases": list(candidate.get("aliases") or []),
                    "voice_profile": "",
                })
                self.ai_candidates.addItem(item)
            self.ai_candidates.currentItemChanged.connect(self._ai_selection_changed)
            ai_layout.addWidget(self.ai_candidates)
            root.addWidget(ai_group)
        else:
            self.ai_candidates = None

        library_group = QGroupBox("Saved / manually added characters")
        library_layout = QVBoxLayout(library_group)
        self.character_search = QLineEdit()
        self.character_search.setPlaceholderText("Search character, alias, or series…")
        self.character_search.textChanged.connect(self._filter_saved_characters)
        library_layout.addWidget(self.character_search)
        self.saved_characters = QListWidget()
        self.saved_characters.setMaximumHeight(145)
        self._saved_character_rows = panel.available_characters()
        self._fill_saved_characters()
        self.saved_characters.currentItemChanged.connect(self._saved_selection_changed)
        library_layout.addWidget(self.saved_characters)
        root.addWidget(library_group)

        create_group = QGroupBox("Create a new character")
        create_form = QFormLayout(create_group)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Canonical character name")
        self.new_series = QComboBox()
        self.new_series.setEditable(True)
        self.new_series.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        series_names = panel.available_series()
        for value in series_names:
            self.new_series.addItem(value, value)
        default_series = panel.default_series()
        if default_series and self.new_series.findText(default_series) < 0:
            self.new_series.addItem(default_series, default_series)
        self.new_series.setCurrentText(default_series)
        self.new_series.setToolTip("Choose a series or type a new series name.")
        self.new_aliases = QLineEdit()
        self.new_aliases.setPlaceholderText("Optional aliases, separated by commas")
        self.profile = QComboBox()
        self.profile.addItem("Unassigned", "")
        self._profiles = load_profiles()
        for profile in self._profiles:
            self.profile.addItem(
                f"{profile.name} · {str(profile.provider or 'Voice').replace('-', ' ').title()}",
                profile.name,
            )
        create_form.addRow("Character name", self.new_name)
        create_form.addRow("Series", self.new_series)
        create_form.addRow("Aliases", self.new_aliases)
        create_form.addRow("Audio profile", self.profile)
        root.addWidget(create_group)

        self.status = QLabel("Choose an AI suggestion or saved character, or create one.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        self.test_button = QPushButton("Test selected voice")
        self.test_button.clicked.connect(self.test_selected_voice)
        buttons.addWidget(self.test_button)
        self.assign_button = QPushButton("Assign selected")
        self.assign_button.setObjectName("primary")
        self.assign_button.clicked.connect(self.assign_selected)
        buttons.addWidget(self.assign_button)
        self.create_button = QPushButton("Create & assign")
        self.create_button.clicked.connect(self.create_and_assign)
        buttons.addWidget(self.create_button)
        self.skip_button = QPushButton("Skip suggestion")
        self.skip_button.clicked.connect(self.skip_suggestion)
        buttons.addWidget(self.skip_button)
        if self.passage.get("assigned"):
            self.unassign_button = QPushButton("Unassign")
            self.unassign_button.clicked.connect(self.unassign)
            buttons.addWidget(self.unassign_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        root.addLayout(buttons)

        if self.ai_candidates and self.ai_candidates.count():
            self.ai_candidates.setCurrentRow(0)
        elif self.saved_characters.count():
            self.saved_characters.setCurrentRow(0)
        else:
            self.test_button.setEnabled(False)

    def _candidate_from_item(self, item: QListWidgetItem | None) -> dict | None:
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return dict(value) if isinstance(value, dict) else None

    def _ai_selection_changed(self, item, _previous=None):
        value = self._candidate_from_item(item)
        if not value:
            return
        self.saved_characters.clearSelection()
        self.new_name.setText(str(value.get("name") or ""))
        self.new_series.setCurrentText(str(value.get("series") or self.panel.default_series()))
        self._select_profile(str(value.get("voice_profile") or ""))
        self.status.setText(str(next((c.get("evidence") for c in self.passage.get("suggestions", [])
                                      if c.get("name") == value.get("name")), "AI candidate selected.")))

    def _fill_saved_characters(self):
        query = str(self.character_search.text() if hasattr(self, "character_search") else "").strip().casefold()
        self.saved_characters.clear()
        for row in self._saved_character_rows:
            searchable = " ".join([
                row.get("name", ""), row.get("series", ""),
                " ".join(row.get("aliases", [])), row.get("voice_profile", ""),
            ]).casefold()
            if query and query not in searchable:
                continue
            item = QListWidgetItem(
                f"{row['name']}  ·  {row['series']}  ·  "
                f"{row.get('voice_profile') or 'Unassigned voice'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, dict(row))
            self.saved_characters.addItem(item)

    def _filter_saved_characters(self, _value):
        self._fill_saved_characters()

    def _saved_selection_changed(self, item, _previous=None):
        value = self._candidate_from_item(item)
        if not value:
            return
        if self.ai_candidates:
            self.ai_candidates.clearSelection()
        self.new_name.setText(str(value.get("name") or ""))
        self.new_series.setCurrentText(str(value.get("series") or self.panel.default_series()))
        self.new_aliases.setText(", ".join(value.get("aliases") or []))
        self._select_profile(str(value.get("voice_profile") or ""))
        self.status.setText(f"Selected {value.get('name')} from {value.get('series')}.")

    def _select_profile(self, name: str):
        index = self.profile.findData(str(name or ""))
        self.profile.setCurrentIndex(index if index >= 0 else 0)

    def _selected_character(self) -> dict | None:
        if self.ai_candidates and self.ai_candidates.currentItem() and self.ai_candidates.currentItem().isSelected():
            return self._candidate_from_item(self.ai_candidates.currentItem())
        if self.saved_characters.currentItem() and self.saved_characters.currentItem().isSelected():
            return self._candidate_from_item(self.saved_characters.currentItem())
        return None

    def test_selected_voice(self):
        profile = str(self.profile.currentData() or "")
        if not profile:
            selected = self._selected_character() or {}
            profile = str(selected.get("voice_profile") or "")
        if not profile:
            self.status.setText("Choose a saved audio profile before testing this sentence.")
            return
        self.panel.test_voice_profile(profile, str(self.passage.get("text") or ""), self.status)

    def assign_selected(self):
        value = self._selected_character()
        if not value:
            self.status.setText("Select a saved character or AI suggestion first.")
            return
        self.action = "assign"
        self.character_result = {
            **value,
            "voice_profile": str(self.profile.currentData() or value.get("voice_profile") or ""),
        }
        self.accept()

    def create_and_assign(self):
        name = self.new_name.text().strip()
        series = self.new_series.currentText().strip()
        if not name:
            self.status.setText("Enter a character name.")
            return
        if not series:
            self.status.setText("Choose an existing series or enter a new series name.")
            return
        aliases = [value.strip() for value in re.split(r"[,;\n]", self.new_aliases.text()) if value.strip()]
        self.action = "create"
        self.character_result = {
            "name": name, "series": series, "aliases": aliases,
            "voice_profile": str(self.profile.currentData() or ""),
        }
        self.accept()

    def skip_suggestion(self):
        self.action = "skip"
        self.accept()

    def unassign(self):
        self.action = "unassign"
        self.accept()


class NativeCharacterDialoguePanel(QWidget):
    """Native Qt Character assigning and Analyze Book views backed by real project data."""

    def __init__(self, cast_page, parent=None):
        super().__init__(parent or cast_page)
        self.cast_page = cast_page
        self.rows: list[dict] = []
        self._analysis_worker: NativeDialogueAnalysisWorker | None = None
        self._review_rows: list[dict] = []
        self._skipped: set[str] = set()
        self._selected_manual_chapter: int | None = None
        self._selected_ai_chapter: int | None = None
        self._preview_worker: VoicePreviewWorker | None = None
        self._preview_status_router: NativeCharacterPreviewCallbackRouter | None = None
        self._preview_dir: Path | None = None

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.78)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)

        self.manual_tab = QWidget()
        self.ai_tab = QWidget()
        self._build_manual_tab()
        self._build_ai_tab()

    def _build_manual_tab(self):
        root = QVBoxLayout(self.manual_tab)
        root.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        self.manual_refresh = QPushButton("Refresh chapters")
        self.manual_refresh.clicked.connect(self.refresh_project_data)
        toolbar.addWidget(self.manual_refresh)
        self.manual_assign_selected = QPushButton("Assign selected text")
        self.manual_assign_selected.clicked.connect(self.assign_selected_text)
        toolbar.addWidget(self.manual_assign_selected)
        toolbar.addStretch(1)
        root.addLayout(toolbar)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.manual_chapters = QListWidget()
        self.manual_chapters.setMinimumWidth(190)
        self.manual_chapters.currentRowChanged.connect(self._manual_chapter_changed)
        self.manual_story = QTextBrowser()
        self.manual_story.setOpenLinks(False)
        self.manual_story.anchorClicked.connect(self._manual_link_clicked)
        self.manual_story.setMinimumHeight(420)
        split.addWidget(self.manual_chapters)
        split.addWidget(self.manual_story)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        root.addWidget(split, 1)
        self.manual_status = QLabel("Open a project to load real chapters and dialogue assignments.")
        self.manual_status.setObjectName("muted")
        self.manual_status.setWordWrap(True)
        root.addWidget(self.manual_status)

    def _build_ai_tab(self):
        root = QVBoxLayout(self.ai_tab)
        root.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        self.ai_analyze_button = QPushButton("Analyze Book / Refresh speaker suggestions")
        self.ai_analyze_button.setObjectName("primary")
        self.ai_analyze_button.clicked.connect(self.analyze_dialogue)
        toolbar.addWidget(self.ai_analyze_button)
        self.ai_refresh_button = QPushButton("Refresh")
        self.ai_refresh_button.clicked.connect(self.refresh_project_data)
        toolbar.addWidget(self.ai_refresh_button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)
        self.ai_summary = QLabel("AI suggestions have not been analyzed for this project yet.")
        self.ai_summary.setObjectName("muted")
        self.ai_summary.setWordWrap(True)
        root.addWidget(self.ai_summary)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.ai_chapters = QListWidget()
        self.ai_chapters.setMinimumWidth(190)
        self.ai_chapters.currentRowChanged.connect(self._ai_chapter_changed)
        self.ai_story = QTextBrowser()
        self.ai_story.setOpenLinks(False)
        self.ai_story.anchorClicked.connect(self._ai_link_clicked)
        self.ai_story.setMinimumHeight(420)
        split.addWidget(self.ai_chapters)
        split.addWidget(self.ai_story)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        root.addWidget(split, 1)
        self.ai_status = QLabel(
            "Orange indicates an unconfirmed AI suggestion. Green indicates a saved assignment. "
            "Plain text has no supported suggestion and remains available for manual assignment."
        )
        self.ai_status.setObjectName("muted")
        self.ai_status.setWordWrap(True)
        root.addWidget(self.ai_status)

    def default_series(self) -> str:
        return str(self.cast_page._series_name() or "").strip()

    def _project(self):
        return getattr(self.cast_page.window(), "project", None)

    def _chapters(self):
        try:
            return list(self.cast_page.get_chapters() or [])
        except Exception:
            project = self._project()
            return list(getattr(project, "chapters", []) or [])

    def available_series(self) -> list[str]:
        values = {self.default_series()} if self.default_series() else set()
        for row in self.cast_page.rows:
            series = str(row.get("series") or "").strip()
            if series:
                values.add(series)
        try:
            values.update(str(row.get("series") or "").strip() for row in list_characters())
        except Exception:
            pass
        return sorted((value for value in values if value), key=str.casefold)

    def available_characters(self) -> list[dict]:
        values: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for row in self.cast_page.rows:
            name = str(row.get("name") or "").strip()
            series = str(row.get("series") or self.default_series()).strip()
            if not name:
                continue
            key = (series.casefold(), name.casefold())
            if key in seen:
                continue
            seen.add(key)
            values.append({
                "name": name, "series": series,
                "aliases": list(row.get("aliases") or []),
                "voice_profile": str(row.get("voice") or row.get("voice_profile") or ""),
                "role": str(row.get("role") or "Character"),
            })
        try:
            for row in list_characters():
                name = str(row.get("primary_name") or "").strip()
                series = str(row.get("series") or "").strip()
                if not name:
                    continue
                key = (series.casefold(), name.casefold())
                if key in seen:
                    continue
                seen.add(key)
                values.append({
                    "name": name, "series": series,
                    "aliases": list(row.get("aliases") or []),
                    "voice_profile": str(row.get("voice_name") or ""),
                    "role": "Character Library",
                })
        except Exception:
            pass
        return values

    def refresh_project_data(self):
        chapters = self._chapters()
        state = self._project_state()
        self._skipped = {str(value) for value in (state.get("character_dialogue_skips") or [])}
        self.rows = list(self.cast_page.rows)
        self._fill_chapter_list(self.manual_chapters, chapters, self._selected_manual_chapter)
        self._fill_chapter_list(self.ai_chapters, chapters, self._selected_ai_chapter)
        self._render_current_chapter(False)
        self._render_current_chapter(True)

    def _project_state(self) -> dict:
        project = self._project()
        if not project or not getattr(project, "folder", None):
            return {}
        try:
            state = load_state(project.folder)
            return state if isinstance(state, dict) else {}
        except Exception:
            return {}

    def _fill_chapter_list(self, widget: QListWidget, chapters, selected_number: int | None):
        current = selected_number
        if current is None and widget.currentItem():
            try:
                current = int(widget.currentItem().data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                current = None
        was_blocked = widget.blockSignals(True)
        try:
            widget.clear()
            for chapter in chapters:
                number = int(getattr(chapter, "number", 0) or 0)
                title = str(getattr(chapter, "title", "") or f"Chapter {number}")
                unresolved = sum(
                    1 for row in self._rows_for_chapter(number)
                    if not row.get("assigned") and not row.get("skipped")
                )
                label = f"Chapter {number} · {title}"
                if unresolved:
                    label += f"  ·  {unresolved} review"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, number)
                widget.addItem(item)
                if current == number:
                    widget.setCurrentItem(item)
            if widget.currentRow() < 0 and widget.count():
                widget.setCurrentRow(0)
        finally:
            widget.blockSignals(was_blocked)
        if widget.currentRow() < 0 and chapters:
            widget.setCurrentRow(0)

    def _rows_for_chapter(self, number: int) -> list[dict]:
        return [dict(row) for row in self._review_rows if int(row.get("chapter_number", 0)) == int(number)]

    def _chapter_by_number(self, number: int):
        return next((chapter for chapter in self._chapters() if int(getattr(chapter, "number", -1)) == int(number)), None)

    def _manual_chapter_changed(self, _row: int):
        item = self.manual_chapters.currentItem()
        self._selected_manual_chapter = int(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self._render_current_chapter(False)

    def _ai_chapter_changed(self, _row: int):
        item = self.ai_chapters.currentItem()
        self._selected_ai_chapter = int(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self._render_current_chapter(True)

    def _dialogue_rows_for_view(self, chapter, ai_mode: bool) -> list[dict]:
        if chapter is None:
            return []
        number = int(getattr(chapter, "number", 0) or 0)
        source = str(getattr(chapter, "text", "") or "")
        current = {
            (int(row.get("start", -1)), int(row.get("end", -1))): dict(row)
            for row in self._rows_for_chapter(number)
            if int(row.get("start", -1)) >= 0 and int(row.get("end", -1)) > int(row.get("start", -1))
        }
        assignments = list(getattr(chapter, "dialogue_assignments", []) or [])
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            try:
                start, end = int(assignment.get("start")), int(assignment.get("end"))
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start or end > len(source):
                continue
            exact = source[start:end]
            if assignment.get("text") is not None and str(assignment.get("text")) != exact:
                continue
            existing = current.get((start, end), {})
            speakers = assignment.get("speakers")
            if not isinstance(speakers, list):
                speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
            existing.update({
                "id": f"{number}:{start}:{end}", "chapter_number": number,
                "chapter_title": str(getattr(chapter, "title", "") or ""),
                "start": start, "end": end, "text": exact, "source_text": exact,
                "assigned_speakers": [str(value) for value in speakers if str(value).strip()],
                "assigned": bool(speakers), "assignment_present": True,
            })
            current[(start, end)] = existing
        # Manual mode remains usable before AI analysis has been run; only
        # literal source quotations are recognized here and no AI name is invented.
        for match in _QUOTE_FALLBACK.finditer(source):
            start, end = match.start(), match.end()
            if (start, end) not in current:
                current[(start, end)] = {
                    "id": f"{number}:{start}:{end}", "chapter_number": number,
                    "chapter_title": str(getattr(chapter, "title", "") or ""),
                    "start": start, "end": end, "text": match.group(0), "source_text": match.group(0),
                    "suggestions": [], "assigned_speakers": [], "assigned": False,
                    "assignment_present": False,
                }
        rows = []
        for (start, end), row in current.items():
            key = f"{number}:{start}:{end}"
            row["skipped"] = key in self._skipped
            if not row.get("assigned") and row["skipped"]:
                row["suggestions"] = []
            rows.append(row)
        return sorted(rows, key=lambda row: (row["start"], row["end"]))

    def _render_current_chapter(self, ai_mode: bool):
        chapters_widget = self.ai_chapters if ai_mode else self.manual_chapters
        browser = self.ai_story if ai_mode else self.manual_story
        item = chapters_widget.currentItem()
        chapter = self._chapter_by_number(int(item.data(Qt.ItemDataRole.UserRole))) if item else None
        if chapter is None:
            browser.setHtml(
                '<div style="color:#aeb6c5;padding:24px;">'
                '<b>No project chapters found.</b><br>Open or import a local book to load live chapter text.</div>'
            )
            return
        source = str(getattr(chapter, "text", "") or "")
        rows = self._dialogue_rows_for_view(chapter, ai_mode)
        cursor = 0
        pieces = []
        for row in rows:
            start, end = int(row["start"]), int(row["end"])
            if start < cursor or start >= len(source) or end > len(source) or end <= start:
                continue
            pieces.append(escape(source[cursor:start]).replace("\n", "<br>"))
            exact = source[start:end]
            speakers = list(row.get("assigned_speakers") or [])
            candidate = next(iter(row.get("suggestions") or []), {})
            confidence = float(candidate.get("confidence") or 0)
            skipped = bool(row.get("skipped"))
            if speakers:
                bg, accent = "rgba(32,201,129,.10)", "#22c982"
                label = "Assigned: " + " + ".join(speakers)
            elif ai_mode and candidate and not skipped:
                bg, accent = "rgba(239,174,53,.10)", "#efae35"
                label = "Suggested: " + str(candidate.get("name") or "Review") + f" · {confidence:.0%}"
            else:
                bg, accent = "transparent", "#b9c0ce"
                label = "Skipped suggestion" if skipped else "Unassigned · click to review"
            url = f"dialogue://{int(chapter.number)}/{start}/{end}"
            pieces.append(
                '<a href="' + url + '" style="color:' + accent + ';background:' + bg +
                ';border-left:3px solid ' + accent + ';text-decoration:none;padding:1px 3px;">' +
                '<span style="font-size:10pt;font-weight:700;">[' + escape(label) + ']</span> ' +
                escape(exact) + '</a>'
            )
            cursor = end
        pieces.append(escape(source[cursor:]).replace("\n", "<br>"))
        browser.setHtml(
            '<html><body style="background:#0b0e14;color:#e9edf5;'
            'font-family:Segoe UI;font-size:12pt;line-height:1.65;padding:12px;">' +
            ("".join(pieces) if source.strip() else
             '<div style="color:#aeb6c5;padding:18px;"><b>No chapter text.</b>'
             'Load or save source text in Chapter Studio.</div>') +
            "</body></html>"
        )
        pending = sum(1 for row in rows if not row.get("assigned") and not row.get("skipped"))
        prefix = "AI review" if ai_mode else "Character assigning"
        message = f"{prefix} · Chapter {chapter.number} · {len(rows)} source passage(s) · {pending} awaiting review"
        if ai_mode:
            self.ai_summary.setText(message + ". Orange is a suggestion, not a saved assignment.")
        else:
            self.manual_status.setText(message + ". Green passages are saved assignments; plain text is unassigned.")

    def _decode_link(self, url: QUrl) -> dict | None:
        try:
            chapter_number = int(url.host())
            parts = [part for part in url.path().split("/") if part]
            start, end = int(parts[0]), int(parts[1])
        except (TypeError, ValueError, IndexError):
            return None
        chapter = self._chapter_by_number(chapter_number)
        if chapter is None:
            return None
        source = str(getattr(chapter, "text", "") or "")
        if start < 0 or end <= start or end > len(source):
            return None
        exact = source[start:end]
        if not exact:
            return None
        row = next((row for row in self._dialogue_rows_for_view(chapter, True)
                    if row["start"] == start and row["end"] == end), {})
        return {
            "id": f"{chapter_number}:{start}:{end}", "chapter_number": chapter_number,
            "chapter_title": str(getattr(chapter, "title", "") or ""),
            "start": start, "end": end, "text": exact, "source_text": exact,
            "suggestions": list(row.get("suggestions") or []),
            "assigned_speakers": list(row.get("assigned_speakers") or []),
            "assigned": bool(row.get("assigned")), "assignment_present": bool(row.get("assignment_present")),
            "skipped": bool(row.get("skipped")),
        }

    def _manual_link_clicked(self, url: QUrl):
        row = self._decode_link(url)
        if not row:
            QMessageBox.warning(self, "Passage unavailable", "The selected passage no longer matches the saved chapter text. Refresh and try again.")
            return
        self._open_assignment_dialog(row, ai_mode=False)

    def _ai_link_clicked(self, url: QUrl):
        row = self._decode_link(url)
        if not row:
            QMessageBox.warning(self, "Passage unavailable", "The selected passage no longer matches the saved chapter text. Refresh or rerun analysis.")
            return
        self._open_assignment_dialog(row, ai_mode=True)

    def assign_selected_text(self):
        browser = self.manual_story
        text = browser.textCursor().selectedText().replace("\u2029", "\n").strip()
        if not text:
            QMessageBox.information(self, "Select source text", "Select a sentence or dialogue passage in the chapter text first.")
            return
        chapter = self._chapter_by_number(self._selected_manual_chapter or 0)
        source = str(getattr(chapter, "text", "") or "") if chapter else ""
        start = source.find(text)
        if start < 0:
            # QTextBrowser may normalize line breaks/spacing. Permit an exact
            # whitespace-normalized match only when it is unique in the source.
            pattern = r"\s+".join(re.escape(part) for part in text.split())
            matches = list(re.finditer(pattern, source))
            if len(matches) == 1:
                start, end = matches[0].start(), matches[0].end()
            else:
                QMessageBox.warning(self, "Selection changed", "The selected text did not match a unique passage in the source. Click a quoted passage or select a longer unique sentence.")
                return
        else:
            end = start + len(text)
            if source.find(text, end) >= 0:
                QMessageBox.warning(self, "Passage is not unique", "This sentence occurs more than once. Click the exact highlighted dialogue passage or select a longer unique sentence.")
                return
        self._open_assignment_dialog({
            "id": f"{chapter.number}:{start}:{end}",
            "chapter_number": int(chapter.number), "chapter_title": str(chapter.title or ""),
            "start": start, "end": end, "text": source[start:end], "source_text": source[start:end],
            "suggestions": [], "assigned_speakers": [], "assigned": False,
        }, ai_mode=False)

    def analyze_dialogue(self):
        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            return
        chapters = self._chapters()
        if not chapters:
            self.ai_summary.setText("No chapters are available. Open a local project first.")
            return
        self.ai_analyze_button.setEnabled(False)
        self.ai_summary.setText("Analyzing source dialogue and confirmed series-specific examples…")
        self._analysis_worker = NativeDialogueAnalysisWorker(
            chapters, self.available_characters(), self.default_series(), self
        )
        self._analysis_worker.progress.connect(self.ai_summary.setText)
        self._analysis_worker.completed.connect(self._analysis_completed)
        self._analysis_worker.failed.connect(self._analysis_failed)
        self._analysis_worker.finished.connect(self._analysis_finished)
        self._analysis_worker.start()

    def _analysis_completed(self, rows: list[dict]):
        self._review_rows = [dict(row) for row in rows if isinstance(row, dict)]
        chapter_counts: dict[int, int] = {}
        for row in self._review_rows:
            if not row.get("assigned") and not row.get("skipped"):
                number = int(row.get("chapter_number", 0))
                chapter_counts[number] = chapter_counts.get(number, 0) + 1
        self._fill_chapter_list(self.manual_chapters, self._chapters(), self._selected_manual_chapter)
        self._fill_chapter_list(self.ai_chapters, self._chapters(), self._selected_ai_chapter)
        self._render_current_chapter(False)
        self._render_current_chapter(True)
        pending = sum(chapter_counts.values())
        suggested = sum(1 for row in self._review_rows if not row.get("assigned") and row.get("suggestions"))
        self.ai_summary.setText(
            f"Analyzed {len(self._chapters())} chapter(s): {len(self._review_rows)} source passage(s), "
            f"{suggested} with ranked suggestions, {pending} awaiting review. "
            "Suggestions are not saved as assignments until you confirm them."
        )

    def _analysis_failed(self, message: str):
        self.ai_summary.setText("Dialogue analysis failed. The source text was not changed. " + str(message)[:1200])

    def _analysis_finished(self):
        self.ai_analyze_button.setEnabled(True)
        self._analysis_worker = None

    def _open_assignment_dialog(self, row: dict, *, ai_mode: bool):
        dialog = NativeCharacterAssignmentDialog(self, row, ai_mode=ai_mode)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.action == "skip":
            self.skip_passage(row)
        elif dialog.action == "unassign":
            self.unassign_passage(row)
        elif dialog.action == "create" and dialog.character_result:
            character = self.cast_page.create_character_record(dialog.character_result)
            if character:
                self.assign_passage(row, character, dialog.character_result.get("voice_profile", ""))
        elif dialog.action == "assign" and dialog.character_result:
            self.assign_passage(row, dialog.character_result, dialog.character_result.get("voice_profile", ""))

    def skip_passage(self, row: dict):
        project = self._project()
        if not project:
            return
        key = f"{int(row['chapter_number'])}:{int(row['start'])}:{int(row['end'])}"
        state = load_state(project.folder)
        skipped = list(dict.fromkeys(str(value) for value in (state.get("character_dialogue_skips") or []) if str(value)))
        if key not in skipped:
            skipped.append(key)
        state["character_dialogue_skips"] = skipped
        save_state(project.folder, state)
        self._skipped.add(key)
        self._render_current_chapter(False)
        self._render_current_chapter(True)

    def assign_passage(self, passage: dict, character: dict, profile_name: str = ""):
        project = self._project()
        if project is None:
            QMessageBox.warning(self, "No project selected", "Open a local book before assigning dialogue.")
            return
        chapter = self._chapter_by_number(int(passage.get("chapter_number", 0)))
        if chapter is None:
            QMessageBox.warning(self, "Chapter unavailable", "The selected chapter was removed or changed. Refresh and choose the passage again.")
            return
        source = str(getattr(chapter, "text", "") or "")
        start, end = int(passage.get("start", -1)), int(passage.get("end", -1))
        exact = str(passage.get("text") or passage.get("source_text") or "")
        if start < 0 or end <= start or end > len(source) or source[start:end] != exact:
            QMessageBox.warning(self, "Passage changed", "The passage no longer matches the source chapter. Refresh and select it again; nothing was assigned.")
            return

        name = str(character.get("name") or character.get("primary_name") or "").strip()
        series = str(character.get("series") or self.default_series()).strip()
        aliases = list(character.get("aliases") or [])
        if not name or not series:
            QMessageBox.warning(self, "Character details required", "Choose a character and series before assigning dialogue.")
            return

        existing = list(getattr(chapter, "dialogue_assignments", []) or [])
        conflicting = [
            item for item in existing
            if isinstance(item, dict) and isinstance(item.get("start"), int) and isinstance(item.get("end"), int)
            and item["start"] < end and item["end"] > start
            and not (item["start"] == start and item["end"] == end)
        ]
        if conflicting:
            QMessageBox.warning(self, "Overlapping assignment", "The selected text overlaps a saved speaker assignment. Select the exact existing passage or remove the old assignment first.")
            return

        previous = next((item for item in existing if isinstance(item, dict)
                         and item.get("start") == start and item.get("end") == end), None)
        base = dict(previous or {"start": start, "end": end, "text": exact, "source": "manual"})
        normalized = normalize_assignment(base, [name], "single")
        normalized.update({"start": start, "end": end, "text": exact, "source": "manual",
                           "confidence": 1.0, "series": series})
        chapter.dialogue_assignments = [
            item for item in existing if not (isinstance(item, dict)
                and item.get("start") == start and item.get("end") == end)
        ] + [normalized]
        chapter.dialogue_assignments.sort(key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0))))
        try:
            project.save()
        except Exception as exc:
            # Revert the in-memory object too. Otherwise the UI could display an
            # assignment that was never persisted and a later save could commit it.
            chapter.dialogue_assignments = existing
            QMessageBox.critical(self, "Assignment could not be saved", f"The assignment was not confirmed because project saving failed:\n{exc}")
            return

        # Learn only after the project save commits. On a failed save, the old
        # assignment and its learning evidence remain intact.
        if previous:
            try:
                remove_assignment_feedback(
                    series=str(previous.get("series") or series),
                    chapter_text=source, start=start, end=end, source_text=exact,
                )
            except Exception:
                # Legacy assignments may not have a matching feedback row.
                pass

        row = self.cast_page.find_character(name, series)
        if row is None:
            row = {
                "name": name, "role": "Manually Added Character", "series": series,
                "dialogue_count": 0, "examples": [], "voice": None,
                "confidence": 1.0, "aliases": aliases,
            }
            self.cast_page.rows.append(row)
        else:
            row["series"] = series
            row["aliases"] = aliases or list(row.get("aliases") or [])
        if profile_name:
            if not any(profile.name == profile_name for profile in load_profiles()):
                QMessageBox.warning(self, "Voice profile unavailable", "This voice profile is no longer saved. The character assignment was saved, but the profile was not changed.")
            else:
                row["voice"] = profile_name
        examples = list(row.get("examples") or [])
        if exact not in examples:
            examples.insert(0, exact)
        row["examples"] = examples[:12]
        self.cast_page._refresh_character_counts()
        self.cast_page._save_cast(update_voice=bool(profile_name))
        try:
            record_assignment_feedback(
                series=series, speaker=name, aliases=aliases,
                chapter_text=source, start=start, end=end, source_text=exact,
                chapter_title=str(getattr(chapter, "title", "") or ""),
            )
        except Exception as exc:
            self.cast_page.summary.setText(f"Assignment saved; learning memory could not be updated: {exc}")
        key = f"{int(chapter.number)}:{start}:{end}"
        self._skipped.discard(key)
        self._review_rows = [
            item for item in self._review_rows
            if not (int(item.get("chapter_number", -1)) == int(chapter.number)
                    and int(item.get("start", -1)) == start and int(item.get("end", -1)) == end)
        ]
        self._review_rows.append({
            "id": key, "chapter_number": int(chapter.number), "chapter_title": str(chapter.title or ""),
            "start": start, "end": end, "text": exact, "source_text": exact,
            "suggestions": [], "assigned_speakers": [name], "assigned": True,
        })
        self._fill_chapter_list(self.manual_chapters, self._chapters(), int(chapter.number))
        self._fill_chapter_list(self.ai_chapters, self._chapters(), int(chapter.number))
        self._selected_manual_chapter = int(chapter.number)
        self._selected_ai_chapter = int(chapter.number)
        self._render_current_chapter(False)
        self._render_current_chapter(True)
        self.cast_page._refresh_labels()

    def unassign_passage(self, passage: dict):
        project = self._project()
        if not project:
            return
        chapter = self._chapter_by_number(int(passage.get("chapter_number", 0)))
        if chapter is None:
            return
        source = str(getattr(chapter, "text", "") or "")
        start, end = int(passage.get("start", -1)), int(passage.get("end", -1))
        exact = str(passage.get("text") or "")
        if start < 0 or end <= start or end > len(source) or source[start:end] != exact:
            QMessageBox.warning(self, "Passage changed", "The source text changed. Refresh before removing this assignment.")
            return
        assignments = list(getattr(chapter, "dialogue_assignments", []) or [])
        match = next((item for item in assignments if isinstance(item, dict)
                      and item.get("start") == start and item.get("end") == end), None)
        if not match:
            self.skip_passage(passage)
            return
        speakers = match.get("speakers") if isinstance(match.get("speakers"), list) else [match.get("speaker")]
        speaker = next((str(value) for value in speakers if str(value or "").strip()), "")
        series = str(match.get("series") or self.default_series())
        chapter.dialogue_assignments = [item for item in assignments if item is not match]
        try:
            project.save()
        except Exception as exc:
            # Restore the visible in-memory assignment if the save failed.
            chapter.dialogue_assignments = assignments
            QMessageBox.critical(self, "Could not save unassignment", f"The saved assignment was not removed:\n{exc}")
            return
        try:
            remove_assignment_feedback(series=series, chapter_text=source, start=start, end=end, source_text=exact)
        except Exception:
            pass
        self._review_rows = [
            item for item in self._review_rows
            if not (int(item.get("chapter_number", -1)) == int(chapter.number)
                    and int(item.get("start", -1)) == start and int(item.get("end", -1)) == end)
        ]
        self._render_current_chapter(False)
        self._render_current_chapter(True)
        self.cast_page._refresh_character_counts()
        self.cast_page._save_cast()
        self.cast_page.summary.setText(f"Removed the saved speaker assignment for {speaker or 'this passage'}; the source text was not changed.")

    def test_voice_profile(self, profile_name: str, sample_text: str, status_label: QLabel | None = None):
        profile_name = str(profile_name or "").strip()
        sample_text = str(sample_text or "").strip()
        profile = next((item for item in load_profiles() if item.name == profile_name), None)
        if profile is None or not sample_text:
            if status_label:
                status_label.setText("Choose a saved voice profile and a non-empty dialogue sentence.")
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            if status_label:
                status_label.setText("A character voice preview is already running. Wait for it to finish.")
            return
        preview_profile = profile
        if profile.provider == "qwen-character" and profile.qwen_mode == "design":
            if not runtime_ready():
                if status_label:
                    status_label.setText("Qwen runtime is not ready. Install the required model in Models, then retry.")
                return
            kind = best_voice_design_kind()
            if not model_installed(kind):
                if status_label:
                    status_label.setText(f"Install the local Qwen VoiceDesign model ({kind}) from Models first.")
                return
            preview_profile = replace(profile, qwen_mode="design-preview", model_id=kind)
        if self._preview_dir:
            try:
                self._player.stop()
                self._player.setSource(QUrl())
                shutil.rmtree(self._preview_dir, ignore_errors=True)
            except Exception:
                pass
        self._preview_dir = Path(tempfile.mkdtemp(prefix="ryu-character-sentence-preview-"))
        output = self._preview_dir / "preview.wav"
        worker = VoicePreviewWorker(preview_profile, sample_text, output, 10)
        self._preview_worker = worker
        router = NativeCharacterPreviewCallbackRouter(self, worker, status_label)
        self._preview_status_router = router
        router.set_label_text(status_label, f"Generating a real 10-second voice test with {profile.name}…")
        # QObject slots provide queued cross-thread delivery; never update labels
        # directly from VoicePreviewWorker's background thread.
        worker.status.connect(router.on_status)
        worker.finished_ok.connect(router.on_success)
        worker.failed.connect(router.on_failure)
        worker.finished.connect(router.on_finished)
        worker.start()

    def _play_character_preview(self, path: str, status_label: QLabel | None):
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        NativeCharacterPreviewCallbackRouter.set_label_text(
            status_label, "Playing the actual selected sentence using the chosen saved profile."
        )

    def _clear_preview_worker(self, worker):
        if self._preview_worker is worker:
            self._preview_worker = None

    def closeEvent(self, event):
        try:
            self._player.stop()
            self._player.setSource(QUrl())
            worker = self._preview_worker
            preview_dir = self._preview_dir
            self._preview_dir = None
            if preview_dir:
                if worker is not None and worker.isRunning():
                    # Keep the output directory alive until cancellation has
                    # unwound in the worker; deleting it immediately races WAV
                    # creation and can turn closing a panel into a synthesis error.
                    worker.cancel()
                    worker.finished.connect(
                        lambda directory=preview_dir: shutil.rmtree(directory, ignore_errors=True)
                    )
                else:
                    shutil.rmtree(preview_dir, ignore_errors=True)
        finally:
            super().closeEvent(event)
