from __future__ import annotations

from pathlib import Path
import json
import re
import time
import tempfile

from PySide6.QtCore import QObject, Signal, QUrl, QTimer, QThread
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
)

from app.chapters.detector import Chapter, detect_chapters
from app.chapters.characters import analyze_book
from app.ai.brain import _numeric_score
from app.tts.pronunciation_suggester import suggest_pronunciation, suggest_names_from_text, COMMON_ENGLISH_WORDS, is_common_english_phrase, nativeish_pronunciation
from app.documents.parser import extract_text
from app.core.state import load_state, save_state
from app.core.project import list_projects
from app.ui.metadata_widgets import HistoryComboBox, GenrePicker
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import load_profiles, VoiceProfile
from app.tts.providers.piper import PiperProvider
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.preview import build_voice_preview
from app.tts.readiness import build_generation_readiness
from app.tts.chatterbox_runtime import runtime_ready
from app.audio.assembler import DEFAULT_AUDIO_BITRATE_KBPS
from app.tts.resume import inspect_generation_state


class VoicePreviewWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    percent = Signal(int)

    def __init__(self, profile, backend, project_folder, profiles, pronunciation_dictionary,
                 text, output, narration_speed, pacing_profile, dialogue_assignments=None):
        super().__init__()
        self.profile = profile
        self.backend = backend
        self.project_folder = project_folder
        self.profiles = profiles
        self.pronunciation_dictionary = pronunciation_dictionary
        self.text = text
        self.output = output
        self.narration_speed = narration_speed
        self.pacing_profile = pacing_profile
        self.dialogue_assignments = list(dialogue_assignments or [])
        self._provider = None

    def run(self) -> None:
        try:
            self.percent.emit(5)
            self.progress.emit('[5%] Loading voice engine…')
            provider, voice = provider_from_profile(self.profile)
            self._provider = provider
            if hasattr(provider, 'backend'):
                provider.backend = self.backend

            if self.project_folder:
                state = load_state(self.project_folder)
                assignments = state.get('voice_cast', {}) if isinstance(state, dict) else {}
                if assignments:
                    from app.tts.cast_provider import CastAwareProvider
                    self._provider = CastAwareProvider(
                        provider, voice,
                        {profile.name: profile for profile in self.profiles},
                        assignments,
                        narrating_character=state.get('voice_cast_narrating_character'),
                        backend_override=self.backend,
                    )

            self.percent.emit(10)
            self.progress.emit('[10%] Voice engine ready • preparing preview segments…')

            def preview_progress(stage: str, current: int, total: int) -> None:
                total = max(1, int(total))
                current = max(0, min(total, int(current)))
                if stage == "preparing":
                    percent = 10
                    label = "Preparing preview segments…"
                elif stage == "synthesizing":
                    percent = 15 + int(70 * current / total)
                    label = f"Generating preview segment {current}/{total}…"
                elif stage == "finalizing":
                    percent = 85 + int(10 * current / total)
                    label = "Finalizing preview…"
                else:
                    percent = 10
                    label = "Preparing preview…"
                self.percent.emit(percent)
                self.progress.emit(f'[{percent}%] {label}')

            result = build_voice_preview(
                self.text,
                self._provider,
                voice,
                self.output,
                pronunciation_dictionary=self.pronunciation_dictionary,
                narration_speed=self.narration_speed,
                pacing_profile=self.pacing_profile,
                dialogue_assignments=self.dialogue_assignments,
                progress_callback=preview_progress,
            )
            self.percent.emit(100)
            self.progress.emit('[100%] Preview ready.')
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            close = getattr(self._provider, 'close', None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            self._provider = None

class PronunciationPreviewWorker(QThread):
    """Generate a short audio sample of one pronunciation override using the active voice."""
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, profile, backend, text, output):
        super().__init__()
        self.profile = profile
        self.backend = backend
        self.text = text
        self.output = output
        self._provider = None

    def run(self) -> None:
        try:
            self._provider, voice = provider_from_profile(self.profile)
            if hasattr(self._provider, "backend"):
                self._provider.backend = self.backend
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self._provider.synthesize(self.text, self.output, voice)
            if not self.output.exists() or self.output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce valid pronunciation audio.")
            self.finished_ok.emit(str(self.output))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            close = getattr(self._provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            self._provider = None


class GenerationSignals(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)


class GenerationPage(QWidget):
    def __init__(
        self,
        chapters: list[Chapter],
        audio_root: Path,
        project_folder: Path | None = None,
        project_title: str | None = None,
    ) -> None:
        super().__init__()
        self.chapters = chapters
        self.audio_root = audio_root
        self.project_folder = project_folder
        self.project_title = str(project_title or "").strip()
        self.profiles = load_profiles()
        self.signals = GenerationSignals()
        self.manager: GenerationManager | None = None
        self.started_at: float | None = None
        self.last_progress_value = 0
        self.initial_progress_value = 0
        self.generation_phase = "idle"
        self.preview_worker: VoicePreviewWorker | None = None
        self._eta_ema_sec_per_unit: float | None = None
        self._eta_last_work: int | None = None
        self._eta_last_time: float | None = None
        self._eta_warmup_samples = 0
        self._eta_rates: list[float] = []

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._player_position)
        self.player.durationChanged.connect(self._player_duration)

        self.preview_player = QMediaPlayer(self)
        self.preview_audio_output = QAudioOutput(self)
        self.preview_audio_output.setVolume(0.85)
        self.preview_player.setAudioOutput(self.preview_audio_output)
        self.preview_player.positionChanged.connect(self._preview_position)
        self.preview_player.durationChanged.connect(self._preview_duration)
        self.preview_player.playbackStateChanged.connect(self._preview_state_changed)
        self.preview_path: Path | None = None
        self.pronunciation_preview_worker: PronunciationPreviewWorker | None = None
        self.pronunciation_preview_path: Path | None = None
        self.pronunciation_player = QMediaPlayer(self)
        self.pronunciation_audio_output = QAudioOutput(self)
        self.pronunciation_audio_output.setVolume(0.85)
        self.pronunciation_player.setAudioOutput(self.pronunciation_audio_output)
        self.pronunciation_player.playbackStateChanged.connect(self._pronunciation_playback_state_changed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(6, 4, 6, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>Generate Audiobook</h2>"))
        header.addStretch(1)
        header.addWidget(QLabel("Review → Generate → Listen"))
        root.addLayout(header)

        book_name = self.project_title or (self.project_folder.name if self.project_folder else "Audiobook")
        self.title = QLineEdit(book_name)
        self.author = HistoryComboBox(self._metadata_history("author"))
        self.narrator = HistoryComboBox(self._metadata_history("narrator"))
        self.publisher = HistoryComboBox(self._metadata_history("publisher"))
        self.series = HistoryComboBox(self._metadata_history("series"))
        self.language = HistoryComboBox(self._metadata_history("language", ["en"]))
        self.year = HistoryComboBox(self._metadata_history("year"))
        self.genre = GenrePicker()
        self.genre.set_value("Audiobook")
        form = QFormLayout()
        form.addRow("Book title", self.title)
        form.addRow("Author", self.author)
        form.addRow("Narrator", self.narrator)
        form.addRow("Publisher", self.publisher)
        form.addRow("Series", self.series)
        form.addRow("Language", self.language)
        form.addRow("Release year", self.year)
        form.addRow("Genre", self.genre)
        root.addWidget(QLabel("Metadata dropdowns remember values used in your previous books. You can still type a new value. Genre supports multiple selections and custom genres."))
        root.itemAt(root.count()-1).widget().setObjectName("muted")
        root.addLayout(form)

        overview = QGroupBox("Audiobook")
        overview_layout = QHBoxLayout(overview)
        self.chapter_count = QLabel()
        self.word_count = QLabel()
        self.duration_estimate = QLabel()
        overview_layout.addWidget(self.chapter_count)
        overview_layout.addWidget(self.word_count)
        overview_layout.addWidget(self.duration_estimate)
        overview_layout.addStretch(1)
        root.addWidget(overview)
        self._update_overview()

        cast_box = QGroupBox("Voice Cast")
        cast_layout = QVBoxLayout(cast_box)
        self.cast_summary = QLabel("No character-specific voice assignments saved. Narrator voice will be used.")
        self.cast_summary.setWordWrap(True)
        cast_layout.addWidget(self.cast_summary)
        root.addWidget(cast_box)

        pronunciation_box = QGroupBox("Pronunciation Dictionary")
        pronunciation_layout = QVBoxLayout(pronunciation_box)
        pronunciation_hint = QLabel(
            "Add words or names the voice should pronounce differently. "
            "This changes only narration text; the original book remains untouched."
        )
        pronunciation_hint.setWordWrap(True)
        pronunciation_layout.addWidget(pronunciation_hint)

        self.pronunciation_table = QTableWidget(0, 3)
        self.pronunciation_table.setHorizontalHeaderLabels(["Written", "Pronounce as", "Enabled"])
        self.pronunciation_table.setWordWrap(False)
        self.pronunciation_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.pronunciation_table.setMinimumHeight(150)
        self.pronunciation_table.verticalHeader().setDefaultSectionSize(34)
        self.pronunciation_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pronunciation_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.pronunciation_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        pronunciation_layout.addWidget(self.pronunciation_table)

        pronunciation_preview_row = QHBoxLayout()
        pronunciation_preview_row.addWidget(QLabel("Test with current voice"))
        self.pronunciation_preview_test = QPushButton("▶ Test Selected")
        self.pronunciation_preview_test.clicked.connect(self._test_selected_pronunciation)
        self.pronunciation_preview_play = QPushButton("▶ Play")
        self.pronunciation_preview_play.setEnabled(False)
        self.pronunciation_preview_play.clicked.connect(self._play_pronunciation_preview)
        self.pronunciation_preview_stop = QPushButton("■ Stop")
        self.pronunciation_preview_stop.setEnabled(False)
        self.pronunciation_preview_stop.clicked.connect(self._stop_pronunciation_preview)
        self.pronunciation_preview_status = QLabel("Select a row to hear exactly how its 'Pronounce as' text sounds.")
        self.pronunciation_preview_status.setObjectName("muted")
        self.pronunciation_preview_status.setWordWrap(True)
        pronunciation_preview_row.addWidget(self.pronunciation_preview_test)
        pronunciation_preview_row.addWidget(self.pronunciation_preview_play)
        pronunciation_preview_row.addWidget(self.pronunciation_preview_stop)
        pronunciation_preview_row.addWidget(self.pronunciation_preview_status, 1)
        pronunciation_layout.addLayout(pronunciation_preview_row)

        pronunciation_actions = QHBoxLayout()
        self.add_pronunciation = QPushButton("+ Add Pronunciation")
        self.add_pronunciation.clicked.connect(self._add_pronunciation_row)
        self.suggest_pronunciation = QPushButton("Import AI Pronunciations")
        self.suggest_pronunciation.clicked.connect(self._suggest_pronunciations)
        self.remove_pronunciation = QPushButton("Remove Selected")
        self.remove_pronunciation.clicked.connect(self._remove_pronunciation_row)
        self.clean_english_pronunciations = QPushButton("Clean Obvious English")
        self.clean_english_pronunciations.clicked.connect(self._clean_obvious_english_pronunciations)
        self.save_pronunciation = QPushButton("Save Pronunciations")
        self.save_pronunciation.setObjectName("primary")
        self.save_pronunciation.clicked.connect(self._save_pronunciations)
        pronunciation_actions.addWidget(self.add_pronunciation)
        pronunciation_actions.addWidget(self.suggest_pronunciation)
        pronunciation_actions.addWidget(self.remove_pronunciation)
        pronunciation_actions.addWidget(self.clean_english_pronunciations)
        pronunciation_actions.addStretch(1)
        pronunciation_actions.addWidget(self.save_pronunciation)
        pronunciation_layout.addLayout(pronunciation_actions)

        self.pronunciation_status = QLabel("No pronunciation overrides saved for this book.")
        self.pronunciation_status.setWordWrap(True)
        pronunciation_layout.addWidget(self.pronunciation_status)
        root.addWidget(pronunciation_box)

        settings = QGroupBox("Audio settings")
        settings_form = QFormLayout(settings)

        voice_row = QHBoxLayout()
        self.voice_profile = QComboBox()
        self.refresh_voice_profiles = QPushButton("Refresh")
        self.refresh_voice_profiles.clicked.connect(self._refresh_voice_profiles)
        voice_row.addWidget(self.voice_profile, 1)
        voice_row.addWidget(self.refresh_voice_profiles)
        settings_form.addRow("Voice", voice_row)
        self._load_profiles()

        self.backend = QComboBox()
        self.backend.addItem("Automatic", "automatic")
        self.backend.addItem("CPU Only", "cpu")
        self.backend.addItem("NVIDIA CUDA", "cuda")
        self.backend.addItem("DirectML", "directml")
        settings_form.addRow("Backend", self.backend)
        self.narration_speed = QComboBox()
        self.narration_speed.addItem("0.85×  Very relaxed", 0.85)
        self.narration_speed.addItem("0.90×  Natural story", 0.90)
        self.narration_speed.addItem("0.95×  Slightly slower", 0.95)
        self.narration_speed.addItem("1.00×  Original speed", 1.00)
        self.narration_speed.setCurrentIndex(1)
        settings_form.addRow("Narration speed", self.narration_speed)

        self.pacing_profile = QComboBox()
        self.pacing_profile.addItem("Natural Story • balanced pauses", "natural")
        self.pacing_profile.addItem("Relaxed Story • longer pauses", "relaxed")
        self.pacing_profile.addItem("Minimal Pauses • lighter pacing", "minimal")
        self.pacing_profile.addItem("Off • provider timing only", "off")
        self.pacing_profile.setCurrentIndex(0)
        settings_form.addRow("Story pacing", self.pacing_profile)

        self.audio_bitrate = QComboBox()
        for kbps in (128, 160, 192, 224, 256, 288, 320):
            label = f"{kbps} kbps"
            if kbps == DEFAULT_AUDIO_BITRATE_KBPS:
                label += " • Premium recommended"
            self.audio_bitrate.addItem(label, kbps)
        self.audio_bitrate.setCurrentIndex(
            max(0, self.audio_bitrate.findData(DEFAULT_AUDIO_BITRATE_KBPS))
        )
        settings_form.addRow("Audio quality", self.audio_bitrate)
        self.pacing_hint = QLabel(
            "Adds small, sentence-aware pauses after generated narration units. "
            "The original wording is not changed."
        )
        self.pacing_hint.setWordWrap(True)
        settings_form.addRow("", self.pacing_hint)
        self.cover: Path | None = None
        cover_row = QHBoxLayout()
        self.cover_label = QLabel("No cover selected")
        self.cover_button = QPushButton("Choose Cover")
        self.cover_button.clicked.connect(self.choose_cover)
        cover_row.addWidget(self.cover_button)
        cover_row.addWidget(self.cover_label, 1)
        settings_form.addRow("Cover", cover_row)
        root.addWidget(settings)

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout(output_box)
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        output_layout.addWidget(self.output)
        output_actions = QHBoxLayout()
        self.change_output = QPushButton("Change output location…")
        self.change_output.clicked.connect(self.choose_output)
        output_actions.addWidget(self.change_output)
        output_actions.addWidget(QLabel("M4B • AAC 128–320 kbps • 256 kbps recommended"))
        output_actions.addStretch(1)
        output_layout.addLayout(output_actions)
        root.addWidget(output_box)

        preview_box = QGroupBox("Voice Preview")
        preview_layout = QVBoxLayout(preview_box)

        preview_source_row = QHBoxLayout()
        preview_source_row.addWidget(QLabel("Source"))
        self.preview_chapter = QComboBox()
        for chapter in self.chapters:
            self.preview_chapter.addItem(
                f"Chapter {chapter.number}: {chapter.title}",
                chapter.number,
            )
        self.preview_chapter.setEnabled(bool(self.chapters))
        preview_source_row.addWidget(self.preview_chapter, 1)
        preview_layout.addLayout(preview_source_row)

        preview_actions = QHBoxLayout()
        self.preview_button = QPushButton("▶  Generate Voice Preview")
        self.preview_button.clicked.connect(self.preview)
        self.preview_play_button = QPushButton("▶  Play Preview")
        self.preview_play_button.setEnabled(False)
        self.preview_play_button.clicked.connect(self.play_preview)
        self.preview_stop_button = QPushButton("■  Stop")
        self.preview_stop_button.setEnabled(False)
        self.preview_stop_button.clicked.connect(self.stop_preview)
        preview_actions.addWidget(self.preview_button, 1)
        preview_actions.addWidget(self.preview_play_button)
        preview_actions.addWidget(self.preview_stop_button)
        preview_layout.addLayout(preview_actions)

        preview_time_row = QHBoxLayout()
        self.preview_status = QLabel("Generate a preview to listen to the selected voice.")
        self.preview_time = QLabel("0:00 / 0:00")
        preview_time_row.addWidget(self.preview_status, 1)
        preview_time_row.addWidget(self.preview_time)
        preview_layout.addLayout(preview_time_row)

        self.preview_loading = QProgressBar()
        self.preview_loading.setRange(0, 100)
        self.preview_loading.setValue(0)
        self.preview_loading.setTextVisible(True)
        self.preview_loading.setFixedHeight(8)
        self.preview_loading.setVisible(False)
        preview_layout.addWidget(self.preview_loading)

        root.addWidget(preview_box)

        progress_box = QGroupBox("Generation")
        progress_layout = QVBoxLayout(progress_box)
        self.progress = QProgressBar()
        progress_layout.addWidget(self.progress)
        stats = QHBoxLayout()
        self.stage = QLabel("Ready")
        self.elapsed = QLabel("Elapsed: 0:00")
        self.remaining = QLabel("Remaining: —")
        self.speed = QLabel("Speed: —")
        stats.addWidget(self.stage)
        stats.addStretch(1)
        stats.addWidget(self.elapsed)
        stats.addWidget(self.remaining)
        stats.addWidget(self.speed)
        progress_layout.addLayout(stats)
        root.addWidget(progress_box)

        result_box = QGroupBox("Audiobook Ready")
        result_layout = QVBoxLayout(result_box)
        self.result_label = QLabel("Your finished audiobook will appear here after M4B packaging.")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        result_actions = QHBoxLayout()
        self.play_button = QPushButton("▶  Play Audiobook")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_result)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.clicked.connect(self.player.stop)
        self.open_button = QPushButton("Open Folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_result_folder)
        result_actions.addWidget(self.play_button)
        result_actions.addWidget(self.stop_button)
        result_actions.addWidget(self.open_button)
        result_layout.addLayout(result_actions)
        self.result_time = QLabel("0:00 / 0:00")
        result_layout.addWidget(self.result_time)
        root.addWidget(result_box)

        readiness_box = QGroupBox("Generation Readiness")
        readiness_layout = QVBoxLayout(readiness_box)
        self.readiness_status = QLabel("Checking generation requirements…")
        self.readiness_status.setWordWrap(True)
        readiness_layout.addWidget(self.readiness_status)
        self.readiness_details = QLabel()
        self.readiness_details.setWordWrap(True)
        readiness_layout.addWidget(self.readiness_details)
        readiness_actions = QHBoxLayout()
        self.refresh_readiness_button = QPushButton("Refresh Checks")
        self.refresh_readiness_button.clicked.connect(self._refresh_readiness)
        readiness_actions.addWidget(self.refresh_readiness_button)
        readiness_actions.addStretch(1)
        readiness_layout.addLayout(readiness_actions)
        root.addWidget(readiness_box)

        self.actions_note = QLabel()
        self.actions_note.setObjectName("muted")
        self.actions_note.setWordWrap(True)
        root.addWidget(self.actions_note)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Generate Audiobook")
        self.start_button.setObjectName("primary")
        self.resume_button = QPushButton("Resume / Retry")
        self.resume_button.setVisible(False)
        self.resume_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.start_button)
        actions.addWidget(self.resume_button)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.finished)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_live_stats)

        self.voice_profile.currentIndexChanged.connect(lambda _index: self._refresh_readiness())
        self.backend.currentIndexChanged.connect(lambda _index: self._refresh_readiness())
        self.narration_speed.currentIndexChanged.connect(lambda _index: self._refresh_readiness())
        self.pacing_profile.currentIndexChanged.connect(lambda _index: self._refresh_readiness())

        self._restore_state()
        self._load_pronunciations()
        self._load_voice_cast_summary()
        self._set_default_output()
        self._refresh_resume_state()
        self._refresh_readiness()

    def _add_pronunciation_row(self, written="", spoken="", enabled=True, source="manual"):
        from PySide6.QtCore import Qt
        row = self.pronunciation_table.rowCount()
        self.pronunciation_table.insertRow(row)
        written_item = QTableWidgetItem(written)
        spoken_item = QTableWidgetItem(spoken)
        written_item.setData(Qt.ItemDataRole.UserRole, source)
        spoken_item.setData(Qt.ItemDataRole.UserRole, source)
        self.pronunciation_table.setItem(row, 0, written_item)
        self.pronunciation_table.setItem(row, 1, spoken_item)
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, source)
        item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        self.pronunciation_table.setItem(row, 2, item)

    def _load_audiobook_analysis(self):
        """Load the completed AI book analysis, or partial chapter analyses."""
        if not self.project_folder:
            return None, False
        analysis_dir = self.project_folder / "analysis"
        aggregate = analysis_dir / "audiobook_brain.json"
        if aggregate.exists():
            try:
                return json.loads(aggregate.read_text(encoding="utf-8")), False
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

        chapter_payloads = []
        for path in sorted(analysis_dir.glob("chapter_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                chapter_payloads.append(payload)
        if not chapter_payloads:
            return None, False

        bible = {}
        for payload in chapter_payloads:
            for character in payload.get("characters", []) or []:
                if not isinstance(character, dict):
                    continue
                name = str(character.get("name") or "").strip()
                if name:
                    bible.setdefault(name, character)

        return {
            "version": 1,
            "book_bible": bible,
            "chapters": sorted(
                chapter_payloads,
                key=lambda item: int(item.get("chapter", 0) or 0),
            ),
        }, True

    def _suggest_pronunciations(self):
        """Import grounded AI pronunciation candidates from completed or partial analysis."""
        if not self.project_folder:
            self.pronunciation_status.setText('Open a saved book before importing AI pronunciation suggestions.')
            return

        data, partial = self._load_audiobook_analysis()
        if data is None:
            existing = {
                str(self.pronunciation_table.item(row, 0).text()).casefold()
                for row in range(self.pronunciation_table.rowCount())
                if self.pronunciation_table.item(row, 0)
            }
            added = 0
            for name in suggest_names_from_text("\n".join(ch.text or "" for ch in self.chapters)):
                clean = name.strip()
                if (
                    not clean
                    or clean.casefold() in existing
                    or clean.casefold() in COMMON_ENGLISH_WORDS
                    or all(part.casefold() in COMMON_ENGLISH_WORDS for part in clean.split())
                ):
                    continue
                spoken = suggest_pronunciation(clean)
                if not spoken or spoken.casefold() == clean.casefold():
                    continue
                self._add_pronunciation_row(clean, spoken, True, source="fallback")
                existing.add(clean.casefold())
                added += 1
                if added >= 30:
                    break
            if added:
                self._save_pronunciations()
                self.pronunciation_status.setText(
                    f"Audiobook AI analysis is not available yet. Added {added} conservative name-only drafts. "
                    "Run Audiobook AI from Chapters for multilingual evidence and richer suggestions."
                )
            else:
                self.pronunciation_status.setText(
                    "Audiobook AI has not produced an analysis yet. Open Chapters → Analyze with Audiobook AI, "
                    "then return here to import grounded pronunciation suggestions."
                )
            return

        book_text = "\n".join(ch.text or "" for ch in self.chapters)
        character_names = set()
        bible = data.get("book_bible", {}) or {}
        for name, value in bible.items():
            if str(name).strip():
                character_names.add(str(name).strip().casefold())
            for alias in (value or {}).get("aliases", []) if isinstance(value, dict) else []:
                if str(alias).strip():
                    character_names.add(str(alias).strip().casefold())

        existing = {
            str(self.pronunciation_table.item(row, 0).text()).casefold()
            for row in range(self.pronunciation_table.rowCount())
            if self.pronunciation_table.item(row, 0)
        }

        def grounded(written: str, spoken: str, confidence: float, language: str) -> bool:
            folded = written.casefold()
            if not written or not spoken or confidence < 0.80:
                return False
            if folded in existing:
                return False
            if folded not in book_text.casefold():
                return False
            if spoken.casefold() == folded:
                return False
            # Never import ordinary English vocabulary merely because the AI
            # assigned it a non-English language. Preserve English words only
            # when they are also a confirmed character name.
            if is_common_english_phrase(written) and folded not in character_names:
                return False

            # For English/unknown-language suggestions, require stronger evidence:
            # a confirmed character/alias name. This prevents common and ordinary
            # English vocabulary from filling the pronunciation dictionary.
            normalized_language = language.casefold().replace("_", "-")
            english_like = normalized_language in {
                "", "unknown", "english", "en", "en-us", "en-gb", "en-in"
            }
            if (
                english_like
                and folded not in character_names
                and script.casefold() in {"", "unknown", "latin", "roman", "english"}
            ):
                return False
            return True

        added = 0
        skipped = 0
        for chapter_data in data.get('chapters', []):
            for suggestion in chapter_data.get('pronunciation', []) or []:
                if not isinstance(suggestion, dict):
                    continue
                written = str(suggestion.get('written') or suggestion.get('text') or '').strip()
                spoken = str(suggestion.get('spoken') or suggestion.get('pronunciation') or '').strip()
                confidence = _numeric_score(suggestion.get('confidence', 0.0))
                language = str(suggestion.get('source_language') or 'unknown').strip()
                script = str(suggestion.get('script') or 'unknown').strip()
                ipa = str(suggestion.get('ipa') or '').strip()
                reason = str(suggestion.get('reason') or '').strip()
                if not grounded(written, spoken, confidence, language):
                    skipped += 1
                    continue

                # Keep the AI's grounded spoken form. The brain layer now
                # preserves a good model reading instead of replacing it with a
                # rough transliteration heuristic.
                self._add_pronunciation_row(written, spoken, True, source="ai")
                row = self.pronunciation_table.rowCount() - 1
                tip = (
                    f'AI confidence: {confidence:.0%}\n'
                    f'Source language: {language}\n'
                    f'Script: {script}'
                )
                if ipa:
                    tip += f'\nIPA: {ipa}'
                if reason:
                    tip += f'\nEvidence: {reason}'
                for col in (0, 1):
                    item = self.pronunciation_table.item(row, col)
                    if item:
                        item.setToolTip(tip)
                existing.add(written.casefold())
                added += 1

        self._save_pronunciations()
        if added:
            status = (
                f'Imported {added} grounded AI pronunciation suggestion(s). {skipped} candidates were filtered.'
            )
            if partial:
                status += ' Partial chapter analysis was used; run the full book analysis for final coverage.'
            self.pronunciation_status.setText(status)
        else:
            self.pronunciation_status.setText(
                f'No new grounded pronunciation suggestions found. {skipped} AI candidates were filtered.'
                + (' Partial analysis is available; continue AI analysis for remaining chapters.' if partial else '')
            )

    def _clean_obvious_english_pronunciations(self):
        removed = 0
        row = 0
        while row < self.pronunciation_table.rowCount():
            item = self.pronunciation_table.item(row, 0)
            spoken_item = self.pronunciation_table.item(row, 1)
            written = item.text().strip() if item else ''
            spoken = spoken_item.text().strip() if spoken_item else ''
            ordinary_english = is_common_english_phrase(written)
            if ordinary_english or not spoken or spoken.casefold() == written.casefold():
                self.pronunciation_table.removeRow(row)
                removed += 1
                continue
            row += 1
        self._save_pronunciations()
        self.pronunciation_status.setText(
            f'Removed {removed} obvious/non-useful pronunciation override(s).' if removed
            else 'No obvious/non-useful pronunciation overrides found.'
        )

    def _remove_pronunciation_row(self):
        row = self.pronunciation_table.currentRow()
        if row >= 0:
            self.pronunciation_table.removeRow(row)
            self._save_pronunciations()

    def _pronunciation_entries(self):
        from PySide6.QtCore import Qt
        entries = []
        for row in range(self.pronunciation_table.rowCount()):
            a = self.pronunciation_table.item(row, 0)
            b = self.pronunciation_table.item(row, 1)
            c = self.pronunciation_table.item(row, 2)
            written = a.text().strip() if a else ""
            spoken = b.text().strip() if b else ""
            if written and spoken:
                source = str(a.data(Qt.ItemDataRole.UserRole) or "manual")
                entries.append({
                    "written": written,
                    "spoken": spoken,
                    "enabled": c is not None and c.checkState() == Qt.CheckState.Checked,
                    "source": source,
                })
        return entries

    def _load_pronunciations(self):
        self.pronunciation_table.setRowCount(0)
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        entries = state.get("pronunciation_dictionary", [])
        version = int(state.get("pronunciation_dictionary_version", 0) or 0)

        # One-time migration: older builds could persist AI-generated garbage
        # without provenance. Start this release with a clean dictionary and
        # preserve all future manual/AI entries with explicit source metadata.
        if version < 2 and entries:
            entries = []
            state["pronunciation_dictionary"] = []
            state["pronunciation_dictionary_version"] = 2
            save_state(self.project_folder, state)
            self.pronunciation_status.setText(
                "Previous pronunciation suggestions were reset because older builds could save inaccurate AI entries. "
                "The original book text was not changed."
            )
            return

        book_text = "\n".join(ch.text or "" for ch in self.chapters)
        folded_book = book_text.casefold()
        name_candidates = {
            str(name).casefold() for name in suggest_names_from_text(book_text)
        }
        # Character names from completed/partial AI analysis are stronger
        # evidence than capitalization alone.
        analysis_data, _partial = self._load_audiobook_analysis()
        analysis_character_names = set(name_candidates)
        if isinstance(analysis_data, dict):
            bible = analysis_data.get("book_bible", {}) or {}
            if isinstance(bible, dict):
                analysis_character_names.update(str(name).casefold() for name in bible.keys() if str(name).strip())
                for value in bible.values():
                    if isinstance(value, dict):
                        analysis_character_names.update(
                            str(alias).casefold()
                            for alias in (value.get("aliases") or [])
                            if str(alias).strip()
                        )
        cleaned = []
        seen = set()
        removed_stale = 0
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                written = str(item.get("written", "")).strip()
                spoken = str(item.get("spoken", "")).strip()
                if not written or not spoken:
                    removed_stale += 1
                    continue
                key = written.casefold()
                if key in seen or key not in folded_book or spoken.casefold() == key:
                    removed_stale += 1
                    continue
                source = str(item.get("source") or "manual").strip().casefold()
                words = [w.strip('.,!?;:()[]{}') for w in written.split()]
                ordinary_english = bool(words) and all(
                    re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", w or '')
                    and w.casefold() in COMMON_ENGLISH_WORDS
                    for w in words
                )
                if source in {"ai", "fallback"} and ordinary_english and key not in analysis_character_names:
                    removed_stale += 1
                    continue
                cleaned_item = dict(item)
                cleaned_item["source"] = source
                cleaned.append(cleaned_item)
                seen.add(key)
                self._add_pronunciation_row(
                    written,
                    spoken,
                    item.get("enabled", True) is not False,
                    source=source,
                )

        if removed_stale or cleaned != entries or version < 2:
            state["pronunciation_dictionary"] = cleaned
            state["pronunciation_dictionary_version"] = 2
            save_state(self.project_folder, state)

        count = len(self._pronunciation_entries())
        if removed_stale:
            self.pronunciation_status.setText(
                f"{count} pronunciation override{'s' if count != 1 else ''} loaded. "
                f"{removed_stale} stale/invalid entry{' was' if removed_stale == 1 else 's were'} removed."
            )
        else:
            self.pronunciation_status.setText(
                f"{count} pronunciation override{'s' if count != 1 else ''} saved for this book."
                if count else "No pronunciation overrides saved for this book."
            )

    def _save_pronunciations(self):
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        entries = self._pronunciation_entries()
        state["pronunciation_dictionary"] = entries
        state["pronunciation_dictionary_version"] = 2
        save_state(self.project_folder, state)
        self.pronunciation_status.setText(f"{len(entries)} pronunciation override{'s' if len(entries) != 1 else ''} saved for this book." if entries else "No pronunciation overrides saved for this book.")
    def _test_selected_pronunciation(self) -> None:
        row = self.pronunciation_table.currentRow()
        if row < 0:
            self.pronunciation_preview_status.setText("Select a pronunciation row first.")
            return
        written_item = self.pronunciation_table.item(row, 0)
        spoken_item = self.pronunciation_table.item(row, 1)
        written = written_item.text().strip() if written_item else ""
        spoken = spoken_item.text().strip() if spoken_item else ""
        if not written or not spoken:
            self.pronunciation_preview_status.setText("The selected row needs both Written and Pronounce as text.")
            return

        profile = self._selected_profile()
        if not profile:
            self.pronunciation_preview_status.setText(
                "Select a Voice in Audio settings below the pronunciation dictionary first."
            )
            return
        if self.pronunciation_preview_worker and self.pronunciation_preview_worker.isRunning():
            return

        backend = self.backend.currentData() or profile.backend or "automatic"
        if backend == "automatic":
            backend = profile.backend or "automatic"
        output = Path(tempfile.gettempdir()) / "ryu_pronunciation_preview.wav"
        self.pronunciation_preview_test.setEnabled(False)
        self.pronunciation_preview_play.setEnabled(False)
        self.pronunciation_preview_stop.setEnabled(True)
        self.pronunciation_preview_status.setText(
            f"Generating '{spoken}' with {profile.name}…"
        )
        self.pronunciation_preview_worker = PronunciationPreviewWorker(
            profile, backend, spoken, output
        )
        self.pronunciation_preview_worker.finished_ok.connect(self._pronunciation_preview_ok)
        self.pronunciation_preview_worker.failed.connect(self._pronunciation_preview_failed)
        self.pronunciation_preview_worker.finished.connect(self._pronunciation_preview_finished)
        self.pronunciation_preview_worker.start()

    def _pronunciation_preview_ok(self, path: str) -> None:
        self.pronunciation_preview_path = Path(path)
        self.pronunciation_player.stop()
        self.pronunciation_player.setSource(QUrl.fromLocalFile(path))
        self.pronunciation_preview_play.setEnabled(True)
        self.pronunciation_preview_stop.setEnabled(True)
        self.pronunciation_preview_play.setText("▶ Play")
        self.pronunciation_preview_status.setText("Pronunciation preview ready.")

    def _pronunciation_preview_failed(self, message: str) -> None:
        self.pronunciation_preview_path = None
        self.pronunciation_preview_play.setEnabled(False)
        self.pronunciation_preview_stop.setEnabled(False)
        self.pronunciation_preview_status.setText(f"Pronunciation preview failed: {message}")

    def _pronunciation_preview_finished(self) -> None:
        self.pronunciation_preview_test.setEnabled(True)
        self.pronunciation_preview_worker = None

    def _play_pronunciation_preview(self) -> None:
        path = self.pronunciation_preview_path
        if not path or not path.exists():
            self.pronunciation_preview_status.setText("Generate a pronunciation preview first.")
            return
        if self.pronunciation_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pronunciation_player.pause()
        else:
            self.pronunciation_player.play()

    def _stop_pronunciation_preview(self) -> None:
        self.pronunciation_player.stop()
        self.pronunciation_preview_stop.setEnabled(False)
        worker = self.pronunciation_preview_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
        self.pronunciation_preview_status.setText("Pronunciation preview stopped.")

    def _pronunciation_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.pronunciation_preview_play.setText("Ⅱ Pause")
            self.pronunciation_preview_stop.setEnabled(True)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.pronunciation_preview_play.setText("▶ Resume")
            self.pronunciation_preview_stop.setEnabled(True)
        else:
            self.pronunciation_preview_play.setText("▶ Play")
            self.pronunciation_preview_stop.setEnabled(bool(self.pronunciation_preview_path))

    def _load_voice_cast_summary(self):
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        cast = state.get("voice_cast", {})
        if not cast:
            self.cast_summary.setText("No character-specific voice assignments saved. Narrator voice will be used.")
            return
        lines = [f"{name} → {voice}" for name, voice in cast.items()]
        self.cast_summary.setText(
            "Saved voice cast assignments:\n" + "\n".join(lines) +
            "\n\nThese assignments are stored with this book and are ready for the cast-aware narration engine."
        )

    def _load_profiles(self, keep_name: str | None = None) -> None:
        self.voice_profile.clear()
        for profile in self.profiles:
            self.voice_profile.addItem(profile.name, profile)
        if not self.profiles:
            self.voice_profile.addItem("No saved voice profiles", None)
            return
        if keep_name:
            index = self.voice_profile.findText(keep_name)
            if index >= 0:
                self.voice_profile.setCurrentIndex(index)

    def _refresh_voice_profiles(self) -> None:
        current = self.voice_profile.currentText()
        self.profiles = load_profiles()
        self._load_profiles(current)
        self.status.setText("Voice profiles refreshed.")

    def _metadata_history(self, key: str, defaults: list[str] | None = None) -> list[str]:
        values = list(defaults or [])
        try:
            projects = list_projects()
        except Exception:
            projects = []
        for project in projects:
            state = load_state(project.folder)
            value = str(state.get(key) or "").strip()
            if value:
                values.append(value)
        # Include this book's current value when reopening a previously saved
        # project, without forcing the field to select it.
        if self.project_folder:
            state = load_state(self.project_folder)
            value = str(state.get(key) or "").strip()
            if value:
                values.append(value)
        result, seen = [], set()
        for value in values:
            folded = value.casefold()
            if folded not in seen:
                result.append(value)
                seen.add(folded)
        return result[:40]

    def _update_overview(self) -> None:
        words = sum(len(ch.text.split()) for ch in self.chapters)
        speed = float(self.narration_speed.currentData() or 0.90) if hasattr(self, "narration_speed") else 0.90
        effective_wpm = max(60.0, 150.0 * speed)
        minutes = max(1, round(words / effective_wpm))
        self.chapter_count.setText(f"Chapters: {len(self.chapters)}")
        self.word_count.setText(f"Words: {words:,}")
        self.duration_estimate.setText(
            f"Estimated length: {minutes // 60}h {minutes % 60:02d}m at {speed:.2f}× narration speed"
        )

    def _default_output(self) -> Path | None:
        if not self.project_folder:
            return None
        folder = self.project_folder / "Audiobook"
        folder.mkdir(parents=True, exist_ok=True)
        title = self.title.text().strip() or self.project_folder.name
        safe = "".join(c if c not in '<>:"/\\|?*' else "_" for c in title).strip() or "Audiobook"
        return folder / f"{safe}.m4b"

    def _set_default_output(self) -> None:
        default = self._default_output()
        state = load_state(self.project_folder) if self.project_folder else {}
        saved = Path(state["output_path"]) if state.get("output_path") else None
        # Old versions used Downloads. New projects always default to the
        # project's Audiobook folder unless the saved path is already there.
        if saved and self.project_folder and saved.parent == self.project_folder / "Audiobook":
            self.output.setText(str(saved))
        elif default:
            self.output.setText(str(default))

    def _restore_state(self) -> None:
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        profile_name = state.get("voice_profile")
        if profile_name:
            index = self.voice_profile.findText(profile_name)
            if index >= 0:
                self.voice_profile.setCurrentIndex(index)
        speed = state.get("narration_speed")
        if speed is not None:
            index = self.narration_speed.findData(float(speed))
            if index >= 0:
                self.narration_speed.setCurrentIndex(index)
        pacing = state.get("pacing_profile")
        if pacing:
            index = self.pacing_profile.findData(pacing)
            if index >= 0:
                self.pacing_profile.setCurrentIndex(index)

        self.author.setText(str(state.get("author") or ""))
        self.narrator.setText(str(state.get("narrator") or ""))
        self.publisher.setText(str(state.get("publisher") or ""))
        self.series.setText(str(state.get("series") or ""))
        self.language.setText(str(state.get("language") or "en"))
        self.year.setText(str(state.get("year") or ""))
        self.genre.set_value(str(state.get("genre") or "Audiobook"))

        cover = state.get("cover_path")
        if cover and Path(cover).exists():
            self.cover = Path(cover)
            self.cover_label.setText(self.cover.name)

    def _selected_profile(self) -> VoiceProfile | None:
        value = self.voice_profile.currentData()
        return value if isinstance(value, VoiceProfile) else None

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save M4B", str(self._default_output() or ""),
            "M4B Audiobook (*.m4b)",
        )
        if path:
            self.output.setText(str(Path(path).with_suffix(".m4b")))
            self._refresh_readiness()

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Cover", "", "Images (*.jpg *.jpeg *.png)")
        if path:
            self.cover = Path(path)
            self.cover_label.setText(self.cover.name)
            self._refresh_readiness()

    def _cast_provider(self, narrator_provider, narrator_voice):
        if not self.project_folder:
            return narrator_provider, narrator_voice
        state = load_state(self.project_folder)
        assignments = state.get("voice_cast", {})
        if not assignments:
            return narrator_provider, narrator_voice
        from app.tts.cast_provider import CastAwareProvider
        profiles = {profile.name: profile for profile in self.profiles}
        narrating_character = state.get("voice_cast_narrating_character")
        return CastAwareProvider(
            narrator_provider,
            narrator_voice,
            profiles,
            assignments,
            narrating_character=narrating_character,
            backend_override=self.backend.currentData() or "automatic",
        ), narrator_voice

    def _provider(self):
        profile = self._selected_profile()
        if not profile:
            return None, None
        backend = self.backend.currentData() or profile.backend
        if backend == "automatic":
            backend = profile.backend
        if profile.provider == "piper":
            return PiperProvider(backend=backend), profile.voice_id
        if profile.provider == "windows-sapi":
            return SystemSAPIProvider(), profile.voice_id
        provider, voice = provider_from_profile(profile)
        if hasattr(provider, "backend"):
            provider.backend = backend
        return provider, voice

    def preview(self) -> None:
        profile = self._selected_profile()
        if not profile:
            self.status.setText('Create or select a Voice Profile first.')
            return

        index = self.preview_chapter.currentIndex()
        if index < 0 or index >= len(self.chapters):
            self.status.setText('Select a chapter for the preview.')
            return
        if self.preview_worker and self.preview_worker.isRunning():
            return

        chapter = self.chapters[index]
        self._save_pronunciations()
        pronunciation_dictionary = self._pronunciation_entries()
        text = chapter.text
        output = Path(tempfile.gettempdir()) / 'ryu_audiobook_voice_preview.wav'
        backend = self.backend.currentData() or profile.backend
        if backend == 'automatic':
            backend = profile.backend

        self.preview_worker = VoicePreviewWorker(
            profile, backend, self.project_folder, self.profiles, pronunciation_dictionary,
            text, output, float(self.narration_speed.currentData() or 0.90),
            self.pacing_profile.currentData() or 'natural',
            dialogue_assignments=getattr(chapter, "dialogue_assignments", []),
        )
        self.preview_worker.progress.connect(self._preview_worker_progress)
        self.preview_worker.percent.connect(self.preview_loading.setValue)
        self.preview_worker.finished_ok.connect(self._preview_worker_ok)
        self.preview_worker.failed.connect(self._preview_worker_failed)
        self.preview_worker.finished.connect(self._preview_worker_finished)

        self.preview_button.setEnabled(False)
        self.preview_play_button.setEnabled(False)
        self.preview_stop_button.setEnabled(True)
        self.preview_loading.setValue(5)
        self.preview_loading.setVisible(True)
        self.preview_status.setText('[5%] Preparing voice preview…')
        self.status.setText('Voice preview is running in the background; the app remains responsive.')
        self.preview_percent = getattr(self, 'preview_percent', None)
        self.preview_worker.start()

    def _preview_worker_progress(self, message: str) -> None:
        self.preview_status.setText(message)

    def _preview_worker_ok(self, result) -> None:
        self.preview_path = result.output_path
        self.preview_player.stop()
        self.preview_player.setSource(QUrl.fromLocalFile(str(result.output_path)))
        self.preview_play_button.setEnabled(True)
        self.preview_stop_button.setEnabled(True)
        self.preview_play_button.setText('▶  Play Preview')
        voice_summary = ', '.join(result.voices_used) if result.voices_used else 'Narrator'
        self.preview_loading.setValue(100)
        self.preview_status.setText(
            f'100% • Preview ready • {result.segments} narration segment(s) • Voices: {voice_summary}'
        )
        self.status.setText(
            'Preview generated from the current pronunciation, voice cast, speed and pacing settings.'
        )

    def _preview_worker_failed(self, message: str) -> None:
        self.preview_path = None
        self.preview_play_button.setEnabled(False)
        self.preview_stop_button.setEnabled(False)
        self.preview_loading.setValue(0)
        self.preview_status.setText('0% • Preview generation failed.')
        self.status.setText(f'Preview failed: {message}')

    def _preview_worker_finished(self) -> None:
        self.preview_loading.setVisible(False)
        self.preview_button.setEnabled(True)
        self.preview_worker = None

    def play_preview(self) -> None:
        if not self.preview_path or not self.preview_path.exists():
            self.preview_status.setText("Generate a voice preview first.")
            return
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.pause()
        else:
            self.preview_player.play()

    def stop_preview(self) -> None:
        self.preview_player.stop()
        worker = self.preview_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            self.preview_loading.setVisible(False)
            self.preview_status.setText('Stopping preview…')

    def _preview_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_play_button.setText("Ⅱ  Pause Preview")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.preview_play_button.setText("▶  Resume Preview")
        else:
            self.preview_play_button.setText("▶  Play Preview")

    def _preview_position(self, position: int) -> None:
        self.preview_time.setText(
            f"{self._fmt(position)} / {self._fmt(self.preview_player.duration())}"
        )

    def _preview_duration(self, duration: int) -> None:
        self.preview_time.setText(
            f"{self._fmt(self.preview_player.position())} / {self._fmt(duration)}"
        )

    def _set_generation_locked(self, locked: bool) -> None:
        controls = [
            self.title, self.author, self.voice_profile, self.refresh_voice_profiles,
            self.backend, self.cover_button, self.change_output, self.preview_button,
            self.start_button, self.resume_button,
        ]
        for control in controls:
            control.setEnabled(not locked)

    def _repair_empty_chapters_from_source(self) -> bool:
        if not self.project_folder:
            return False
        try:
            project_file = self.project_folder / "project.json"
            metadata = json.loads(project_file.read_text(encoding="utf-8"))
            source_name = metadata.get("source_file")
            if not source_name:
                return False
            source = self.project_folder / "source" / source_name
            if not source.exists():
                return False
            detected = detect_chapters(extract_text(source).text)
            if not detected or any(not c.text.strip() for c in detected):
                return False
            chapters_file = self.project_folder / "chapters.json"
            chapters_file.write_text(
                json.dumps(
                    [
                        {"number": c.number, "title": c.title, "text": c.text}
                        for c in detected
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.chapters = detected
            self._update_overview()
            self.status.setText("Chapter list was automatically repaired from the original source.")
            return True
        except Exception:
            return False

    def _refresh_resume_state(self) -> None:
        if not self.project_folder:
            self.resume_button.setVisible(False)
            self.actions_note.setText("")
            return

        info = inspect_generation_state(self.audio_root, self.chapters)
        state = load_state(self.project_folder)
        status = str(state.get("status") or "new").lower()
        output_value = state.get("output_path")
        output_exists = bool(output_value and Path(str(output_value)).exists())
        resumable = (
            info.resume_available
            or bool(state.get("failed_chapters"))
            or status in {"failed", "cancelled", "generating"}
        )

        # A fully completed book should not advertise a resume action unless
        # the user has explicitly started a new generation.
        if status == "completed" and not info.resume_available:
            resumable = False

        self.resume_button.setVisible(resumable)
        if resumable:
            completed = len(info.completed_chapters)
            partial = len(info.partial_chapters)
            details = []
            if completed:
                details.append(f"{completed}/{len(self.chapters)} chapter(s) already complete")
            if partial:
                details.append(f"{partial} chapter(s) have partial work")
            if state.get("failed_chapters"):
                details.append(
                    "failed: " + ", ".join(map(str, state.get("failed_chapters") or []))
                )
            if output_exists and status != "completed":
                details.append("an earlier M4B remains on disk")
            suffix = " • ".join(details) if details else "saved working audio is available"
            self.resume_button.setText("Resume / Retry")
            self.actions_note.setText(
                f"Resume available • {suffix}. Existing compatible chunks will be reused."
            )
        else:
            self.actions_note.setText(
                "A new generation will create fresh audio and retain the project for later resume if interrupted."
            )

    def _refresh_readiness(self) -> None:
        profile = self._selected_profile()
        provider_name = profile.provider if profile else None
        state = load_state(self.project_folder) if self.project_folder else {}
        assignments = state.get("voice_cast", {}) if isinstance(state, dict) else {}
        readiness = build_generation_readiness(
            self.chapters,
            profile.name if profile else None,
            provider_name,
            self.output.text().strip() if hasattr(self, "output") else "",
            custom_runtime_ready=runtime_ready(),
            assignments=assignments,
            cover_selected=bool(self.cover),
        )

        self._refresh_resume_state()

        if readiness.ready:
            self.readiness_status.setText("✓ Ready to generate")
            self.readiness_status.setObjectName("ready")
            self.start_button.setEnabled(True)
            self.resume_button.setEnabled(True)
        else:
            failures = readiness.blocking_failures
            self.readiness_status.setText(
                f"⚠ {len(failures)} item(s) need attention before generation."
            )
            self.readiness_status.setObjectName("warning")
            self.start_button.setEnabled(False)
            self.resume_button.setEnabled(False)

        lines = []
        for item in readiness.items:
            icon = "✓" if item.ok else ("⚠" if not item.blocking else "✕")
            lines.append(f"{icon} <b>{item.label}</b>: {item.detail}")
        self.readiness_details.setText("<br>".join(lines))
        self.readiness_status.style().unpolish(self.readiness_status)
        self.readiness_status.style().polish(self.readiness_status)

    def start(self) -> None:
        if not self.chapters:
            self.status.setText("No chapters available.")
            return

        self._refresh_readiness()
        if not self.start_button.isEnabled():
            self.status.setText("Generation is blocked by the readiness checks above.")
            return

        empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            self._repair_empty_chapters_from_source()
            empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            # Empty records are never synthesizable. If the source cannot be
            # re-read, safely remove only the empty records instead of blocking
            # an otherwise valid audiobook because of stale project state.
            self.chapters = [c for c in self.chapters if c.text and c.text.strip()]
            for number, chapter in enumerate(self.chapters, start=1):
                chapter.number = number
            if self.project_folder:
                try:
                    chapters_file = self.project_folder / "chapters.json"
                    chapters_file.write_text(
                        json.dumps(
                            [{"number": c.number, "title": c.title, "text": c.text} for c in self.chapters],
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            self._update_overview()
            empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            numbers = ", ".join(str(c.number) for c in empty)
            self.status.setText(
                f"Generation stopped: chapter(s) {numbers} contain no body text. "
                "Please review the Chapters page."
            )
            return

        output = Path(self.output.text().strip()) if self.output.text().strip() else self._default_output()
        if not output:
            self.status.setText("Choose an M4B output.")
            return
        self._save_pronunciations()
        resume_info = inspect_generation_state(self.audio_root, self.chapters)
        state_before_start = load_state(self.project_folder) if self.project_folder else {}
        is_resume = (
            resume_info.resume_available
            or bool(state_before_start.get("failed_chapters"))
            or str(state_before_start.get("status") or "").lower() in {"failed", "cancelled", "generating"}
        )
        profile = self._selected_profile()
        if profile and profile.provider == "chatterbox" and not runtime_ready():
            self.status.setText(
                "Custom voice engine is not installed. Open Models → Install / Repair Custom Voice Engine, "
                "then return to Generate."
            )
            return

        provider, voice = self._provider()
        if not provider:
            self.status.setText("Select a Voice Profile.")
            return
        provider, voice = self._cast_provider(provider, voice)

        output.parent.mkdir(parents=True, exist_ok=True)
        if self.project_folder:
            state = load_state(self.project_folder)
            profile = self._selected_profile()
            state.update({
                "voice_profile": profile.name if profile else None,
                "output_path": str(output),
                "cover_path": str(self.cover) if self.cover else None,
                "narrator": self.narrator.text().strip(),
                "publisher": self.publisher.text().strip(),
                "series": self.series.text().strip(),
                "language": self.language.text().strip(),
                "year": self.year.text().strip(),
                "genre": self.genre.value(),
                "narration_speed": float(self.narration_speed.currentData() or 0.90),
                "pacing_profile": self.pacing_profile.currentData() or "natural",
                "audio_bitrate": int(self.audio_bitrate.currentData() or DEFAULT_AUDIO_BITRATE_KBPS),
                "status": "generating",
            })
            save_state(self.project_folder, state)

        self.progress.setRange(0, len(self.chapters))
        self.progress.setValue(0)
        self.last_progress_value = 0
        self.initial_progress_value = 0
        self._eta_ema_sec_per_unit = None
        self._eta_warmup_samples = 0
        self._eta_rates = []
        self._eta_last_work = 0
        self._eta_last_time = time.monotonic()
        self.generation_phase = "synthesis"
        self.started_at = time.monotonic()
        self.timer.start(1000)
        self._set_generation_locked(True)
        self.cancel_button.setEnabled(True)
        self.play_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.result_label.setText("Generating chapters and packaging the final M4B…")
        self.status.setText(
            "Resuming generation and reusing compatible completed chunks…"
            if is_resume else "Starting generation…"
        )

        metadata = {
            "title": self.title.text().strip(),
            "author": self.author.text().strip(),
            "narrator": self.narrator.text().strip(),
            "publisher": self.publisher.text().strip(),
            "series": self.series.text().strip(),
            "language": self.language.text().strip(),
            "year": self.year.text().strip(),
            "genre": self.genre.value(),
        }
        self.manager = GenerationManager(
            provider, voice, self.chapters, self.audio_root,
            on_progress=lambda *args: self.signals.progress.emit(*args),
            on_finished=lambda summary: self.signals.finished.emit(summary),
            pronunciation_dictionary=self._pronunciation_entries(),
            narration_speed=float(self.narration_speed.currentData() or 0.90),
            pacing_profile=self.pacing_profile.currentData() or "natural",
            metadata=metadata,
            bitrate=int(self.audio_bitrate.currentData() or DEFAULT_AUDIO_BITRATE_KBPS),
        )
        self.manager.start(
            output,
            self.title.text().strip(),
            self.author.text().strip(),
            self.cover,
            metadata=metadata,
        )

    def cancel(self) -> None:
        if self.manager:
            self.manager.cancel()
            self.status.setText("Stopping generation and releasing the voice engine…")

    def update_progress(self, chapter: int, total: int, done: int, message: str) -> None:
        if message.startswith("provider:"):
            self.status.setText(message.split(":", 1)[1].strip())
            self.stage.setText(
                f"{message.split(':', 1)[1].strip()} • chapter {chapter}/{total}"
            )
            return
        if message.startswith("plan:"):
            try:
                parts = message.split(":")
                work_total = max(1, int(parts[1]))
                completed_work = max(0, min(work_total, int(parts[2]))) if len(parts) >= 3 else 0
                chunk_total = max(1, int(parts[3])) if len(parts) >= 4 else work_total
            except (ValueError, IndexError):
                work_total = max(1, total)
                completed_work = 0
                chunk_total = work_total
            self.progress.setRange(0, work_total)
            self.progress.setValue(completed_work)
            self.last_progress_value = completed_work
            self.initial_progress_value = completed_work
            self._eta_ema_sec_per_unit = None
            self._eta_warmup_samples = 0
            self._eta_rates = []
            self._eta_last_work = completed_work
            self._eta_last_time = time.monotonic()
            self.generation_phase = "synthesis"
            if completed_work:
                self.stage.setText(
                    f"Preparing {chunk_total:,} audio segments… "
                    f"{completed_work:,}/{work_total:,} text-units already reusable"
                )
            else:
                self.stage.setText(
                    f"Preparing {chunk_total:,} audio segments… "
                    f"ETA will calibrate after the first few segments"
                )
            return

        if message.startswith("m4b-package:"):
            self.generation_phase = "packaging"
            parts = message.split(":")
            if len(parts) >= 3:
                try:
                    current_pkg, total_pkg = parts[1].split("/", 1)
                    current_pkg = int(current_pkg)
                    total_pkg = max(1, int(total_pkg))
                    self.stage.setText(
                        f"Packaging M4B • chapter {current_pkg}/{total_pkg}"
                    )
                except (ValueError, IndexError):
                    self.stage.setText("Packaging final M4B…")
            else:
                self.stage.setText("Packaging final M4B…")
            self.remaining.setText("Remaining: packaging…")
            self.speed.setText("Speed: —")
        if message.startswith("m4b-complete"):
            self.generation_phase = "complete"
            self.progress.setValue(self.progress.maximum())
            self.last_progress_value = self.progress.maximum()
            self.remaining.setText("Remaining: 0:00")
            self.speed.setText("Speed: complete")
            self.stage.setText("M4B packaging complete")
        elif message.startswith("m4b-packaging"):
            self.generation_phase = "packaging"
            self.progress.setValue(self.progress.maximum())
            self.last_progress_value = self.progress.maximum()
            self.remaining.setText("Remaining: packaging…")
            self.speed.setText("Speed: —")
            self.stage.setText("Packaging final M4B • this may take a few minutes for a large audiobook")
        elif message.startswith("m4b-failed"):
            self.stage.setText("M4B packaging failed")
            self.status.setText(message)
        elif message.startswith("chunk-start:"):
            self.generation_phase = "synthesis"
            self.stage.setText(
                f"Synthesizing audio • {message.split(':', 1)[1]} • chapter {chapter}/{total}"
            )
            self.status.setText(
                "Voice engine is generating the current chunk. "
                "ETA will appear after the first chunk completes."
            )
        elif message.startswith("chunk:"):
            try:
                payload = message.split(":", 1)[1]
                chunk_part, work_part = payload.split(":", 1)
                current, planned = chunk_part.split("/", 1)
                work_done, work_total = work_part.split("/", 1)
                current_n, planned_n = int(current), int(planned)
                work_done_n, work_total_n = int(work_done), max(1, int(work_total))
                self.progress.setRange(0, work_total_n)
                self.progress.setValue(max(0, min(work_total_n, work_done_n)))
                self.last_progress_value = work_done_n
                self.stage.setText(
                    f"Generating audio • segment {current_n:,}/{planned_n:,} • "
                    f"chapter {chapter}/{total}"
                )
                now = time.monotonic()
                if self._eta_last_work is not None and self._eta_last_time is not None:
                    delta_work = work_done_n - self._eta_last_work
                    delta_time = now - self._eta_last_time
                    if delta_work > 0 and delta_time >= 0.2:
                        sample = delta_time / delta_work
                        # The first completed segments include model startup and
                        # cache warm-up. Do not let those samples dominate the
                        # full-book ETA.
                        if self._eta_warmup_samples < 2:
                            self._eta_warmup_samples += 1
                        else:
                            self._eta_rates.append(sample)
                            self._eta_rates = self._eta_rates[-8:]
                            ordered = sorted(self._eta_rates)
                            median = ordered[len(ordered) // 2]
                            self._eta_ema_sec_per_unit = (
                                median
                                if self._eta_ema_sec_per_unit is None
                                else (0.25 * median + 0.75 * self._eta_ema_sec_per_unit)
                            )
                self._eta_last_work = work_done_n
                self._eta_last_time = now
            except (ValueError, IndexError):
                self.stage.setText(f"Chapter {chapter}/{total}")
        else:
            if message == "chapter-complete":
                self.generation_phase = "synthesis"
                value = max(0, min(self.progress.maximum(), done))
                self.progress.setValue(value)
                self.last_progress_value = value
                self.stage.setText(
                    f"Chapter {chapter}/{total} complete • "
                    f"{value:,}/{self.progress.maximum():,} chunks"
                )
            elif message.startswith("chapter-failed"):
                self.stage.setText(f"Chapter {chapter}/{total} failed")
            else:
                value = max(0, min(self.progress.maximum(), chapter - 1))
                self.progress.setValue(value)
                self.last_progress_value = value
                self.stage.setText(f"Chapter {chapter}/{total}")

    def _update_live_stats(self) -> None:
        if self.started_at is None:
            return
        elapsed = int(time.monotonic() - self.started_at)
        self.elapsed.setText(f"Elapsed: {elapsed // 60}:{elapsed % 60:02d}")

        if self.generation_phase == "packaging":
            self.remaining.setText("Remaining: packaging…")
            self.speed.setText("Speed: —")
            return

        if self.generation_phase == "complete":
            self.remaining.setText("Remaining: 0:00")
            self.speed.setText("Speed: complete")
            return

        current = self.progress.value()
        total = max(1, self.progress.maximum())
        work_done = max(0, current - self.initial_progress_value)
        work_remaining = max(0, total - current)

        if self._eta_ema_sec_per_unit is not None and work_remaining > 0:
            remaining = max(0, int(work_remaining * self._eta_ema_sec_per_unit))
            self.remaining.setText(
                f"Remaining: {remaining // 60}:{remaining % 60:02d}"
            )
            units_per_min = 60.0 / max(self._eta_ema_sec_per_unit, 1e-9)
            self.speed.setText(f"Speed: {units_per_min:,.0f} text-units/min")
        elif work_done > 0 and elapsed > 8:
            fallback_rate = work_done / elapsed
            remaining = max(0, int(work_remaining / max(fallback_rate, 1e-9)))
            self.remaining.setText(
                f"Remaining: {remaining // 60}:{remaining % 60:02d}"
            )
            self.speed.setText(f"Speed: {fallback_rate * 60:,.0f} text-units/min")
        else:
            self.remaining.setText("Remaining: calibrating…")
            self.speed.setText("Speed: calibrating…")

    def finished(self, summary: GenerationSummary) -> None:
        self.timer.stop()
        self.generation_phase = "idle"
        self._set_generation_locked(False)
        self.cancel_button.setEnabled(False)
        if self.project_folder:
            state = load_state(self.project_folder)
            state["status"] = "completed" if summary.output_path else ("failed" if (summary.chapters_failed or summary.packaging_failed) else "cancelled")
            state["completed_chapters"] = list(summary.chapters_completed_numbers or [])
            state["failed_chapters"] = summary.chapters_failed
            save_state(self.project_folder, state)

        if summary.output_path:
            self.progress.setValue(self.progress.maximum())
            self.stage.setText("Audiobook ready")
            self.result_label.setText(f"✓ Finished M4B\n{summary.output_path}")
            self.play_button.setEnabled(True)
            self.open_button.setEnabled(True)
            self.status.setText("Audiobook created successfully. Intermediate generation audio has been cleaned.")
        elif summary.packaging_failed:
            self.stage.setText("M4B packaging failed")
            error = f"\n\nPackaging error: {summary.packaging_error}" if summary.packaging_error else ""
            self.result_label.setText(
                "The chapters were generated, but the final M4B could not be packaged. "
                "Temporary files were kept so you can retry." + error
            )
            self.status.setText("M4B creation failed. The generated audio has been kept for retry.")
        elif summary.chapters_failed:
            self.stage.setText("Generation failed")
            details = []
            for number in summary.chapters_failed:
                reason = (summary.failure_details or {}).get(number, "Unknown generation error")
                details.append(f"Chapter {number}: {reason}")
            self.result_label.setText(
                "Generation failed. Temporary files were kept so you can retry.\n\n"
                + "\n".join(details)
            )
            self.status.setText("The final M4B was not created. See the chapter-specific errors above.")
        else:
            self.stage.setText("Generation cancelled")
            self.result_label.setText("Generation cancelled. Temporary files were kept for resume.")
            self.status.setText("No final M4B was created.")
        self._refresh_resume_state()
        self._refresh_readiness()

    def play_result(self) -> None:
        path = Path(self.output.text().strip())
        if not path.exists():
            self.status.setText("Final M4B was not found.")
            return
        if self.player.source().toLocalFile() != str(path):
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("▶  Play Audiobook")
        else:
            self.player.play()
            self.play_button.setText("Ⅱ  Pause")

    def open_result_folder(self) -> None:
        path = Path(self.output.text().strip())
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _player_position(self, position: int) -> None:
        self.result_time.setText(f"{self._fmt(position)} / {self._fmt(self.player.duration())}")

    def _player_duration(self, duration: int) -> None:
        self.result_time.setText(f"{self._fmt(self.player.position())} / {self._fmt(duration)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        seconds = max(0, ms // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"
