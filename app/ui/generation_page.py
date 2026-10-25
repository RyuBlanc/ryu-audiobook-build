from __future__ import annotations

from pathlib import Path
import hashlib
import logging
import json
import re
import time
import tempfile
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, QUrl, QTimer, QThread, QSettings
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QCheckBox,
    QDoubleSpinBox, QSpinBox,
)

from app.chapters.detector import Chapter, detect_chapters
from app.core.paths import audiobooks_root
from app.chapters.characters import analyze_book
from app.ai.brain import _numeric_score
from app.tts.pronunciation_suggester import (
    suggest_pronunciation, suggest_names_from_text, COMMON_ENGLISH_WORDS,
    is_common_english_phrase, is_likely_character_name_candidate, nativeish_pronunciation,
)
from app.documents.parser import extract_text
from app.documents.cover_art import persist_project_cover
from app.core.state import load_state, save_state
from app.core.character_identity import parse_character_identity_key
from app.core.project import list_projects
from app.ui.metadata_widgets import HistoryComboBox, GenrePicker
from app.ui.motion import SmoothProgressBar
from app.ui.stable_refresh import sync_combo_items_in_place
from app.ui.audio_visualizer import AudioVisualizer
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import load_profiles, load_saved_profile, load_saved_profiles, VoiceProfile
from app.tts.providers.piper import PiperProvider
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.preview import build_voice_preview
from app.tts.readiness import build_generation_readiness, partition_chapters_by_body
from app.tts.chatterbox_runtime import runtime_ready
from app.tts.qwen_character_runtime import runtime_ready as qwen_runtime_ready
from app.audio.assembler import DEFAULT_AUDIO_BITRATE_KBPS, _duration_ms
from app.tts.resume import inspect_generation_state
from app.audio.library import (
    AUDIO_SOURCE_LINKS, CUE_KIND_LABELS, MUSIC_CATEGORIES, ensure_audio_library,
    import_audio_files, list_cue_tracks, list_music_tracks, resolve_cue_track, resolve_music_track,
)


log = logging.getLogger(__name__)


class VoicePreviewWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(str)
    percent = Signal(int)

    def __init__(self, profile, backend, project_folder, profiles, pronunciation_dictionary,
                 text, output, narration_speed, pacing_profile, dialogue_assignments=None,
                 target_seconds: float | None = 30.0, mix_settings: dict | None = None):
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
        self.target_seconds = max(0.0, float(target_seconds or 0.0))
        self.mix_settings = dict(mix_settings or {})
        self._provider = None
        self._progress_floor = 0
        self._preview_started = 0.0

    def _emit_percent(self, value: int) -> int:
        self._progress_floor = max(self._progress_floor, min(100, max(0, int(value))))
        self.percent.emit(self._progress_floor)
        return self._progress_floor

    def _provider_status(self, message: str) -> None:
        value = str(message or "")
        low = value.casefold()
        if "building the saved character identity" in low or "preparing the saved character identity" in low:
            self._emit_percent(30)
        elif "loading cached canonical character identity" in low:
            self._emit_percent(28)
        elif "expression references ready" in low or "loading base clone engine" in low:
            self._emit_percent(42)
        elif "loading qwen model" in low:
            self._emit_percent(18 if self._progress_floor < 30 else 45)
        elif "qwen model loaded" in low:
            self._emit_percent(25 if self._progress_floor < 30 else 50)
        elif (
            "generating natural voicedesign" in low
            or "generating qwen customvoice speech" in low
            or "generating qwen base clone speech" in low
        ):
            self._emit_percent(52)
        # Keep long inference visibly alive without claiming token-level
        # percentage that Qwen's local Base interface does not provide.
        if ("processing" in low or "generating" in low) and "elapsed" not in low and self._preview_started > 0:
            elapsed = max(0, int(time.monotonic() - self._preview_started))
            value += f" • elapsed {elapsed // 60}:{elapsed % 60:02d}"
        self.progress.emit(value)

    def run(self) -> None:
        self._preview_started = time.monotonic()
        self._progress_floor = 0
        try:
            self._emit_percent(5)
            self.progress.emit('[5%] Loading voice engine…')
            provider, voice = provider_from_profile(self.profile)
            self._provider = provider
            if hasattr(provider, 'backend'):
                provider.backend = self.backend
            set_status = getattr(provider, "set_status_callback", None)
            if callable(set_status):
                set_status(self._provider_status)

            if self.project_folder:
                state = load_state(self.project_folder)
                assignments = state.get('voice_cast', {}) if isinstance(state, dict) else {}
                identity_assignments = state.get("voice_cast_identity_assignments", {}) if isinstance(state, dict) else {}
                if assignments or identity_assignments:
                    from app.tts.cast_provider import CastAwareProvider
                    self._provider = CastAwareProvider(
                        provider, voice,
                        {profile.name: profile for profile in self.profiles},
                        assignments,
                        narrating_character=state.get('voice_cast_narrating_character'),
                        backend_override=self.backend,
                        identity_assignments=identity_assignments,
                    )
                    wrapper_status = getattr(self._provider, "set_status_callback", None)
                    if callable(wrapper_status):
                        wrapper_status(self._provider_status)

            self._emit_percent(10)
            self.progress.emit('[10%] Voice engine ready • preparing preview segments…')

            preview_started = time.monotonic()
            def fmt_seconds(value: float) -> str:
                seconds = max(0, int(value))
                return f"{seconds // 60}:{seconds % 60:02d}"

            def preview_progress(stage: str, current: int, total: int) -> None:
                total = max(1, int(total))
                current = max(0, min(total, int(current)))
                elapsed = time.monotonic() - preview_started
                eta = None
                if stage == "synthesizing" and current > 0 and current < total:
                    eta = elapsed * (total - current) / current
                if stage == "preparing":
                    percent = 10
                    label = f"Preparing preview • elapsed {fmt_seconds(elapsed)}"
                elif stage == "synthesizing":
                    percent = 15 + int(70 * current / total)
                    timing = f" • elapsed {fmt_seconds(elapsed)}"
                    if eta is not None:
                        timing += f" • ETA {fmt_seconds(eta)}"
                    label = f"Generating segment {current}/{total}{timing}"
                elif stage == "finalizing":
                    percent = 85 + int(10 * current / total)
                    label = f"Finalizing preview • elapsed {fmt_seconds(elapsed)}"
                else:
                    percent = 10
                    label = "Preparing preview…"
                actual_percent = self._emit_percent(percent)
                self.progress.emit(f'[{actual_percent}%] {label}')

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
                target_seconds=self.target_seconds,
            )
            if self.mix_settings.get("enabled"):
                self._emit_percent(91)
                self.progress.emit("[91%] Mixing selected BGM, narration ducking and story effects…")
                from app.audio.preview_mixer import mix_voice_preview
                mixed_output = self.output.with_name(f"{self.output.stem}_full_mix.wav")
                mix_voice_preview(
                    result.output_path,
                    mixed_output,
                    result.source_text,
                    background_enabled=bool(self.mix_settings.get("background_enabled", False)),
                    background_mode=str(self.mix_settings.get("background_mode") or "auto"),
                    music_style=str(self.mix_settings.get("music_style") or "auto"),
                    music_variation_id=self.mix_settings.get("music_variation_id"),
                    background_audio_path=self.mix_settings.get("background_audio_path"),
                    ambience_audio_path=self.mix_settings.get("ambience_audio_path"),
                    music_volume=float(self.mix_settings.get("music_volume", 0.12)),
                    ambience_volume=float(self.mix_settings.get("ambience_volume", 0.06)),
                    story_effects_enabled=bool(self.mix_settings.get("story_effects_enabled", True)),
                    story_effect_volume=float(self.mix_settings.get("story_effect_volume", 0.12)),
                    chapter_transition_sound=bool(self.mix_settings.get("chapter_transition_sound", True)),
                    is_first_chapter=bool(self.mix_settings.get("is_first_chapter", True)),
                    is_last_chapter=bool(self.mix_settings.get("is_last_chapter", False)),
                    sound_cue_style=str(self.mix_settings.get("sound_cue_style") or "classic-book"),
                    opening_cue_path=self.mix_settings.get("opening_cue_path"),
                    page_turn_cue_path=self.mix_settings.get("page_turn_cue_path"),
                    ending_cue_path=self.mix_settings.get("ending_cue_path"),
                )
                from dataclasses import replace
                result = replace(result, output_path=mixed_output)
                self._emit_percent(98)
            self._emit_percent(100)
            self.progress.emit('[100%] Preview ready.')
            self.finished_ok.emit(result)
        except Exception as exc:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
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
        self._estimated_listening_seconds = 0.0
        self._estimated_generation_seconds = 0.0
        self._active_calibration_key: str | None = None
        self._active_calibration_is_resume = False
        self._calibration_factor = 2.45
        self.motion_settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        self._reduce_motion_enabled = bool(
            self.motion_settings.value("ui/reduce_motion", False, type=bool)
        )

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._player_position)
        self.music_player = QMediaPlayer(self)
        self.music_audio_output = QAudioOutput(self)
        self.music_audio_output.setVolume(0.85)
        self.music_player.setAudioOutput(self.music_audio_output)
        self.music_player.playbackStateChanged.connect(self._background_music_state_changed)
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

        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        self.content_root_layout = root
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
        self.generation_estimate = QLabel()
        self.generation_estimate.setWordWrap(True)
        self.generation_estimate.setObjectName("muted")
        overview_layout.addWidget(self.generation_estimate)
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
        self.pronunciation_box = pronunciation_box
        pronunciation_box.setObjectName("pronunciationDictionarySection")
        pronunciation_layout = QVBoxLayout(pronunciation_box)
        pronunciation_hint = QLabel(
            "Add words or names the voice should pronounce differently. "
            "This changes only narration text; the original book remains untouched."
        )
        pronunciation_hint.setWordWrap(True)
        pronunciation_layout.addWidget(pronunciation_hint)

        pronunciation_filter_row = QHBoxLayout()
        self.pronunciation_scope = QComboBox()
        self.pronunciation_scope.setObjectName("pronunciationScope")
        self.pronunciation_scope.addItem("Current book", "book")
        self.pronunciation_scope.addItem("Global library", "global")
        pronunciation_filter_row.addWidget(self.pronunciation_scope)
        self.pronunciation_search = QLineEdit()
        self.pronunciation_search.setObjectName("pronunciationSearch")
        self.pronunciation_search.setPlaceholderText("Search dictionary…")
        self.pronunciation_search.setClearButtonEnabled(True)
        pronunciation_filter_row.addWidget(self.pronunciation_search, 1)
        pronunciation_layout.addLayout(pronunciation_filter_row)
        self.pronunciation_search.textChanged.connect(self._apply_pronunciation_search)
        self.pronunciation_scope.currentIndexChanged.connect(self._switch_pronunciation_scope)

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
        self.audio_settings_box = settings
        settings.setObjectName("audioSettingsSection")
        settings_form = QFormLayout(settings)
        self._background_audio_form = settings_form

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
        try:
            global_bitrate = int(QSettings("RyuBlanc", "Ryu's Audiobook").value(
                "audio/default_bitrate", DEFAULT_AUDIO_BITRATE_KBPS
            ) or DEFAULT_AUDIO_BITRATE_KBPS)
        except (TypeError, ValueError):
            global_bitrate = DEFAULT_AUDIO_BITRATE_KBPS
        self.audio_bitrate.setCurrentIndex(
            max(0, self.audio_bitrate.findData(global_bitrate))
        )
        settings_form.addRow("Audio quality", self.audio_bitrate)

        # Stage 1: an optional user-supplied/licensed continuous music bed.
        # The default remains narration-only. Track settings are stored in the
        # project state and mixed only during final M4B packaging.
        audio_state = load_state(self.project_folder) if self.project_folder else {}
        try:
            project_bitrate = int(audio_state.get("audio_bitrate")) if audio_state.get("audio_bitrate") is not None else None
        except (TypeError, ValueError):
            project_bitrate = None
        if project_bitrate is not None:
            saved_bitrate_index = self.audio_bitrate.findData(project_bitrate)
            if saved_bitrate_index >= 0:
                self.audio_bitrate.setCurrentIndex(saved_bitrate_index)
        self.background_audio_enabled = QCheckBox("Enable background music / ambience")
        self.background_audio_enabled.setChecked(
            bool(audio_state.get("background_audio_enabled", False))
        )
        settings_form.addRow("Background audio", self.background_audio_enabled)

        self.background_audio_mode = QComboBox()
        self.background_audio_mode.addItem("Automatic • chapter-aware music", "auto")
        self.background_audio_mode.addItem("Manual • use my own tracks", "manual")
        legacy_has_manual_tracks = bool(
            str(audio_state.get("background_audio_path") or "").strip()
            or str(audio_state.get("ambience_audio_path") or "").strip()
        )
        saved_audio_mode = str(
            audio_state.get("background_audio_mode")
            or ("manual" if legacy_has_manual_tracks else "auto")
        )
        saved_mode_index = self.background_audio_mode.findData(saved_audio_mode)
        self.background_audio_mode.setCurrentIndex(max(0, saved_mode_index))
        self.background_audio_mode.currentIndexChanged.connect(
            lambda *_: self._toggle_background_audio_controls(
                self.background_audio_enabled.isChecked()
            )
        )
        settings_form.addRow("Music mode", self.background_audio_mode)

        self.auto_music_style = QComboBox()
        for label, value in (
            ("Auto-detect from each chapter", "auto"),
            ("Epic Anime Fantasy", "fantasy"),
            ("Cinematic Mystery / Suspense", "mystery"),
            ("Emotional Cinematic Drama", "romance"),
            ("Dark Supernatural Tension", "dark"),
            ("Heroic Anime Battle", "action"),
            ("Adventure Journey / Exploration", "calm"),
            ("High-Energy Anime Rock", "anime-rock"),
            ("Futuristic Sword-Fantasy / Sci-Fi", "sci-fi"),
        ):
            self.auto_music_style.addItem(label, value)
        saved_style_index = self.auto_music_style.findData(
            str(audio_state.get("auto_music_style") or "auto")
        )
        self.auto_music_style.setCurrentIndex(max(0, saved_style_index))
        settings_form.addRow("Automatic music style", self.auto_music_style)

        # Original rhythmic cinematic arrangements replace the old harmony-pad
        # catalogue. Tracks are synthesized only when previewed or exported.
        ensure_audio_library()
        self.bgm_variation = QComboBox()
        self.bgm_variation.setObjectName("realBgmCatalogue")
        self.bgm_variation.setMinimumContentsLength(28)
        self.bgm_variation.setToolTip(
            "Real audio files only. Auto mode selects a track from your local library "
            "based on each chapter's mood. Add multiple tracks per category for variety."
        )
        self.bgm_variation.addItem("Auto • match each chapter to a real track", "auto")
        for track in list_music_tracks():
            self.bgm_variation.addItem(
                f"{track.category_label} • {track.path.name}",
                str(track.path),
            )
        saved_track_path = str(audio_state.get("auto_music_track_path") or "")
        saved_track_index = self.bgm_variation.findData(saved_track_path)
        self.bgm_variation.setCurrentIndex(saved_track_index if saved_track_index >= 0 else 0)

        music_filter_row = QHBoxLayout()
        self.music_catalogue_search = QLineEdit()
        self.music_catalogue_search.setObjectName("musicCatalogueSearch")
        self.music_catalogue_search.setPlaceholderText("Search tracks, mood or scene…")
        self.music_catalogue_search.setClearButtonEnabled(True)
        music_filter_row.addWidget(self.music_catalogue_search, 2)
        self.music_category_filter = QComboBox()
        self.music_category_filter.setObjectName("musicCategoryFilter")
        self.music_category_filter.addItem("All categories", "all")
        for category_key, category_label in MUSIC_CATEGORIES:
            self.music_category_filter.addItem(category_label, category_key)
        music_filter_row.addWidget(self.music_category_filter, 1)
        music_filter_container = QWidget()
        music_filter_container.setLayout(music_filter_row)
        settings_form.addRow("Browse music", music_filter_container)
        self.music_catalogue_search.textChanged.connect(lambda *_: self._refresh_bgm_catalogue())
        self.music_category_filter.currentIndexChanged.connect(lambda *_: self._refresh_bgm_catalogue())

        music_catalogue_row = QHBoxLayout()
        music_catalogue_row.addWidget(self.bgm_variation, 1)
        self.music_catalogue_preview = QPushButton("▶ Preview selected BGM")
        self.music_catalogue_preview.clicked.connect(self.preview_catalogue_music)
        music_catalogue_row.addWidget(self.music_catalogue_preview)
        self.music_import_button = QPushButton("Import tracks…")
        self.music_import_button.clicked.connect(self.import_music_tracks)
        music_catalogue_row.addWidget(self.music_import_button)
        self.music_sources_button = QPushButton("Find tracks online…")
        self.music_sources_button.clicked.connect(lambda: self.open_audio_sources("music"))
        music_catalogue_row.addWidget(self.music_sources_button)
        self.music_catalogue_container = QWidget()
        self.music_catalogue_container.setLayout(music_catalogue_row)
        settings_form.addRow("Real BGM catalogue", self.music_catalogue_container)
        self._catalogue_preview_path: Path | None = None
        self.music_catalogue_hint = QLabel(
            "Import licensed tracks into story categories. Auto chooses a real, mood-matched file; "
            "if no track is installed, narration stays clean rather than using synthetic music."
        )
        self.music_catalogue_hint.setObjectName("muted")
        settings_form.addRow("", self.music_catalogue_hint)

        self.chapter_transition_sound = QCheckBox(
            "Add real book-opening, chapter-turn and book-closing sounds"
        )
        self.chapter_transition_sound.setChecked(
            bool(audio_state.get("chapter_transition_sound", True))
        )
        self.chapter_transition_sound.setToolTip(
            "Use imported real audio clips. Leave a cue field blank to rotate through "
            "the relevant local library folder."
        )
        settings_form.addRow("", self.chapter_transition_sound)

        # Compatibility field for older saved project state. Generated cue
        # presets are removed from the user interface and export path.
        self.sound_cue_style = QComboBox()
        self.sound_cue_style.addItem("Local audio library (real sounds only)", "library")
        self.sound_cue_style.hide()

        cue_preview_row = QHBoxLayout()
        self.preview_opening_cue = QPushButton("▶ Preview opening")
        self.preview_opening_cue.clicked.connect(lambda: self.preview_cue("opening"))
        cue_preview_row.addWidget(self.preview_opening_cue)
        self.preview_page_cue = QPushButton("▶ Preview next chapter")
        self.preview_page_cue.clicked.connect(lambda: self.preview_cue("page"))
        cue_preview_row.addWidget(self.preview_page_cue)
        self.preview_ending_cue = QPushButton("▶ Preview book closing")
        self.preview_ending_cue.clicked.connect(lambda: self.preview_cue("ending"))
        cue_preview_row.addWidget(self.preview_ending_cue)
        settings_form.addRow("Audition book cues", cue_preview_row)

        custom_cues_layout = QVBoxLayout()
        custom_cues_layout.setContentsMargins(0, 0, 0, 0)
        custom_cues_layout.setSpacing(8)
        self.opening_cue_path = QLineEdit(str(audio_state.get("opening_cue_path") or ""))
        self.opening_cue_path.setPlaceholderText("No opening sound selected • Auto library is active")
        self.page_turn_cue_path = QLineEdit(str(audio_state.get("page_turn_cue_path") or ""))
        self.page_turn_cue_path.setPlaceholderText("Optional chapter-turn clip • blank = auto-rotate library")
        self.ending_cue_path = QLineEdit(str(audio_state.get("ending_cue_path") or ""))
        self.ending_cue_path.setPlaceholderText("Optional closing clip • blank = auto-rotate library")
        self._cue_path_fields = {
            "opening": self.opening_cue_path,
            "page": self.page_turn_cue_path,
            "ending": self.ending_cue_path,
        }

        opening_card = QGroupBox("Book opening")
        self.opening_cue_box = opening_card
        opening_card_layout = QVBoxLayout(opening_card)
        opening_card_layout.setContentsMargins(10, 10, 10, 10)
        opening_card_layout.setSpacing(6)
        opening_card_layout.addWidget(QLabel("Choose a real opening sound, preview it, or use Auto to rotate the opening library."))
        opening_controls = QHBoxLayout()
        opening_controls.addWidget(self.opening_cue_path, 1)
        self.opening_cue_preview_button = QPushButton("▶ Preview")
        self.opening_cue_preview_button.clicked.connect(lambda: self.preview_cue("opening"))
        opening_controls.addWidget(self.opening_cue_preview_button)
        opening_browse = QPushButton("Import from PC…")
        opening_browse.clicked.connect(lambda: self.import_cue_audio("opening"))
        opening_controls.addWidget(opening_browse)
        opening_library = QPushButton("Library…")
        opening_library.clicked.connect(lambda: self.choose_from_cue_library("opening"))
        opening_controls.addWidget(opening_library)
        opening_auto = QPushButton("Auto")
        opening_auto.setToolTip("Clear the selected file and choose from the opening library automatically.")
        opening_auto.clicked.connect(lambda: self.clear_cue_audio_path("opening"))
        opening_controls.addWidget(opening_auto)
        opening_card_layout.addLayout(opening_controls)
        custom_cues_layout.addWidget(opening_card)

        other_cues_card = QGroupBox("Chapter transition and book closing")
        self.transition_cue_box = other_cues_card
        other_cues_layout = QVBoxLayout(other_cues_card)
        other_cues_layout.setContentsMargins(10, 10, 10, 10)
        other_cues_layout.setSpacing(5)
        for kind, field in (("page", self.page_turn_cue_path), ("ending", self.ending_cue_path)):
            row = QHBoxLayout()
            row.addWidget(field, 1)
            browse = QPushButton("Browse…")
            browse.setToolTip("Use one specific local sound file")
            browse.clicked.connect(lambda _checked=False, cue_kind=kind: self.choose_cue_audio(cue_kind))
            row.addWidget(browse)
            library_button = QPushButton("Library…")
            library_button.setToolTip("Choose one of the imported real sounds")
            library_button.clicked.connect(lambda _checked=False, cue_kind=kind: self.choose_from_cue_library(cue_kind))
            row.addWidget(library_button)
            import_button = QPushButton("Import…")
            import_button.clicked.connect(lambda _checked=False, cue_kind=kind: self.import_cue_audio(cue_kind))
            row.addWidget(import_button)
            clear_button = QPushButton("Auto")
            clear_button.setToolTip("Clear the override and rotate through this cue library")
            clear_button.clicked.connect(lambda _checked=False, cue_kind=kind: self.clear_cue_audio_path(cue_kind))
            row.addWidget(clear_button)
            other_cues_layout.addLayout(row)
        custom_cues_layout.addWidget(other_cues_card)
        self.custom_cues_container = QWidget()
        self.custom_cues_container.setLayout(custom_cues_layout)
        settings_form.addRow("Real audiobook cue files", self.custom_cues_container)

        cue_source_row = QHBoxLayout()
        self.cue_sources_button = QPushButton("Find book sounds online…")
        self.cue_sources_button.clicked.connect(lambda: self.open_audio_sources("cue"))
        cue_source_row.addWidget(self.cue_sources_button)
        self.cue_library_hint = QLabel(
            "Add multiple clips to each library for rotation. Opening, page-turn and closing "
            "sounds stay separate; no generated placeholder cues are used."
        )
        self.cue_library_hint.setObjectName("muted")
        cue_source_row.addWidget(self.cue_library_hint, 1)
        cue_source_container = QWidget()
        cue_source_container.setLayout(cue_source_row)
        settings_form.addRow("", cue_source_container)
        self._toggle_custom_cue_fields()

        self.story_effects_enabled = QCheckBox(
            "Add story-aware sound effects (footsteps, doors, weather, impacts, magic, etc.)"
        )
        self.story_effects_enabled.setChecked(
            bool(audio_state.get("story_effects_enabled", True))
        )
        self.story_effects_enabled.setToolTip(
            "Effects are added only for clear action/environment phrases in the chapter text. "
            "The detector avoids broad emotion keywords and limits repeated cues."
        )
        settings_form.addRow("Story sound design", self.story_effects_enabled)

        self.story_effect_volume = QDoubleSpinBox()
        self.story_effect_volume.setRange(0.0, 50.0)
        self.story_effect_volume.setDecimals(0)
        self.story_effect_volume.setSingleStep(2.0)
        self.story_effect_volume.setSuffix("%")
        try:
            saved_sfx_volume = float(audio_state.get("story_effect_volume", 0.22))
        except (TypeError, ValueError):
            saved_sfx_volume = 0.22
        self.story_effect_volume.setValue(
            max(0.0, min(50.0, saved_sfx_volume * 100.0))
        )
        settings_form.addRow("Sound-effect volume", self.story_effect_volume)
        self.story_effects_enabled.toggled.connect(self.story_effect_volume.setEnabled)
        self.story_effect_volume.setEnabled(self.story_effects_enabled.isChecked())

        music_file_row = QHBoxLayout()
        self.background_audio_path = QLineEdit(
            str(audio_state.get("background_audio_path") or "")
        )
        self.background_audio_path.setPlaceholderText("Choose a music/ambience audio file…")
        self.background_audio_browse = QPushButton("Browse…")
        self.background_audio_browse.clicked.connect(self.choose_background_audio)
        self.background_audio_preview = QPushButton("▶ Preview Track")
        self.background_audio_preview.clicked.connect(self.preview_background_audio)
        music_file_row.addWidget(self.background_audio_path, 1)
        music_file_row.addWidget(self.background_audio_browse)
        music_file_row.addWidget(self.background_audio_preview)
        self.music_file_container = QWidget()
        self.music_file_container.setLayout(music_file_row)
        settings_form.addRow("Music / ambience file", self.music_file_container)

        self.background_audio_volume = QDoubleSpinBox()
        self.background_audio_volume.setRange(0.0, 100.0)
        self.background_audio_volume.setDecimals(0)
        self.background_audio_volume.setSingleStep(5.0)
        self.background_audio_volume.setSuffix("%")
        try:
            saved_music_volume = float(audio_state.get("background_audio_volume", 0.18))
        except (TypeError, ValueError):
            saved_music_volume = 0.18
        self.background_audio_volume.setValue(max(0.0, min(100.0, saved_music_volume * 100.0)))
        settings_form.addRow("BGM volume", self.background_audio_volume)

        ambience_file_row = QHBoxLayout()
        self.ambience_audio_path = QLineEdit(
            str(audio_state.get("ambience_audio_path") or "")
        )
        self.ambience_audio_path.setPlaceholderText("Optional ambience track (forest, rain, city, etc.)…")
        self.ambience_audio_browse = QPushButton("Browse…")
        self.ambience_audio_browse.clicked.connect(self.choose_ambience_audio)
        self.ambience_audio_preview = QPushButton("▶ Preview Ambience")
        self.ambience_audio_preview.clicked.connect(self.preview_ambience_audio)
        ambience_file_row.addWidget(self.ambience_audio_path, 1)
        ambience_file_row.addWidget(self.ambience_audio_browse)
        ambience_file_row.addWidget(self.ambience_audio_preview)
        self.ambience_file_container = QWidget()
        self.ambience_file_container.setLayout(ambience_file_row)
        settings_form.addRow("Ambience file", self.ambience_file_container)

        self.ambience_audio_volume = QDoubleSpinBox()
        self.ambience_audio_volume.setRange(0.0, 100.0)
        self.ambience_audio_volume.setDecimals(0)
        self.ambience_audio_volume.setSingleStep(5.0)
        self.ambience_audio_volume.setSuffix("%")
        try:
            saved_ambience_volume = float(audio_state.get("ambience_audio_volume", 0.10))
        except (TypeError, ValueError):
            saved_ambience_volume = 0.10
        self.ambience_audio_volume.setValue(max(0.0, min(100.0, saved_ambience_volume * 100.0)))
        settings_form.addRow("Ambience volume", self.ambience_audio_volume)

        self.background_audio_fade_in = QSpinBox()
        self.background_audio_fade_in.setRange(0, 30)
        self.background_audio_fade_in.setSuffix(" sec")
        self.background_audio_fade_in.setValue(
            max(0, min(30, int(audio_state.get("background_audio_fade_in", 2) or 0)))
        )
        settings_form.addRow("Music fade-in", self.background_audio_fade_in)

        self.background_audio_fade_out = QSpinBox()
        self.background_audio_fade_out.setRange(0, 30)
        self.background_audio_fade_out.setSuffix(" sec")
        self.background_audio_fade_out.setValue(
            max(0, min(30, int(audio_state.get("background_audio_fade_out", 3) or 0)))
        )
        settings_form.addRow("Music fade-out", self.background_audio_fade_out)

        self.background_audio_hint = QLabel(
            "Automatic: chapter-matched local BGM with optional story effects. "
            "Manual: use your own music or ambience. Effects stay beneath narration."
        )
        self.background_audio_hint.setToolTip(
            "Automatic mode selects from 1,344 original local cinematic arrangements "
            "(8 story styles × 8 rhythmic textures × 7 tempos × 3 rhythmic arrangements). "
            "These use bass movement, ostinatos, percussion, strings and melodic leads "
            "instead of the retired quiet harmony-pad recipe. Tracks render only as needed. "
            "The linked cue set adds an opening, chapter page turns and a different closing; "
            "choose a preset or supply your own three recordings. Use only music/ambience "
            "you have permission to use and review the final mix before publishing."
        )
        self.background_audio_hint.setWordWrap(True)
        self.background_audio_hint.setObjectName("muted")
        settings_form.addRow("", self.background_audio_hint)
        self.background_audio_enabled.toggled.connect(self._toggle_background_audio_controls)
        self.background_audio_enabled.toggled.connect(self._update_overview)
        self.background_audio_mode.currentIndexChanged.connect(self._update_overview)
        self.auto_music_style.currentIndexChanged.connect(self._update_overview)
        self.bgm_variation.currentIndexChanged.connect(self._update_overview)
        self.chapter_transition_sound.toggled.connect(self._update_overview)
        self.sound_cue_style.currentIndexChanged.connect(self._update_overview)
        for cue_path_field in self._cue_path_fields.values():
            cue_path_field.textChanged.connect(self._update_overview)
        self.story_effects_enabled.toggled.connect(self._update_overview)
        self.story_effect_volume.valueChanged.connect(self._update_overview)
        self.background_audio_volume.valueChanged.connect(self._update_overview)
        self.ambience_audio_volume.valueChanged.connect(self._update_overview)
        self.narration_speed.currentIndexChanged.connect(self._update_overview)
        self.pacing_profile.currentIndexChanged.connect(self._update_overview)
        self.voice_profile.currentIndexChanged.connect(self._update_overview)
        self._toggle_background_audio_controls(self.background_audio_enabled.isChecked())

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

        preview_options_row = QHBoxLayout()
        preview_options_row.addWidget(QLabel("Preview length"))
        self.preview_duration = QComboBox()
        for seconds in (15, 30, 60):
            self.preview_duration.addItem(f"{seconds} seconds", seconds)
        self.preview_duration.setCurrentIndex(1)
        preview_options_row.addWidget(self.preview_duration)
        self.preview_mix_enabled = QCheckBox("Include selected BGM, story effects and chapter/end cues")
        self.preview_mix_enabled.setChecked(bool(audio_state.get("preview_include_sound_design", True)))
        self.preview_mix_enabled.setToolTip(
            "When enabled, the generated sample auditions narration with the selected "
            "background music/ambience, ducking, story effects and any page-turn or final-book cue. "
            "Turn it off for a dry voice-only comparison."
        )
        preview_options_row.addWidget(self.preview_mix_enabled, 1)
        preview_layout.addLayout(preview_options_row)

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
        self.preview_status = QLabel("Generate a 15/30/60-second preview; optionally include the current soundtrack and effects.")
        self.preview_time = QLabel("0:00 / 0:00")
        preview_time_row.addWidget(self.preview_status, 1)
        preview_time_row.addWidget(self.preview_time)
        preview_layout.addLayout(preview_time_row)

        self.preview_loading = SmoothProgressBar()
        self.preview_loading.setRange(0, 100)
        self.preview_loading.setValue(0)
        self.preview_loading.setTextVisible(True)
        self.preview_loading.setFixedHeight(14)
        self.preview_loading.setVisible(False)
        preview_layout.addWidget(self.preview_loading)
        self.preview_activity = SmoothProgressBar()
        self.preview_activity.setRange(0, 0)
        self.preview_activity.setTextVisible(False)
        self.preview_activity.setFixedHeight(4)
        self.preview_activity.setVisible(False)
        preview_layout.addWidget(self.preview_activity)

        root.addWidget(preview_box)

        progress_box = QGroupBox("Generation")
        progress_box.setObjectName("generationProgressSection")
        progress_layout = QVBoxLayout(progress_box)
        self.progress = SmoothProgressBar()
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
        self.stop_button.clicked.connect(self.stop_result)
        self.open_button = QPushButton("Open Folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_result_folder)
        result_actions.addWidget(self.play_button)
        result_actions.addWidget(self.stop_button)
        result_actions.addWidget(self.open_button)
        result_layout.addLayout(result_actions)

        visualizer_row = QHBoxLayout()
        self.audio_visualizer = AudioVisualizer()
        self.audio_visualizer.set_reduced_motion(self._reduce_motion_enabled)
        visualizer_row.addWidget(self.audio_visualizer, 1)
        self.reduce_motion_toggle = QCheckBox("Reduce motion")
        self.reduce_motion_toggle.setChecked(self._reduce_motion_enabled)
        self.reduce_motion_toggle.setToolTip(
            "Use a static waveform while listening. This also saves a little CPU time."
        )
        self.reduce_motion_toggle.toggled.connect(self._set_reduce_motion)
        visualizer_row.addWidget(self.reduce_motion_toggle)
        result_layout.addLayout(visualizer_row)
        # Connect after playback controls and visualizer exist so an early
        # media-state notification cannot reach a partially initialized page.
        self.player.playbackStateChanged.connect(self._player_playback_state_changed)
        self._player_playback_state_changed(self.player.playbackState())

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
        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("generationPauseButton")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_generation_pause)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.start_button)
        actions.addWidget(self.resume_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

        self.content_scroll.setWidget(content)
        outer.addWidget(self.content_scroll, 1)

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

    def focus_section(self, section: str) -> bool:
        """Scroll the existing production UI to a real feature section."""
        targets = {
            "pronunciation": "pronunciationDictionarySection",
            "sound": "audioSettingsSection",
            "generate": "generationProgressSection",
        }
        object_name = targets.get(str(section or "").strip().lower())
        if not object_name:
            return False
        target = self.findChild(QGroupBox, object_name)
        if target is None or not hasattr(self, "content_scroll"):
            return False
        self.content_scroll.ensureWidgetVisible(target, 0, 18)
        return True

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
        if hasattr(self, "pronunciation_search"):
            self._apply_pronunciation_search()

    def _apply_pronunciation_search(self) -> None:
        query = str(self.pronunciation_search.text() or "").strip().casefold()
        for row in range(self.pronunciation_table.rowCount()):
            values = []
            for column in (0, 1):
                cell = self.pronunciation_table.item(row, column)
                values.append(cell.text().casefold() if cell else "")
            self.pronunciation_table.setRowHidden(
                row, bool(query) and not any(query in value for value in values)
            )

    def _switch_pronunciation_scope(self, *_args) -> None:
        # Save the visible scope before loading the newly selected one.
        if not hasattr(self, "pronunciation_table"):
            return
        previous = str(getattr(self, "_loaded_pronunciation_scope", "book"))
        if previous == str(self.pronunciation_scope.currentData() or "book"):
            return
        self._save_pronunciations(scope=previous)
        self._load_pronunciations()

    def _global_pronunciation_entries(self) -> list[dict]:
        raw = QSettings("RyuBlanc", "Ryu's Audiobook").value(
            "pronunciation/global_dictionary", "[]"
        )
        try:
            entries = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            entries = []
        return [
            dict(item) for item in entries
            if isinstance(item, dict)
            and str(item.get("written") or "").strip()
            and str(item.get("spoken") or "").strip()
        ] if isinstance(entries, list) else []

    def _combined_pronunciation_entries(self) -> list[dict]:
        """Merge global entries with per-book overrides; book entries win by spelling."""
        global_entries = self._global_pronunciation_entries()
        book_entries = []
        if self.project_folder:
            state = load_state(self.project_folder)
            value = state.get("pronunciation_dictionary", [])
            if isinstance(value, list):
                book_entries = [
                    dict(item) for item in value
                    if isinstance(item, dict)
                    and str(item.get("written") or "").strip()
                    and str(item.get("spoken") or "").strip()
                ]
        merged: dict[str, dict] = {}
        for item in global_entries + book_entries:
            merged[str(item["written"]).casefold()] = item
        return list(merged.values())

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
            # Do not scrape every capitalized sentence-initial word from prose.
            # Use names returned by the same source-grounded character analyzer
            # as Character Studio, and only suggest readings for those entities.
            detected = analyze_book(self.chapters)
            candidate_names = []
            for character in detected.characters:
                name = str(getattr(character, "name", "") or "").strip()
                if name:
                    candidate_names.append(name)
            all_names = set(candidate_names)
            source_text = "\n".join(ch.text or "" for ch in self.chapters)
            added = 0
            for clean in dict.fromkeys(candidate_names):
                if clean.casefold() in existing or clean.casefold() not in source_text.casefold():
                    continue
                if not is_likely_character_name_candidate(clean, known_names=all_names):
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
            # Do not trust the model's language label alone: "Having" or "The Oath"
            # must not become a Japanese reading just because the model tagged it
            # as Japanese. Character names from the book bible are explicitly allowed.
            if not is_likely_character_name_candidate(
                written, known_names=character_names, script=script
            ):
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
        scope = str(self.pronunciation_scope.currentData() or "book")
        self._loaded_pronunciation_scope = scope
        if not self.project_folder:
            return
        if scope == "global":
            entries = self._global_pronunciation_entries()
            for item in entries:
                self._add_pronunciation_row(
                    str(item.get("written") or ""),
                    str(item.get("spoken") or ""),
                    item.get("enabled", True) is not False,
                    source=str(item.get("source") or "manual"),
                )
            self.pronunciation_status.setText(
                f"{len(entries)} global pronunciation entr{'y' if len(entries) == 1 else 'ies'} loaded. "
                "Saved entries are available across books on this PC."
                if entries else "Global library is empty. Add a pronunciation and save it to reuse it across books."
            )
            self._apply_pronunciation_search()
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
        self._apply_pronunciation_search()

    def _save_pronunciations(self, scope: str | None = None):
        target_scope = str(scope or self.pronunciation_scope.currentData() or "book")
        entries = self._pronunciation_entries()
        if target_scope == "global":
            settings = QSettings("RyuBlanc", "Ryu's Audiobook")
            settings.setValue(
                "pronunciation/global_dictionary",
                json.dumps(entries, ensure_ascii=False),
            )
            settings.sync()
            self.pronunciation_status.setText(
                f"Saved {len(entries)} global pronunciation entr{'y' if len(entries) == 1 else 'ies'}."
            )
            return
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        state["pronunciation_dictionary"] = entries
        state["pronunciation_dictionary_version"] = 2
        save_state(self.project_folder, state)
        self.pronunciation_status.setText(
            f"{len(entries)} pronunciation override{'s' if len(entries) != 1 else ''} saved for this book."
            if entries else "No pronunciation overrides saved for this book."
        )
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
        legacy_cast = state.get("voice_cast", {})
        legacy_cast = legacy_cast if isinstance(legacy_cast, dict) else {}
        identity_cast = state.get("voice_cast_identity_assignments", {})
        lines = []
        if isinstance(identity_cast, dict) and identity_cast:
            for identity, voice in identity_cast.items():
                parsed = parse_character_identity_key(identity)
                if not parsed or not str(voice or "").strip():
                    continue
                series, name = parsed
                lines.append(f"{name} [{series}] → {voice}")
            # Narrator remains a legacy, project-wide fallback assignment.
            narrator = legacy_cast.get("Narrator") or legacy_cast.get("narrator")
            if narrator:
                lines.append(f"Narrator → {narrator}")
        else:
            lines = [f"{name} → {voice}" for name, voice in legacy_cast.items() if voice]
        if not lines:
            self.cast_summary.setText("No character-specific voice assignments saved. Narrator voice will be used.")
            return
        self.cast_summary.setText(
            "Saved voice cast assignments:\n" + "\n".join(lines) +
            "\n\nThese assignments are stored with this book and are ready for the cast-aware narration engine."
        )

    def _load_profiles(self, keep_name: str | None = None) -> None:
        current = keep_name if keep_name is not None else self.voice_profile.currentText()
        if self.profiles:
            rows = [(profile.name, profile) for profile in self.profiles]
            selected = next((profile for profile in self.profiles if profile.name == current), None)
        else:
            rows = [("No saved voice profiles", None)]
            selected = None
        sync_combo_items_in_place(self.voice_profile, rows, selected)

    def _refresh_voice_profiles(self) -> None:
        current = self.voice_profile.currentText()
        self.profiles = load_profiles()
        self._load_profiles(current)
        # Signals are intentionally blocked during the in-place update, so refresh
        # dependent readiness and duration estimates once from the final selection.
        self._update_overview()
        self._refresh_readiness()
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

    def refresh_chapter_sources(self) -> None:
        """Refresh chapter-dependent UI without clearing the visible selector."""
        selected_number = self.preview_chapter.currentData()
        rows = [
            (f"Chapter {chapter.number}: {chapter.title}", chapter.number)
            for chapter in self.chapters
        ]
        sync_combo_items_in_place(self.preview_chapter, rows, selected_number)
        self.preview_chapter.setEnabled(bool(self.chapters))
        self._update_overview()
        self._refresh_readiness()
        self._refresh_resume_state()


    def _update_overview(self) -> None:
        words = sum(len(ch.text.split()) for ch in self.chapters)
        speed = float(self.narration_speed.currentData() or 0.90) if hasattr(self, "narration_speed") else 0.90
        effective_wpm = max(60.0, 170.0 * speed)
        listening_seconds = words * 60.0 / effective_wpm
        if hasattr(self, "motion_settings") and hasattr(self, "voice_profile"):
            try:
                key = self._generation_calibration_key()
                observed_seconds_per_word = float(
                    self.motion_settings.value(f"{key}/seconds_per_word", 0.0) or 0.0
                )
                if observed_seconds_per_word > 0:
                    listening_seconds = words * observed_seconds_per_word
            except (TypeError, ValueError, AttributeError):
                pass
        # Include the actual transition/end cues in the duration estimate when
        # this book is configured to add them.
        if (
            hasattr(self, "chapter_transition_sound")
            and self.chapter_transition_sound.isChecked()
            and len(self.chapters) > 0
        ):
            from app.audio.sound_design import ENDING_SECONDS, OPENING_SECONDS, PAGE_TURN_SECONDS
            listening_seconds += OPENING_SECONDS + max(0, len(self.chapters) - 1) * PAGE_TURN_SECONDS + ENDING_SECONDS
            if str(self.sound_cue_style.currentData() or "classic-book") == "custom":
                for path_field, times_used, default_seconds in (
                    (self.opening_cue_path, 1, OPENING_SECONDS),
                    (self.page_turn_cue_path, max(0, len(self.chapters) - 1), PAGE_TURN_SECONDS),
                    (self.ending_cue_path, 1, ENDING_SECONDS),
                ):
                    try:
                        custom_path = Path(path_field.text().strip()).expanduser()
                        if custom_path.is_file():
                            listening_seconds += times_used * (
                                _duration_ms(custom_path) / 1000.0 - default_seconds
                            )
                    except Exception:
                        pass
        self._estimated_listening_seconds = max(0.0, listening_seconds)
        listening_minutes = max(1, round(self._estimated_listening_seconds / 60.0))
        self.chapter_count.setText(f"Chapters: {len(self.chapters)}")
        self.word_count.setText(f"Words: {words:,}")
        self.duration_estimate.setText(
            f"Estimated listening length: {listening_minutes // 60}h {listening_minutes % 60:02d}m "
            f"at {speed:.2f}× narration speed"
        )
        self.duration_estimate.setToolTip(
            "Estimated duration of the finished narration at the selected playback speed. "
            "This is not the time required to generate it. This estimate learns actual seconds-per-word "
            "from completed books using the same voice and settings and includes enabled chapter/end cues."
        )
        factor = self._calibration_factor
        samples = 0
        try:
            key = self._generation_calibration_key()
            stored_factor = self.motion_settings.value(f"{key}/realtime_factor", None)
            if stored_factor is not None and float(stored_factor) > 0:
                factor = max(0.4, min(20.0, float(stored_factor)))
                samples = int(self.motion_settings.value(f"{key}/samples", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            pass
        self._estimated_generation_seconds = self._estimated_listening_seconds * factor
        processing_minutes = max(1, round(self._estimated_generation_seconds / 60.0))
        confidence = (
            f"learned from {samples} completed export(s)"
            if samples > 0
            else "initial estimate from your observed 18:55 processing / 7:43 audio run"
        )
        if hasattr(self, "generation_estimate"):
            self.generation_estimate.setText(
                f"Estimated generation time: about {processing_minutes // 60}h {processing_minutes % 60:02d}m "
                f"({factor:.2f}× listening duration; {confidence})"
            )
            self.generation_estimate.setToolTip(
                "Includes voice synthesis, sound design and M4B packaging. The estimate starts from "
                "your last observed ~2.45× real-time run, then learns a separate timing ratio and "
                "listening duration for this voice/backend/speed/pacing/soundtrack configuration on this PC."
            )

    def _default_output(self) -> Path | None:
        if not self.project_folder:
            return None
        # New exports use the configured audio-assets location, grouped by this
        # unique project folder so similarly titled books cannot overwrite each other.
        project_label = "".join(
            c if c not in '<>:"/\\|?*' else "_"
            for c in self.project_folder.name
        ).strip() or "Project"
        folder = audiobooks_root() / project_label
        title = self.title.text().strip() or self.project_folder.name
        safe = "".join(c if c not in '<>:"/\\|?*' else "_" for c in title).strip() or "Audiobook"
        return folder / f"{safe}.m4b"

    def _set_default_output(self) -> None:
        default = self._default_output()
        state = load_state(self.project_folder) if self.project_folder else {}
        saved = Path(state["output_path"]).expanduser() if state.get("output_path") else None
        if saved and not saved.is_absolute() and self.project_folder:
            saved = self.project_folder / saved
        # Always honour a book's explicitly saved output path, including a path
        # the user selected on another drive. Only a book without a saved path
        # receives the configured default audio-assets destination.
        if saved:
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
            try:
                portable_cover = persist_project_cover(self.cover, self.project_folder)
                if portable_cover != self.cover.resolve():
                    self.cover = portable_cover
                    state["cover_path"] = str(portable_cover)
                    save_state(self.project_folder, state)
            except (OSError, ValueError, RuntimeError) as exc:
                log.warning("Could not migrate an existing cover into the project folder: %s", exc)
            self.cover_label.setText(self.cover.name)

    def _current_profiles(self) -> list[VoiceProfile]:
        """Overlay fresh persisted records onto the in-memory voice catalogue."""
        saved = {profile.name.casefold(): profile for profile in load_saved_profiles()}
        return [saved.get(profile.name.casefold(), profile) for profile in self.profiles]

    def _selected_profile(self) -> VoiceProfile | None:
        value = self.voice_profile.currentData()
        if not isinstance(value, VoiceProfile):
            return None
        # The Voice page and Generate page live in the same application
        # session. Always prefer the persisted record when it exists instead
        # of an older object captured when this page was first opened.
        saved = load_saved_profile(value.name)
        if saved:
            return saved
        return value

    def _generation_calibration_key(self) -> str:
        profile = self._selected_profile()
        recipe = {
            "profile": getattr(profile, "name", "unselected"),
            "provider": getattr(profile, "provider", "unknown"),
            "voice": getattr(profile, "voice_id", "default"),
            "backend": self.backend.currentData() if hasattr(self, "backend") else "automatic",
            "speed": float(self.narration_speed.currentData() or 1.0) if hasattr(self, "narration_speed") else 1.0,
            "pacing": self.pacing_profile.currentData() if hasattr(self, "pacing_profile") else "natural",
            "bgm_enabled": self.background_audio_enabled.isChecked() if hasattr(self, "background_audio_enabled") else False,
            "bgm_mode": self.background_audio_mode.currentData() if hasattr(self, "background_audio_mode") else "off",
            "bgm_style": self.auto_music_style.currentData() if hasattr(self, "auto_music_style") else "auto",
            "bgm_track": self.bgm_variation.currentData() if hasattr(self, "bgm_variation") else "auto",
            "bgm_file": self.background_audio_path.text().strip() if hasattr(self, "background_audio_path") else "",
            "ambience_file": self.ambience_audio_path.text().strip() if hasattr(self, "ambience_audio_path") else "",
            "bgm_volume": float(self.background_audio_volume.value()) if hasattr(self, "background_audio_volume") else 18.0,
            "ambience_volume": float(self.ambience_audio_volume.value()) if hasattr(self, "ambience_audio_volume") else 10.0,
            "story_effects": self.story_effects_enabled.isChecked() if hasattr(self, "story_effects_enabled") else False,
            "story_effect_volume": float(self.story_effect_volume.value()) if hasattr(self, "story_effect_volume") else 22.0,
            "chapter_cues": self.chapter_transition_sound.isChecked() if hasattr(self, "chapter_transition_sound") else False,
            "cue_style": self.sound_cue_style.currentData() if hasattr(self, "sound_cue_style") else "classic-book",
            "opening_cue_path": self.opening_cue_path.text().strip() if hasattr(self, "opening_cue_path") else "",
            "page_turn_cue_path": self.page_turn_cue_path.text().strip() if hasattr(self, "page_turn_cue_path") else "",
            "ending_cue_path": self.ending_cue_path.text().strip() if hasattr(self, "ending_cue_path") else "",
        }
        signature = json.dumps(recipe, sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
        return f"generation/calibration/{digest}"

    def _toggle_background_audio_controls(self, enabled: bool) -> None:
        enabled = bool(enabled)
        auto_mode = enabled and self.background_audio_mode.currentData() == "auto"
        manual_mode = enabled and self.background_audio_mode.currentData() == "manual"
        self.background_audio_mode.setEnabled(enabled)
        self.auto_music_style.setEnabled(auto_mode)
        self.bgm_variation.setEnabled(auto_mode)
        self.music_catalogue_preview.setEnabled(auto_mode)
        # Book cue controls stay enabled even when background music is turned off.
        # Hide manual track rows entirely in Automatic mode instead of leaving
        # four disabled rows on screen. The rows return when Manual is selected.
        self.music_catalogue_hint.setVisible(auto_mode)
        for widget, visible in (
            (self.music_file_container, manual_mode),
            (self.background_audio_volume, auto_mode or manual_mode),
            (self.ambience_file_container, manual_mode),
            (self.ambience_audio_volume, manual_mode),
            (self.music_catalogue_container, auto_mode),
        ):
            self._background_audio_form.setRowVisible(widget, visible)
        for widget in (
            self.background_audio_path,
            self.background_audio_browse,
            self.background_audio_preview,
            self.ambience_audio_path,
            self.ambience_audio_browse,
            self.ambience_audio_preview,
            self.ambience_audio_volume,
        ):
            widget.setEnabled(manual_mode)
        self.background_audio_volume.setEnabled(auto_mode or manual_mode)
        for widget in (self.background_audio_fade_in, self.background_audio_fade_out):
            widget.setEnabled(enabled)

    def _refresh_bgm_catalogue(self, preferred_path: str | None = None) -> None:
        current = str(preferred_path or self.bgm_variation.currentData() or "auto")
        query = str(self.music_catalogue_search.text() if hasattr(self, "music_catalogue_search") else "").strip().casefold()
        category = str(self.music_category_filter.currentData() or "all") if hasattr(self, "music_category_filter") else "all"
        tracks = list_music_tracks()
        visible_tracks = [
            track for track in tracks
            if (category == "all" or track.category == category)
            and (
                not query
                or query in track.path.name.casefold()
                or query in track.category_label.casefold()
                or query in track.category.casefold()
                or query in str(track.license_note or "").casefold()
            )
        ]
        self.bgm_variation.blockSignals(True)
        self.bgm_variation.clear()
        self.bgm_variation.addItem("Auto • match each chapter to a real track", "auto")
        for track in visible_tracks:
            self.bgm_variation.addItem(
                f"{track.category_label} • {track.path.name}",
                str(track.path),
            )
        index = self.bgm_variation.findData(current)
        self.bgm_variation.setCurrentIndex(index if index >= 0 else 0)
        self.bgm_variation.blockSignals(False)
        if hasattr(self, "music_catalogue_hint"):
            self.music_catalogue_hint.setText(
                f"Showing {len(visible_tracks)} of {len(tracks)} local music tracks. "
                "Search by title or mood; choose a category to narrow the catalogue. "
                "Import licensed tracks to expand your offline library."
            )

    def import_music_tracks(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import licensed BGM / audiobook music",
            "",
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma);;All Files (*.*)",
        )
        if not files:
            return
        labels = [label for _key, label in MUSIC_CATEGORIES]
        preferred = labels.index("Universal / low-distraction narration bed")
        selected_label, ok = QInputDialog.getItem(
            self,
            "Categorize imported music",
            "Choose the main story mood for these files:",
            labels,
            preferred,
            False,
        )
        if not ok:
            return
        category = next(key for key, label in MUSIC_CATEGORIES if label == selected_label)
        license_note, _ = QInputDialog.getText(
            self,
            "Source and license note",
            "Optional source URL / license note (saved locally beside the track):",
        )
        added = import_audio_files(
            files,
            target_kind="music",
            category=category,
            license_note=license_note,
        )
        self._refresh_bgm_catalogue("auto")
        self.status.setText(
            f"Imported {len(added)} real BGM track(s) into {selected_label}. "
            "Auto mode can now match these tracks to chapter moods."
        )

    def open_audio_sources(self, group: str = "both") -> None:
        valid = [
            source for source in AUDIO_SOURCE_LINKS
            if group == "both" or source["group"] in {group, "both"}
        ]
        if not valid:
            return
        labels = [source["label"] for source in valid]
        selected, ok = QInputDialog.getItem(
            self,
            "Find licensed audiobook audio",
            "Choose a source to open in your browser:",
            labels,
            0,
            False,
        )
        if not ok:
            return
        source = next(item for item in valid if item["label"] == selected)
        QDesktopServices.openUrl(QUrl(source["url"]))
        self.status.setText(
            "Source opened. Review the track's current license, download the files you choose, "
            "then import them into the matching local category."
        )

    def import_cue_audio(self, kind: str) -> None:
        if kind not in self._cue_path_fields:
            self.status.setText(f"Unknown cue type: {kind}")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"Import licensed {CUE_KIND_LABELS.get(kind, kind)} clips",
            "",
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma);;All Files (*.*)",
        )
        if not files:
            return
        license_note, _ = QInputDialog.getText(
            self,
            "Source and license note",
            "Optional source URL / license note (saved locally beside these clips):",
        )
        added = import_audio_files(
            files,
            target_kind=kind,
            license_note=license_note,
        )
        if kind == "opening" and added:
            # Importing from the opening card selects the first imported clip
            # so the filename is visible and the preview uses that exact file.
            self._cue_path_fields[kind].setText(str(added[0]))
            self.status.setText(
                f"Imported {len(added)} opening sound(s). Selected: {added[0].name}. "
                "Use Auto to rotate through the opening library."
            )
        else:
            self._cue_path_fields[kind].clear()
            self.status.setText(
                f"Imported {len(added)} real {kind} cue(s). "
                "Leave this field blank to rotate through the library or choose a specific file."
            )

    def choose_from_cue_library(self, kind: str) -> None:
        tracks = list_cue_tracks(kind)
        if not tracks:
            self.status.setText(
                f"No {kind} cues are installed. Import licensed clips or use Find book sounds online…"
            )
            return
        labels = [f"{path.name} — {path.parent.name}" for path in tracks]
        selected, ok = QInputDialog.getItem(
            self,
            f"Choose {CUE_KIND_LABELS.get(kind, kind)}",
            "Select one real local audio file:",
            labels,
            0,
            False,
        )
        if ok:
            chosen = tracks[labels.index(selected)]
            self._cue_path_fields[kind].setText(str(chosen))
            self.status.setText(f"Selected real cue: {chosen.name}")

    def clear_cue_audio_path(self, kind: str) -> None:
        field = self._cue_path_fields.get(kind)
        if field is not None:
            field.clear()
            self.status.setText(
                f"{kind.title()} cue will auto-rotate through its imported library."
            )

    def choose_background_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Music or Ambience",
            self.background_audio_path.text().strip(),
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma);;All Files (*.*)",
        )
        if path:
            self.background_audio_path.setText(str(Path(path)))
            self.status.setText("Background track selected. Enable Background music to include it in the final M4B.")

    def _toggle_custom_cue_fields(self, *_args) -> None:
        # The library is always available. A blank path means auto-rotate
        # through real local files for that cue role.
        self.custom_cues_container.setVisible(True)

    def choose_cue_audio(self, kind: str) -> None:
        field = self._cue_path_fields.get(kind)
        if field is None:
            self.status.setText(f"Unknown sound cue: {kind}")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select a specific {kind} sound",
            field.text().strip(),
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma);;All Files (*.*)",
        )
        if path:
            field.setText(str(Path(path).expanduser()))
            self.status.setText(f"Selected real {kind} sound: {Path(path).name}")

    def preview_cue(self, kind: str) -> None:
        if kind not in self._cue_path_fields:
            self.status.setText(f"Unknown sound cue: {kind}")
            return
        # The opening preview button is a true play/pause toggle for the
        # currently selected cue, using the shared in-app audio player.
        if kind == "opening":
            current = self.music_player.source().toLocalFile()
            if current and self.music_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.music_player.pause()
                self.opening_cue_preview_button.setText("▶ Preview")
                self.status.setText("Opening sound preview paused.")
                return
            if current and self.music_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self.music_player.play()
                self.opening_cue_preview_button.setText("Ⅱ Pause")
                self.status.setText("Resumed opening sound preview.")
                return
        selected = self._cue_path_fields[kind].text().strip() or None
        index = self.preview_chapter.currentIndex()
        chapter = self.chapters[index] if 0 <= index < len(self.chapters) else None
        title = chapter.title if chapter else self.title.text().strip()
        text = chapter.text if chapter else ""
        cue = resolve_cue_track(
            kind,
            selected_path=selected,
            seed_text=f"{kind}|{title}|{text}|{index}",
        )
        if cue is None or not cue.is_file():
            self.status.setText(
                f"No real {kind} sound is installed. Import licensed clips with Import… "
                "or use Find book sounds online…"
            )
            return
        self.music_player.stop()
        self.music_player.setSource(QUrl.fromLocalFile(str(cue.resolve())))
        self.music_player.play()
        if kind == "opening":
            self.opening_cue_preview_button.setText("Ⅱ Pause")
        label = CUE_KIND_LABELS.get(kind, kind)
        self.status.setText(f"Previewing real {label.lower()}: {cue.name}")

    def preview_catalogue_music(self) -> None:
        if self.music_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            current = self.music_player.source().toLocalFile()
            if self._catalogue_preview_path and current == str(self._catalogue_preview_path):
                self.music_player.pause()
                return
        index = self.preview_chapter.currentIndex()
        chapter = self.chapters[index] if 0 <= index < len(self.chapters) else None
        title = chapter.title if chapter else self.title.text().strip()
        text = chapter.text if chapter else ""
        from app.audio.sound_design import detect_chapter_mood
        mood = detect_chapter_mood(
            title,
            text,
            str(self.auto_music_style.currentData() or "auto"),
        )
        selected_value = str(self.bgm_variation.currentData() or "auto")
        selected_track = None if selected_value == "auto" else selected_value
        track = resolve_music_track(
            mood,
            selected_track=selected_track,
            seed_text=f"{title}|{text}|{index}",
        )
        if track is None or not track.is_file():
            self.status.setText(
                f"No real BGM track is installed for {mood}. Use Import tracks… or Find tracks online… "
                "to add audio you are licensed to use."
            )
            return
        self._catalogue_preview_path = track.resolve()
        self.music_player.stop()
        self.music_player.setSource(QUrl.fromLocalFile(str(track.resolve())))
        self.music_player.play()
        self.status.setText(
            f"Previewing real BGM • {mood.title()} • {track.name}. "
            "Use Voice Preview to hear this track beneath narration."
        )

    def preview_background_audio(self) -> None:
        self._preview_audio_layer(self.background_audio_path, "background music")

    def choose_ambience_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Ambience Track",
            self.ambience_audio_path.text().strip(),
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma);;All Files (*.*)",
        )
        if path:
            self.ambience_audio_path.setText(str(Path(path)))
            self.status.setText("Ambience track selected. Enable background audio to include it in the final M4B.")

    def preview_ambience_audio(self) -> None:
        self._preview_audio_layer(self.ambience_audio_path, "ambience")

    def _preview_audio_layer(self, field: QLineEdit, label: str) -> None:
        value = field.text().strip()
        if not value or not Path(value).is_file():
            self.status.setText(f"Choose a valid {label} audio file before previewing it.")
            return
        if self.music_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.music_player.pause()
            return
        self.music_player.setSource(QUrl.fromLocalFile(str(Path(value).resolve())))
        self.music_player.play()
        self.status.setText(f"Previewing {label}: {Path(value).name}")

    def _background_music_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        if hasattr(self, "background_audio_preview"):
            self.background_audio_preview.setText("Ⅱ Pause Track" if playing else "▶ Preview Track")
        if hasattr(self, "music_catalogue_preview"):
            current = self.music_player.source().toLocalFile()
            catalogue = str(self._catalogue_preview_path) if self._catalogue_preview_path else ""
            if catalogue and current == catalogue:
                self.music_catalogue_preview.setText("Ⅱ Pause BGM" if playing else "▶ Preview selected BGM")

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save M4B", str(self._default_output() or ""),
            "M4B Audiobook (*.m4b)",
        )
        if path:
            self.output.setText(str(Path(path).with_suffix(".m4b")))
            self._refresh_readiness()

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Cover", "", "Images (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff)"
        )
        if path:
            selected = Path(path)
            try:
                self.cover = persist_project_cover(selected, self.project_folder) if self.project_folder else selected
            except (OSError, ValueError) as exc:
                # Keep the chosen image usable for this session, but make the
                # portability problem visible instead of silently reverting to
                # the generic Dashboard artwork.
                self.cover = selected
                self.cover_label.setText(f"{selected.name} (external file; could not copy)")
                self._refresh_readiness()
                log.warning("Could not persist cover image into the project folder: %s", exc, exc_info=True)
                return
            self.cover_label.setText(self.cover.name)
            self._refresh_readiness()

    def _cast_provider(self, narrator_provider, narrator_voice):
        if not self.project_folder:
            return narrator_provider, narrator_voice
        state = load_state(self.project_folder)
        assignments = state.get("voice_cast", {})
        identity_assignments = state.get("voice_cast_identity_assignments", {})
        if not assignments and not identity_assignments:
            return narrator_provider, narrator_voice
        from app.tts.cast_provider import CastAwareProvider
        profiles = {profile.name: profile for profile in self._current_profiles()}
        narrating_character = state.get("voice_cast_narrating_character")
        return CastAwareProvider(
            narrator_provider,
            narrator_voice,
            profiles,
            assignments,
            narrating_character=narrating_character,
            backend_override=self.backend.currentData() or "automatic",
            identity_assignments=identity_assignments,
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
        pronunciation_dictionary = self._combined_pronunciation_entries()
        text = chapter.text
        output = Path(tempfile.gettempdir()) / 'ryu_audiobook_voice_preview.wav'
        backend = self.backend.currentData() or profile.backend
        if backend == 'automatic':
            backend = profile.backend

        preview_seconds = int(self.preview_duration.currentData() or 30)
        selected_bgm_path_value = str(self.bgm_variation.currentData() or "auto")
        mix_settings = {
            "enabled": self.preview_mix_enabled.isChecked(),
            "background_enabled": True,
            "background_mode": str(self.background_audio_mode.currentData() or "auto"),
            "music_style": str(self.auto_music_style.currentData() or "auto"),
            "music_variation_id": None if selected_bgm_path_value == "auto" else selected_bgm_path_value,
            "background_audio_path": self.background_audio_path.text().strip(),
            "ambience_audio_path": self.ambience_audio_path.text().strip(),
            "music_volume": float(self.background_audio_volume.value()) / 100.0,
            "ambience_volume": float(self.ambience_audio_volume.value()) / 100.0,
            "story_effects_enabled": self.story_effects_enabled.isChecked(),
            "story_effect_volume": float(self.story_effect_volume.value()) / 100.0,
            "chapter_transition_sound": self.chapter_transition_sound.isChecked(),
            "is_first_chapter": index == 0,
            "is_last_chapter": index == len(self.chapters) - 1,
            "sound_cue_style": "library",
            "opening_cue_path": self.opening_cue_path.text().strip(),
            "page_turn_cue_path": self.page_turn_cue_path.text().strip(),
            "ending_cue_path": self.ending_cue_path.text().strip(),
        }
        self.preview_worker = VoicePreviewWorker(
            profile, backend, self.project_folder, self._current_profiles(), pronunciation_dictionary,
            text, output, float(self.narration_speed.currentData() or 0.90),
            self.pacing_profile.currentData() or 'natural',
            dialogue_assignments=getattr(chapter, "dialogue_assignments", []),
            target_seconds=preview_seconds,
            mix_settings=mix_settings,
        )
        self.preview_worker.progress.connect(self._preview_worker_progress)
        self.preview_worker.percent.connect(self.preview_loading.setValue)
        self.preview_worker.finished_ok.connect(self._preview_worker_ok)
        self.preview_worker.failed.connect(self._preview_worker_failed)
        self.preview_worker.cancelled.connect(self._preview_worker_cancelled)
        self.preview_worker.finished.connect(self._preview_worker_finished)

        self.preview_button.setEnabled(False)
        self.preview_play_button.setEnabled(False)
        self.preview_stop_button.setEnabled(True)
        self.preview_loading.setValue(5)
        self.preview_loading.setVisible(True)
        self.preview_activity.setVisible(True)
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
        mix_label = " • Full soundtrack mix" if self.preview_mix_enabled.isChecked() else " • Dry voice"
        self.preview_status.setText(
            f'100% • Preview ready{mix_label} • {result.segments} narration segment(s) • Voices: {voice_summary}'
        )
        self.status.setText(
            "Preview generated with the current voice, pronunciation, pacing and selected sound design."
            if self.preview_mix_enabled.isChecked()
            else "Dry voice preview generated with the current voice and narration settings."
        )

    def _preview_worker_failed(self, message: str) -> None:
        self.preview_path = None
        self.preview_play_button.setEnabled(False)
        self.preview_stop_button.setEnabled(False)
        self.preview_loading.setValue(0)
        self.preview_activity.setVisible(False)
        self.preview_status.setText('0% • Preview generation failed.')
        self.status.setText(f'Preview failed: {message}')

    def _preview_worker_finished(self) -> None:
        self.preview_loading.setVisible(False)
        self.preview_activity.setVisible(False)
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
            provider = getattr(worker, "_provider", None)
            cancel = getattr(provider, "request_cancel", None)
            if callable(cancel):
                # This is intentionally non-blocking: waiting for Qwen's model
                # process from the Qt thread caused the Windows "Not Responding"
                # state while the preview was being cancelled.
                cancel()
            self.preview_loading.setVisible(False)
            self.preview_activity.setVisible(False)
            self.preview_status.setText('Stopping preview…')

    def _preview_worker_cancelled(self) -> None:
        self.preview_play_button.setEnabled(False)
        self.preview_stop_button.setEnabled(False)
        self.preview_loading.setValue(0)
        self.preview_status.setText('Preview cancelled.')
        self.status.setText('Voice preview cancelled.')

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
            self.start_button, self.resume_button, self.background_audio_enabled,
            self.background_audio_mode, self.auto_music_style, self.chapter_transition_sound,
            self.story_effects_enabled, self.story_effect_volume,
            self.background_audio_path, self.background_audio_browse,
            self.background_audio_preview, self.background_audio_volume,
            self.ambience_audio_path, self.ambience_audio_browse,
            self.ambience_audio_preview, self.ambience_audio_volume,
            self.background_audio_fade_in, self.background_audio_fade_out,
        ]
        for control in controls:
            control.setEnabled(not locked)
        self._toggle_background_audio_controls(
            self.background_audio_enabled.isChecked() and not locked
        )

    def _repair_empty_chapters_from_source(self) -> bool:
        """Repair empty chapter bodies without replacing manual edits or assignments."""
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
            if not detected:
                return False

            def normalize_title(value: str) -> str:
                return re.sub(r"[\W_]+", "", str(value or "").casefold())

            # Repair only empty chapters. Existing non-empty bodies are user
            # edits and must never be replaced by source text automatically.
            detected_by_title = {
                normalize_title(chapter.title): chapter
                for chapter in detected
                if normalize_title(chapter.title) and str(chapter.text or "").strip()
            }
            detected_by_number = {
                int(chapter.number): chapter
                for chapter in detected
                if str(chapter.text or "").strip()
            }
            changed = False
            for chapter in self.chapters:
                if str(chapter.text or "").strip():
                    continue
                candidate = detected_by_title.get(normalize_title(chapter.title))
                # Source extraction sometimes normalizes or renumbers headings
                # differently from the saved project. If the title does not
                # match, use the corresponding chapter number as a conservative
                # fallback, but only for an empty target chapter.
                if candidate is None:
                    candidate = detected_by_number.get(int(chapter.number))
                if candidate is None and chapter.number == 1 and len(self.chapters) == 1 and len(detected) == 1:
                    candidate = detected[0]
                if candidate is None or not str(candidate.text or "").strip():
                    continue
                chapter.text = candidate.text
                changed = True

            if not changed:
                return False

            # Preserve all fields (including dialogue assignments) and use
            # atomic Project persistence rather than rebuilding chapter JSON.
            chapters_file = self.project_folder / "chapters.json"
            payload = json.loads(chapters_file.read_text(encoding="utf-8"))
            by_number = {int(ch.number): ch for ch in self.chapters}
            for item in payload:
                current = by_number.get(int(item.get("number", 0)))
                if current is not None:
                    item["title"] = current.title
                    item["text"] = current.text
                    item["dialogue_assignments"] = getattr(current, "dialogue_assignments", [])
            temp_file = chapters_file.with_suffix(".json.repair.tmp")
            temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_file.replace(chapters_file)
            self._update_overview()
            self.status.setText("Empty chapter text was restored from the original source; existing edits were preserved.")
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
            or status in {"failed", "cancelled", "generating", "paused"}
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
        assignments = dict(assignments) if isinstance(assignments, dict) else {}
        identity_assignments = state.get("voice_cast_identity_assignments", {}) if isinstance(state, dict) else {}
        if isinstance(identity_assignments, dict) and identity_assignments:
            # Readiness counts the series-scoped assignments instead of losing
            # duplicate names through the legacy name-keyed dictionary.
            assignments = {key: value for key, value in identity_assignments.items() if str(value or "").strip()}
            narrator = (state.get("voice_cast", {}) or {}).get("Narrator") if isinstance(state.get("voice_cast", {}), dict) else None
            if narrator:
                assignments["narrator"] = narrator
        qwen_models_ready = True
        qwen_model_detail = "Required local Qwen model files are present."
        if profile and profile.provider == "qwen-character":
            try:
                from app.tts.qwen_character_runtime import profile_model_readiness
                qwen_models_ready, qwen_model_detail = profile_model_readiness(profile)
            except Exception as exc:
                qwen_models_ready = False
                qwen_model_detail = f"Could not verify the selected Qwen model: {exc}"
        readiness = build_generation_readiness(
            self.chapters,
            profile.name if profile else None,
            provider_name,
            self.output.text().strip() if hasattr(self, "output") else "",
            custom_runtime_ready=runtime_ready(),
            assignments=assignments,
            cover_selected=bool(self.cover),
            qwen_runtime_ready=qwen_runtime_ready(),
            qwen_models_ready=qwen_models_ready,
            qwen_model_detail=qwen_model_detail,
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

        # Try to repair stale/empty chapter records from the original source
        # before readiness gating. The readiness panel must not prevent the
        # repair path from running.
        empty_before_repair = [c for c in self.chapters if not str(c.text or "").strip()]
        if empty_before_repair:
            self._repair_empty_chapters_from_source()

        self._refresh_readiness()
        if not self.start_button.isEnabled():
            self.status.setText("Generation is blocked by the readiness checks above.")
            return

        generation_chapters, skipped_empty_chapters = partition_chapters_by_body(self.chapters)
        if not generation_chapters:
            self.status.setText(
                "Generation stopped: no chapters contain body text. "
                "Repair the source or restore chapter text before generating."
            )
            return

        # Keep the original project chapter list untouched when a stale empty
        # chapter cannot be repaired. Only non-empty chapters are passed to the
        # generator; the readiness panel records which chapter numbers were skipped.
        if skipped_empty_chapters:
            skipped_numbers = ", ".join(str(c.number) for c in skipped_empty_chapters)
            self.status.setText(
                f"Empty chapter(s) {skipped_numbers} will be skipped. "
                "Your original chapter list is preserved."
            )

        output = Path(self.output.text().strip()) if self.output.text().strip() else self._default_output()
        if not output:
            self.status.setText("Choose an M4B output.")
            return

        background_audio_path = None
        ambience_audio_path = None
        background_audio_mode = "off"
        auto_music_style = str(self.auto_music_style.currentData() or "auto")
        chapter_transition_sound = bool(self.chapter_transition_sound.isChecked())
        sound_cue_style = "library"
        opening_cue_path = self.opening_cue_path.text().strip() or None
        page_turn_cue_path = self.page_turn_cue_path.text().strip() or None
        ending_cue_path = self.ending_cue_path.text().strip() or None
        if self.background_audio_enabled.isChecked():
            background_audio_mode = str(self.background_audio_mode.currentData() or "auto")
            if background_audio_mode == "manual":
                selected_music = self.background_audio_path.text().strip()
                selected_ambience = self.ambience_audio_path.text().strip()
                if not selected_music and not selected_ambience:
                    self.status.setText(
                        "Manual background audio is enabled, but no music or ambience track is selected. "
                        "Choose at least one track or switch to Automatic mode."
                    )
                    return
                for label, value in (("Music", selected_music), ("Ambience", selected_ambience)):
                    if value and not Path(value).expanduser().is_file():
                        self.status.setText(
                            f"{label} track was not found: {value}. Choose a valid file or clear that field."
                        )
                        return
                if selected_music:
                    background_audio_path = Path(selected_music).expanduser().resolve()
                if selected_ambience:
                    ambience_audio_path = Path(selected_ambience).expanduser().resolve()
            elif background_audio_mode != "auto":
                self.status.setText("Choose Automatic or Manual background audio, or turn it off.")
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
                "modified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
                "background_audio_enabled": self.background_audio_enabled.isChecked(),
                "background_audio_mode": str(self.background_audio_mode.currentData() or "auto"),
                "auto_music_style": str(self.auto_music_style.currentData() or "auto"),
                "auto_music_track_path": str(self.bgm_variation.currentData() or "auto") if str(self.bgm_variation.currentData() or "auto") != "auto" else "",
                "preview_include_sound_design": self.preview_mix_enabled.isChecked(),
                "chapter_transition_sound": self.chapter_transition_sound.isChecked(),
                "sound_cue_style": "library",
                "opening_cue_path": self.opening_cue_path.text().strip(),
                "page_turn_cue_path": self.page_turn_cue_path.text().strip(),
                "ending_cue_path": self.ending_cue_path.text().strip(),
                "story_effects_enabled": self.story_effects_enabled.isChecked(),
                "story_effect_volume": float(self.story_effect_volume.value()) / 100.0,
                "background_audio_path": self.background_audio_path.text().strip(),
                "background_audio_volume": float(self.background_audio_volume.value()) / 100.0,
                "ambience_audio_path": self.ambience_audio_path.text().strip(),
                "ambience_audio_volume": float(self.ambience_audio_volume.value()) / 100.0,
                "background_audio_fade_in": int(self.background_audio_fade_in.value()),
                "background_audio_fade_out": int(self.background_audio_fade_out.value()),
                "status": "generating",
            })
            save_state(self.project_folder, state)

        self.progress.setRange(0, len(generation_chapters))
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
        self._active_calibration_key = self._generation_calibration_key()
        self._active_calibration_is_resume = bool(is_resume)
        self._update_overview()
        self.timer.start(1000)
        self._set_generation_locked(True)
        self.cancel_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Pause")
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
        selected_bgm_path_value = str(self.bgm_variation.currentData() or "auto")
        self.manager = GenerationManager(
            provider, voice, generation_chapters, self.audio_root,
            on_progress=lambda *args: self.signals.progress.emit(*args),
            on_finished=lambda summary: self.signals.finished.emit(summary),
            pronunciation_dictionary=self._combined_pronunciation_entries(),
            narration_speed=float(self.narration_speed.currentData() or 0.90),
            pacing_profile=self.pacing_profile.currentData() or "natural",
            metadata=metadata,
            bitrate=int(self.audio_bitrate.currentData() or DEFAULT_AUDIO_BITRATE_KBPS),
            background_audio_path=background_audio_path,
            background_audio_volume=float(self.background_audio_volume.value()) / 100.0,
            ambience_audio_path=ambience_audio_path,
            ambience_audio_volume=float(self.ambience_audio_volume.value()) / 100.0,
            background_audio_fade_in=float(self.background_audio_fade_in.value()),
            background_audio_fade_out=float(self.background_audio_fade_out.value()),
            background_audio_mode=background_audio_mode,
            auto_music_style=auto_music_style,
            auto_music_variation=None if selected_bgm_path_value == "auto" else selected_bgm_path_value,
            chapter_transition_sound=chapter_transition_sound,
            story_effects_enabled=self.story_effects_enabled.isChecked(),
            story_effect_volume=float(self.story_effect_volume.value()) / 100.0,
            sound_cue_style=sound_cue_style,
            opening_cue_path=Path(opening_cue_path) if opening_cue_path else None,
            page_turn_cue_path=Path(page_turn_cue_path) if page_turn_cue_path else None,
            ending_cue_path=Path(ending_cue_path) if ending_cue_path else None,
        )
        self.manager.start(
            output,
            self.title.text().strip(),
            self.author.text().strip(),
            self.cover,
            metadata=metadata,
        )

    def toggle_generation_pause(self) -> None:
        if not self.manager:
            return
        if self.manager.pause_event.is_set():
            self.manager.resume()
            self.pause_button.setText("Pause")
            self.status.setText("Resume requested. Generation will continue from the chapter checkpoint.")
            if self.project_folder:
                state = load_state(self.project_folder)
                state["status"] = "generating"
                save_state(self.project_folder, state)
        else:
            self.manager.pause()
            self.pause_button.setText("Resume")
            self.status.setText("Pause requested. The current chapter will finish before generation pauses.")

    def cancel(self) -> None:
        if self.manager:
            self.manager.cancel()
            self.pause_button.setEnabled(False)
            self.status.setText("Stopping generation and releasing the voice engine…")

    def update_progress(self, chapter: int, total: int, done: int, message: str) -> None:
        if message.startswith("paused:"):
            note = message.split(":", 1)[1].strip()
            self.status.setText(note)
            self.stage.setText("Generation paused at a chapter checkpoint")
            self.remaining.setText("Remaining: paused at checkpoint")
            self.pause_button.setText("Resume")
            if self.project_folder:
                state = load_state(self.project_folder)
                state["status"] = "paused"
                save_state(self.project_folder, state)
            return
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
            baseline_rate = None
            # Start with the persisted end-to-end estimate for this voice/settings
            # signature. Live chunk measurements refine it as this book progresses.
            try:
                if self._estimated_generation_seconds > 0:
                    self._eta_ema_sec_per_unit = (
                        self._estimated_generation_seconds / max(1, work_total)
                    )
                else:
                    provider = self.manager.provider if self.manager else None
                    estimated_cpm = float(getattr(provider, "estimated_chars_per_minute", 0) or 0)
                    if estimated_cpm > 0:
                        baseline_rate = estimated_cpm / 60.0
                    self._eta_ema_sec_per_unit = (1.0 / baseline_rate) if baseline_rate else None
            except Exception:
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
                    f"ETA is an initial estimate and will refine after the first segments"
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
                            previous = self._eta_ema_sec_per_unit
                            # Ignore extreme one-sample stalls/spikes; they make
                            # a multi-hour ETA jump from minutes to days.
                            if previous is None or sample <= previous * 4.0:
                                self._eta_rates.append(sample)
                                self._eta_rates = self._eta_rates[-10:]
                                ordered = sorted(self._eta_rates)
                                median = ordered[len(ordered) // 2]
                                self._eta_ema_sec_per_unit = (
                                    median
                                    if previous is None
                                    else (0.18 * median + 0.82 * previous)
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
                f"Remaining: {remaining // 3600:02d}:{(remaining // 60) % 60:02d}:{remaining % 60:02d}"
            )
            units_per_min = 60.0 / max(self._eta_ema_sec_per_unit, 1e-9)
            self.speed.setText(f"Speed: {units_per_min:,.0f} chars/min")
        elif work_done > 0 and elapsed > 8:
            fallback_rate = work_done / elapsed
            remaining = max(0, int(work_remaining / max(fallback_rate, 1e-9)))
            self.remaining.setText(
                f"Remaining: {remaining // 3600:02d}:{(remaining // 60) % 60:02d}:{remaining % 60:02d}"
            )
            self.speed.setText(f"Speed: {fallback_rate * 60:,.0f} chars/min")
        else:
            self.remaining.setText("Remaining: calibrating…")
            self.speed.setText("Speed: calibrating…")

    def finished(self, summary: GenerationSummary) -> None:
        self.timer.stop()
        self.generation_phase = "idle"
        self._set_generation_locked(False)
        self.cancel_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        if self.project_folder:
            state = load_state(self.project_folder)
            state["status"] = "completed" if summary.output_path else ("failed" if (summary.chapters_failed or summary.packaging_failed) else "cancelled")
            state["completed_chapters"] = list(summary.chapters_completed_numbers or [])
            state["failed_chapters"] = summary.chapters_failed
            save_state(self.project_folder, state)

        if summary.output_path:
            calibration_summary = ""
            try:
                if (
                    not self._active_calibration_is_resume
                    and self.started_at is not None
                    and summary.output_path.is_file()
                ):
                    elapsed_seconds = max(1.0, time.monotonic() - self.started_at)
                    listening_seconds = max(1.0, _duration_ms(summary.output_path) / 1000.0)
                    words = max(1, sum(len(chapter.text.split()) for chapter in self.chapters))
                    actual_factor = max(0.4, min(20.0, elapsed_seconds / listening_seconds))
                    seconds_per_word = max(0.05, min(5.0, listening_seconds / words))
                    key = self._active_calibration_key or self._generation_calibration_key()
                    old_factor = self.motion_settings.value(f"{key}/realtime_factor", None)
                    old_word_rate = self.motion_settings.value(f"{key}/seconds_per_word", None)
                    old_samples = int(self.motion_settings.value(f"{key}/samples", 0) or 0)
                    if old_factor is not None and old_samples > 0:
                        actual_factor = 0.35 * actual_factor + 0.65 * float(old_factor)
                    if old_word_rate is not None and old_samples > 0:
                        seconds_per_word = 0.35 * seconds_per_word + 0.65 * float(old_word_rate)
                    self.motion_settings.setValue(f"{key}/realtime_factor", actual_factor)
                    self.motion_settings.setValue(f"{key}/seconds_per_word", seconds_per_word)
                    self.motion_settings.setValue(f"{key}/samples", old_samples + 1)
                    self.motion_settings.sync()
                    self._update_overview()
                    calibration_summary = (
                        f" Timing calibration updated: {elapsed_seconds / 60.0:.1f} min processing / "
                        f"{listening_seconds / 60.0:.1f} min listening."
                    )
            except Exception as exc:
                calibration_summary = f" Timing calibration could not be saved ({exc})."
            self.progress.setValue(self.progress.maximum())
            self.stage.setText("Audiobook ready")
            self.result_label.setText(f"✓ Finished M4B\n{summary.output_path}")
            self.play_button.setEnabled(True)
            self.open_button.setEnabled(True)
            self.status.setText(
                "Audiobook created successfully. Intermediate generation audio has been cleaned."
                + calibration_summary
            )
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
            elapsed = 0
            if self.started_at is not None:
                elapsed = max(0, int(time.monotonic() - self.started_at))
            self.remaining.setText("Remaining: paused at checkpoint")
            self.speed.setText("Speed: checkpoint saved")
            self.elapsed.setText(f"Elapsed: {elapsed // 3600:02d}:{(elapsed // 60) % 60:02d}:{elapsed % 60:02d}")
            self.result_label.setText(
                "Generation failed. Your completed compatible chunks were kept so Resume / Retry "
                "can continue from the checkpoint.\n\n"
                + "\n".join(details)
            )
            self.status.setText("Generation stopped safely. No completed compatible audio was discarded.")
        else:
            self.stage.setText("Generation cancelled")
            self.result_label.setText("Generation cancelled. Temporary files were kept for resume.")
            self.status.setText("No final M4B was created.")
        self._refresh_resume_state()
        self._refresh_readiness()

    def _set_reduce_motion(self, enabled: bool) -> None:
        from PySide6.QtWidgets import QApplication

        self._reduce_motion_enabled = bool(enabled)
        self.motion_settings.setValue("ui/reduce_motion", self._reduce_motion_enabled)
        self.audio_visualizer.set_reduced_motion(self._reduce_motion_enabled)
        # Apply globally, including Voice & Narration and standalone M4B
        # assembly pages that may already exist in the application session.
        for widget in QApplication.allWidgets():
            if isinstance(widget, SmoothProgressBar):
                widget.set_reduced_motion(self._reduce_motion_enabled)

    def _player_playback_state_changed(self, state) -> None:
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        if hasattr(self, "audio_visualizer"):
            self.audio_visualizer.set_playing(is_playing)
        if is_playing:
            self.play_button.setText("Ⅱ  Pause")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.play_button.setText("▶  Resume")
        else:
            self.play_button.setText("▶  Play Audiobook")

    def stop_result(self) -> None:
        self.player.stop()
        self.play_button.setText("▶  Play Audiobook")
        self.audio_visualizer.set_playing(False)

    def play_result(self) -> None:
        path = Path(self.output.text().strip())
        if not path.exists():
            self.status.setText("Final M4B was not found.")
            return
        if self.player.source().toLocalFile() != str(path):
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

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
