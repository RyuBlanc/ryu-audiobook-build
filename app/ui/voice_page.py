from __future__ import annotations

import tempfile
import hashlib
from dataclasses import replace
import re
from pathlib import Path
import webbrowser
import secrets
import wave
import time
import uuid

from PySide6.QtCore import QUrl, QThread, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QInputDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTextEdit, QSpinBox,
    QVBoxLayout, QWidget,
)


class PassiveScrollComboBox(QComboBox):
    """Prevent mouse-wheel changes until the user explicitly opens the combo."""
    
    def wheelEvent(self, event) -> None:
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

from app.ui.motion import SmoothProgressBar
from app.tts.profile_provider import provider_from_profile
from app.tts.preview import build_voice_preview
from app.tts.expression import DEFAULT_VOICE_DESIGN_ANCHOR_TEXT
from app.tts.chatterbox_runtime import runtime_ready, runtime_status
from app.tts.qwen_character_runtime import (
    runtime_ready as qwen_runtime_ready,
    model_installed as qwen_model_installed,
    best_clone_kind,
    best_long_form_clone_kind,
    best_custom_kind,
    best_voice_design_kind,
)
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import (
    VoiceProfile, builtin_voice_profiles, import_reference_audio,
    load_profiles, load_saved_profiles, save_profiles,
)
from app.tts.providers.edge_tts import EdgeTTSProvider
from app.tts.providers.elevenlabs import ElevenLabsProvider


# Keep the longer audition options available; 30 seconds remains the default.
PREVIEW_DURATION_OPTIONS = (10, 20, 30, 45, 60)


class VoicePreviewWorker(QThread):
    finished_ok = Signal(str, float)
    failed = Signal(str)
    cancelled = Signal()
    status = Signal(str)
    progress = Signal(int)

    def __init__(self, profile: VoiceProfile, text: str, output: Path, target_seconds: int = 30):
        super().__init__()
        self.profile = profile
        self.text = text
        self.output = output
        self.target_seconds = max(1, int(target_seconds))
        self.provider = None
        self.cancel_requested = False
        self._progress_floor = 0
        self._preview_started = 0.0

    def _emit_progress(self, value: int) -> int:
        # Coarse phase progress only: Qwen's Base inference does not expose
        # token-level completion, so never invent a smooth percentage.
        self._progress_floor = max(self._progress_floor, min(100, max(0, int(value))))
        self.progress.emit(self._progress_floor)
        return self._progress_floor

    def _status(self, message: str) -> None:
        if not message:
            return
        value = str(message)
        low = value.casefold()
        # These are real worker phase boundaries, not estimates of tokens.
        if "building the saved character identity" in low or "preparing the saved character identity" in low:
            self._emit_progress(30)
        elif "loading cached canonical character identity" in low:
            self._emit_progress(28)
        elif "expression references ready" in low or "loading base clone engine" in low:
            self._emit_progress(42)
        elif "loading qwen model" in low:
            self._emit_progress(18 if self._progress_floor < 30 else 45)
        elif "qwen model loaded" in low:
            self._emit_progress(25 if self._progress_floor < 30 else 50)
        elif (
            "generating natural voicedesign" in low
            or "generating qwen customvoice speech" in low
            or "generating qwen base clone speech" in low
        ):
            self._emit_progress(52)
        if (
            ("processing" in low or "generating" in low)
            and "elapsed" not in low
            and self._preview_started > 0
        ):
            seconds = max(0, int(time.monotonic() - self._preview_started))
            value += f" • elapsed {seconds // 60}:{seconds % 60:02d}"
        self.status.emit(value)

    def run(self) -> None:
        # Measure from worker entry so model startup and provider initialization
        # are included in the final "time taken" displayed to the user.
        preview_started = time.monotonic()
        self._preview_started = preview_started
        self._progress_floor = 0
        try:
            self._emit_progress(5)
            self._status(
                f"[5%] Preparing preview • {self.profile.provider} • "
                f"{self.profile.qwen_mode if self.profile.provider == 'qwen-character' else self.profile.backend}"
            )
            self.provider, voice = provider_from_profile(self.profile)
            callback = getattr(self.provider, "set_status_callback", None)
            if callable(callback):
                callback(self._status)
            self.output.parent.mkdir(parents=True, exist_ok=True)
            if self.cancel_requested:
                self.cancelled.emit()
                return

            self._emit_progress(10)
            self._status("[10%] Voice engine ready • preparing preview segments…")

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
                    label = f"Preparing preview segments • elapsed {fmt_seconds(elapsed)}"
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
                actual_percent = self._emit_progress(percent)
                self._status(f"[{actual_percent}%] {label}")

            build_voice_preview(
                self.text,
                self.provider,
                voice,
                self.output,
                # Preview should represent the default full-generation path,
                # not the old unpaced flat read.
                narration_speed=0.90,
                pacing_profile="natural",
                max_chars=max(1800, len(self.text) + 1),
                progress_callback=preview_progress,
                target_seconds=self.target_seconds,
            )
            if self.cancel_requested:
                self.cancelled.emit()
                return
            if not self.output.exists() or self.output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce valid audio.")
            self._emit_progress(100)
            elapsed_seconds = max(0.0, time.monotonic() - preview_started)
            self._status(f"[100%] Preview ready • generated in {fmt_seconds(elapsed_seconds)}")
            self.finished_ok.emit(str(self.output), elapsed_seconds)
        except Exception as exc:
            if self.cancel_requested:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        finally:
            provider = self.provider
            self.provider = None
            close = getattr(provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def cancel(self) -> None:
        self.cancel_requested = True
        self._status("Stopping preview…")
        provider = self.provider
        cancel = getattr(provider, "request_cancel", None)
        if callable(cancel):
            # Must not call close()/wait() in the Qt thread; Qwen model startup
            # and generation can take minutes on a 4 GB GPU.
            try:
                cancel()
            except Exception:
                pass


class PremiumCharacterVoiceWorker(QThread):
    previews_ready = Signal(object)
    voice_created = Signal(object)
    failed = Signal(str)

    def __init__(self, action: str, payload: dict):
        super().__init__()
        self.action = action
        self.payload = dict(payload or {})

    def run(self) -> None:
        try:
            if self.action == "design":
                previews = ElevenLabsProvider.design_character_voice(
                    style=self.payload.get("style", "anime"),
                    gender=self.payload.get("gender", "female"),
                    age=self.payload.get("age", "young adult"),
                    temperament=self.payload.get("temperament", "expressive"),
                    archetype=self.payload.get("archetype", "heroine"),
                    seed=self.payload.get("seed"),
                )
                self.previews_ready.emit(previews)
            elif self.action == "create":
                result = ElevenLabsProvider.create_designed_voice(
                    generated_voice_id=str(self.payload["generated_voice_id"]),
                    voice_name=str(self.payload["voice_name"]),
                    voice_description=str(self.payload["voice_description"]),
                    style=str(self.payload.get("style", "anime")),
                    gender=str(self.payload.get("gender", "female")),
                    age=str(self.payload.get("age", "young adult")),
                )
                self.voice_created.emit(result)
            else:
                raise RuntimeError(f"Unknown premium character action: {self.action}")
        except Exception as exc:
            self.failed.emit(str(exc))


class VoicePage(QWidget):
    """Offline-first voice library and reusable narration profiles."""

    def __init__(self) -> None:
        super().__init__()
        self.profiles = load_profiles()
        # Keep a draft clone's identity stable between preview and Save. Without
        # this cache, an unsaved clone could preview with UUID A and be saved
        # with UUID B, causing the saved voice to sound different at generation.
        self._draft_qwen_clone_profile_ids: dict[tuple[str, str], str] = {}
        self.sapi = SystemSAPIProvider()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None
        self.last_preview_elapsed_seconds: float | None = None
        self.preview_worker: VoicePreviewWorker | None = None
        self.character_worker: PremiumCharacterVoiceWorker | None = None
        self.character_previews: list[dict] = []
        self.edge_voices: list[dict] = []
        self.premium_voices: list[dict] = []
        self.offline_voices: list[VoiceProfile] = builtin_voice_profiles()

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(self._player_error)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.positionChanged.connect(self._position_changed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(QLabel("<h1>Voice & Narration</h1>"))
        sub = QLabel(
            "Offline neural voices are included with the Windows build. Internet is not required "
            "for the built-in voices, preview, or audiobook generation."
        )
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        title_col.addWidget(sub)
        header.addLayout(title_col, 1)
        self.profile_badge = QLabel("No profile selected")
        self.profile_badge.setObjectName("stat")
        header.addWidget(self.profile_badge)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 2, 4, 18)
        root.setSpacing(14)

        source = QGroupBox("1  •  Voice Library")
        source_layout = QVBoxLayout(source)
        source_layout.addWidget(QLabel(
            "Choose where the voice comes from. Local neural voices are the default."
        ))
        self.mode = PassiveScrollComboBox()
        self.mode.addItem("Offline Neural Voices  ·  built into this app", "offline-neural")
        self.mode.addItem("Qwen3-TTS  ·  CustomVoice", "qwen-custom")
        self.mode.addItem("Qwen3-TTS  ·  VoiceDesign", "qwen-design")
        self.mode.addItem("Qwen3-TTS  ·  Voice Clone", "qwen-clone")
        self.mode.addItem("Windows SAPI  ·  installed offline voices", "windows-sapi")
        self.mode.addItem("Online Neural Voices  ·  Edge TTS", "edge-tts")
        self.mode.addItem("Premium Online Voices  ·  ElevenLabs", "elevenlabs")
        self.mode.addItem("Custom Voice  ·  authorized reference audio", "chatterbox")
        self.mode.currentIndexChanged.connect(self.update_mode)
        source_layout.addWidget(self.mode)
        self.source_hint = QLabel()
        self.source_hint.setObjectName("muted")
        self.source_hint.setWordWrap(True)
        source_layout.addWidget(self.source_hint)

        premium_row = QHBoxLayout()
        self.premium_key_button = QPushButton("Set Premium API Key")
        self.premium_key_button.clicked.connect(self._set_premium_api_key)
        self.premium_key_help_button = QPushButton("Get API Key")
        self.premium_key_help_button.clicked.connect(
            lambda: webbrowser.open("https://elevenlabs.io/app/developers/api-keys")
        )
        self.premium_key_status = QLabel("Premium key: not configured")
        self.premium_key_status.setObjectName("muted")
        premium_row.addWidget(self.premium_key_button)
        premium_row.addWidget(self.premium_key_help_button)
        premium_row.addWidget(self.premium_key_status, 1)
        self.character_box = QGroupBox("Premium Character Voice Studio")
        character = QVBoxLayout(self.character_box)
        character_info = QLabel(
            "Create premium English character voices through ElevenLabs Voice Design. "
            "Anime and cartoon presets generate fresh voice options; you choose one and explicitly "
            "add it to your ElevenLabs library before Ryu's Audiobook uses it for generation."
        )
        character_info.setObjectName("muted")
        character_info.setWordWrap(True)
        character.addWidget(character_info)

        character_filters = QHBoxLayout()
        self.character_style = QComboBox()
        self.character_style.addItem("Anime", "anime")
        self.character_style.addItem("Cartoon", "cartoon")
        self.character_gender = QComboBox()
        self.character_gender.addItems(["Female", "Male", "Neutral"])
        self.character_age = QComboBox()
        self.character_age.addItems(["Child", "Teen", "Young adult", "Adult", "Older adult"])
        self.character_temperament = QComboBox()
        self.character_temperament.addItems([
            "Bright / cheerful",
            "Dramatic / heroic",
            "Mischievous",
            "Warm / friendly",
            "Villain / ominous",
            "Calm / cinematic",
        ])
        self.character_archetype = QComboBox()
        archetypes = [
            ("Anime Heroine", "heroine"),
            ("Anime Hero", "hero"),
            ("Anime Rival", "rival"),
            ("Anime Tsundere", "tsundere"),
            ("Anime Healer", "healer"),
            ("Anime Villain", "villain"),
            ("Anime Mentor", "mentor"),
            ("Anime Chibi", "chibi"),
            ("Anime Sidekick", "sidekick"),
            ("Anime Mysterious", "mysterious"),
            ("Cartoon Hero", "cartoon_hero"),
            ("Cartoon Sidekick", "cartoon_sidekick"),
            ("Cartoon Villain", "cartoon_villain"),
            ("Cartoon Friend", "cartoon_friend"),
        ]
        for label, value in archetypes:
            self.character_archetype.addItem(label, value)
        for label, widget in (
            ("Style", self.character_style),
            ("Archetype", self.character_archetype),
            ("Gender", self.character_gender),
            ("Age", self.character_age),
            ("Temperament", self.character_temperament),
        ):
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            col.addWidget(widget)
            character_filters.addLayout(col, 1)
        character.addLayout(character_filters)

        character_actions = QHBoxLayout()
        self.design_character_button = QPushButton("Generate 3 Premium Character Voices")
        self.design_character_button.setObjectName("primary")
        self.design_character_button.clicked.connect(self.design_character_voices)
        character_actions.addWidget(self.design_character_button)
        self.design_character_more_button = QPushButton("Generate 3 More")
        self.design_character_more_button.clicked.connect(lambda: self.design_character_voices(more=True))
        self.design_character_more_button.setEnabled(False)
        character_actions.addWidget(self.design_character_more_button)
        self.character_preview_selector = QComboBox()
        self.character_preview_selector.addItem("No generated previews", None)
        character_actions.addWidget(self.character_preview_selector, 1)
        self.play_character_button = QPushButton("▶  Play")
        self.play_character_button.setEnabled(False)
        self.play_character_button.clicked.connect(self.play_character_preview)
        character_actions.addWidget(self.play_character_button)
        character.addLayout(character_actions)

        save_character_row = QHBoxLayout()
        self.character_name = QLineEdit()
        self.character_name.setPlaceholderText("e.g. Aiko • Anime Heroine")
        save_character_row.addWidget(self.character_name, 1)
        self.add_character_button = QPushButton("Add Selected to My Voices")
        self.add_character_button.clicked.connect(self.add_selected_character_voice)
        save_character_row.addWidget(self.add_character_button)
        character.addLayout(save_character_row)

        self.character_status = QLabel("No character voice preview generated yet.")
        self.character_status.setObjectName("muted")
        self.character_status.setWordWrap(True)
        character.addWidget(self.character_status)
        root.addWidget(source)

        library_config_box = QGroupBox("2  •  Library Configuration")
        library_config = QVBoxLayout(library_config_box)
        self.install_character_voices_button = QPushButton("Install / Repair Qwen Voice Studio")
        self.install_character_voices_button.clicked.connect(self.open_offline_character_models)
        self.install_character_voices_button.setVisible(False)
        library_config.addWidget(self.install_character_voices_button)
        self.offline_character_status = QLabel()
        self.offline_character_status.setObjectName("muted")
        self.offline_character_status.setWordWrap(True)
        library_config.addWidget(self.offline_character_status)

        premium_row = QHBoxLayout()
        self.premium_key_button = QPushButton("Set Premium API Key")
        self.premium_key_button.clicked.connect(self._set_premium_api_key)
        self.premium_key_help_button = QPushButton("Get API Key")
        self.premium_key_help_button.clicked.connect(
            lambda: webbrowser.open("https://elevenlabs.io/app/developers/api-keys")
        )
        self.premium_key_status = QLabel("Premium key: not configured")
        self.premium_key_status.setObjectName("muted")
        premium_row.addWidget(self.premium_key_button)
        premium_row.addWidget(self.premium_key_help_button)
        premium_row.addWidget(self.premium_key_status, 1)
        library_config.addLayout(premium_row)
        self.premium_key_button.setVisible(False)
        self.premium_key_help_button.setVisible(False)
        self.premium_key_status.setVisible(False)
        library_config.addWidget(self.character_box)

        self.neural_box = QGroupBox("Voice Browser • filters and voice selection")
        neural = QVBoxLayout(self.neural_box)
        row = QHBoxLayout()
        self.language_filter = QComboBox()
        self.language_filter.currentIndexChanged.connect(self._refresh_voice_list)
        self.gender_filter = QComboBox()
        self.gender_filter.addItems(["All", "Female", "Male", "Neutral"])
        self.gender_filter.currentIndexChanged.connect(self._refresh_voice_list)
        self.accent_filter = QComboBox()
        self.accent_filter.currentIndexChanged.connect(self._refresh_voice_list)
        for label, widget, stretch in (
            ("Language", self.language_filter, 2),
            ("Gender", self.gender_filter, 1),
            ("Region / Accent", self.accent_filter, 2),
        ):
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            col.addWidget(widget)
            row.addLayout(col, stretch)
        neural.addLayout(row)
        self.recommended = QLabel("★ Recommended voices appear first")
        self.recommended.setObjectName("muted")
        neural.addWidget(self.recommended)
        voice_row = QHBoxLayout()
        self.neural_voice = QComboBox()
        self.neural_voice.currentIndexChanged.connect(self._neural_voice_changed)
        voice_row.addWidget(self.neural_voice, 1)
        self.refresh_neural = QPushButton("Refresh")
        self.refresh_neural.clicked.connect(self._refresh_voice_source)
        voice_row.addWidget(self.refresh_neural)
        self.neural_count = QLabel("")
        self.neural_count.setObjectName("muted")
        voice_row.addWidget(self.neural_count)
        neural.addLayout(voice_row)
        library_config.addWidget(self.neural_box)

        self.qwen_phase_box = QGroupBox("Qwen3-TTS Voice Studio")
        qwen_phase = QVBoxLayout(self.qwen_phase_box)
        self.qwen_phase_status = QLabel()
        self.qwen_phase_status.setObjectName("muted")
        self.qwen_phase_status.setWordWrap(True)
        qwen_phase.addWidget(self.qwen_phase_status)

        self.qwen_design_box = QGroupBox("VoiceDesign • create a brand-new voice from a description")
        design_layout = QVBoxLayout(self.qwen_design_box)
        design_top = QHBoxLayout()
        design_top.addWidget(QLabel("Preset"))
        self.qwen_design_preset = QComboBox()
        presets = [
            ("Anime Heroine", "Young adult female voice, bright and warm, slightly playful anime heroine timbre, clear natural English diction, expressive emotional reactions, cinematic storytelling, medium-fast pace with soft warmth and controlled breath."),
            ("Anime Hero", "Young adult male voice, confident and dynamic anime protagonist timbre, clear English diction, strong rhythmic drive, heroic energy, expressive but natural emotional changes, cinematic pacing."),
            ("Anime Rival", "Young adult male voice, cool restrained anime rival timbre, slightly husky edge, precise English diction, teasing confidence, controlled intensity and cinematic pauses."),
            ("Anime Villain", "Adult male voice, low mellow theatrical anime villain timbre, elegant menace, controlled authority, slower cinematic pacing, crisp English diction and restrained emotion."),
            ("Anime Healer", "Young adult female voice, gentle warm anime healer timbre, soft breath, reassuring tone, emotionally sincere English narration, calm cinematic pacing and delicate reactions."),
            ("Custom voice description", ""),
        ]
        for label, prompt in presets:
            self.qwen_design_preset.addItem(label, prompt)
        self.qwen_design_preset.currentIndexChanged.connect(self._qwen_design_preset_changed)
        design_top.addWidget(self.qwen_design_preset, 1)
        design_top.addWidget(QLabel("Language"))
        self.qwen_design_language = QComboBox()
        self.qwen_design_language.addItems(["English", "Japanese", "Korean", "Chinese", "German", "French", "Spanish", "Italian", "Portuguese", "Russian"])
        design_top.addWidget(self.qwen_design_language)
        design_layout.addLayout(design_top)
        design_layout.addWidget(QLabel("Voice description"))
        self.qwen_design_prompt = QTextEdit()
        self.qwen_design_prompt.setPlainText(str(self.qwen_design_preset.currentData() or ""))
        self.qwen_design_prompt.setMinimumHeight(88)
        self.qwen_design_prompt.setMaximumHeight(125)
        self.qwen_design_prompt.setPlaceholderText("Describe age, timbre, accent, emotion, energy, pace and cinematic style.")
        design_layout.addWidget(self.qwen_design_prompt)
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("Design seed"))
        self.qwen_design_seed = QSpinBox()
        self.qwen_design_seed.setRange(0, 2147483647)
        self.qwen_design_seed.setValue(0)
        seed_row.addWidget(self.qwen_design_seed)
        seed_row.addWidget(QLabel("0 = natural variation"))
        seed_row.addStretch(1)
        design_layout.addLayout(seed_row)

        design_layout.addWidget(QLabel(
            "VoiceDesign describes the character identity. Use the Preview section below to test it before saving."
        ))
        qwen_phase.addWidget(self.qwen_design_box)

        self.qwen_clone_box = QGroupBox("Voice Clone • authorized reference audio")
        clone_layout = QVBoxLayout(self.qwen_clone_box)
        clone_row = QHBoxLayout()
        self.qwen_clone_sample_button = QPushButton("Choose reference MP3 / WAV / M4A / FLAC…")
        self.qwen_clone_sample_button.clicked.connect(self.select_qwen_clone_sample)
        clone_row.addWidget(self.qwen_clone_sample_button)
        self.qwen_clone_sample_label = QLabel("No reference selected")
        self.qwen_clone_sample_label.setWordWrap(True)
        clone_row.addWidget(self.qwen_clone_sample_label, 1)
        clone_layout.addLayout(clone_row)
        clone_layout.addWidget(QLabel("Reference transcript • recommended for highest-fidelity ICL cloning"))
        self.qwen_reference_text = QLineEdit()
        self.qwen_reference_text.setPlaceholderText("Exact words spoken in the reference. Leave blank for speaker-embedding-only cloning.")
        clone_layout.addWidget(self.qwen_reference_text)
        self.qwen_clone_authorized = QCheckBox("I have permission to use this reference recording.")
        clone_layout.addWidget(self.qwen_clone_authorized)
        self.qwen_clone_hint = QLabel("Qwen Base supports short-reference cloning. An exact transcript enables its ICL mode; blank uses speaker-embedding-only cloning.")
        self.qwen_clone_hint.setObjectName("muted")
        self.qwen_clone_hint.setWordWrap(True)
        clone_layout.addWidget(self.qwen_clone_hint)
        qwen_phase.addWidget(self.qwen_clone_box)

        library_config.addWidget(self.qwen_phase_box)

        # Stage 2 is the library-specific configuration area. It must be
        # attached to the page or none of the voice selectors are visible.
        root.addWidget(library_config_box)

        self.sapi_box = QGroupBox("Windows Voice")
        sapi_layout = QHBoxLayout(self.sapi_box)
        sapi_layout.addWidget(QLabel("Installed voice"))
        self.sapi_voice = QComboBox()
        sapi_layout.addWidget(self.sapi_voice, 1)
        self.sapi_voice.currentIndexChanged.connect(self._sapi_voice_changed)
        library_config.addWidget(self.sapi_box)

        self.custom_box = QGroupBox("Custom Authorized Voice")
        custom = QVBoxLayout(self.custom_box)
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Character style"))
        self.style_preset = QComboBox()
        self.style_preset.addItem("Natural", ("Natural", 0.50, 0.35))
        self.style_preset.addItem("Anime Bright", ("Anime Bright", 0.72, 0.28))
        self.style_preset.addItem("Anime Dramatic", ("Anime Dramatic", 0.62, 0.45))
        self.style_preset.addItem("Cartoon Energetic", ("Cartoon Energetic", 0.85, 0.20))
        self.style_preset.addItem("Warm Storyteller", ("Warm Storyteller", 0.45, 0.42))
        self.style_preset.addItem("Calm / Emotional", ("Calm / Emotional", 0.35, 0.50))
        self.style_preset.setToolTip(
            "Expression presets for the local Chatterbox engine. They shape delivery from your authorized reference voice."
        )
        style_row.addWidget(self.style_preset, 1)
        custom.addLayout(style_row)
        custom_row = QHBoxLayout()
        self.sample_button = QPushButton("Choose MP3 / WAV / M4A / FLAC…")
        self.sample_button.clicked.connect(self.select_sample)
        custom_row.addWidget(self.sample_button)
        self.sample_label = QLabel("No reference selected")
        self.sample_label.setWordWrap(True)
        custom_row.addWidget(self.sample_label, 1)
        custom.addLayout(custom_row)
        self.authorized = QCheckBox("I have permission to use this reference recording.")
        custom.addWidget(self.authorized)
        info = QLabel(
            "The source recording stays local. It is normalized to a local WAV reference "
            "for the voice engine. English custom voices use the faster, expressive "
            "Chatterbox Turbo path automatically on suitable GPUs; low-memory systems "
            "use Nano."
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        custom.addWidget(info)
        self.install_custom_button = QPushButton("Install / Repair Custom Voice Engine")
        self.install_custom_button.clicked.connect(self.open_custom_engine_installer)
        custom.addWidget(self.install_custom_button)
        library_config.addWidget(self.custom_box)

        profile_box = QGroupBox("3  •  Voice Profile")
        profile = QVBoxLayout(profile_box)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Main Narrator")
        form.addRow("Profile name", self.name)
        profile.addLayout(form)

        self.library_filter = QComboBox()
        self.library_filter.addItem("All voices", "all")
        self.library_filter.addItem("Built-in offline", "builtin")
        self.library_filter.addItem("Saved custom", "custom")
        self.library_filter.addItem("Windows", "windows-sapi")
        self.library_filter.addItem("Online", "edge-tts")
        self.library_filter.addItem("Premium Online", "elevenlabs")
        self.library_filter.addItem("Qwen3-TTS", "qwen3-tts")
        self.library_filter.setVisible(False)

        saved_search_row = QHBoxLayout()
        saved_search_row.addWidget(QLabel("Search saved profiles"))
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search by profile, provider, language, voice ID or description…")
        self.library_search.textChanged.connect(self.refresh_profiles)
        saved_search_row.addWidget(self.library_search, 1)
        profile.addLayout(saved_search_row)

        saved_row = QHBoxLayout()
        saved_row.addWidget(QLabel("Voice profiles"))
        self.saved_profiles = QComboBox()
        self.saved_profiles.currentIndexChanged.connect(self._saved_profile_changed)
        saved_row.addWidget(self.saved_profiles, 1)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_selected_profile)
        saved_row.addWidget(self.load_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected_profile)
        saved_row.addWidget(self.delete_button)
        profile.addLayout(saved_row)

        details_box = QGroupBox("Selected Voice Details")
        details = QFormLayout(details_box)
        self.detail_library = QLabel("—")
        self.detail_provider = QLabel("—")
        self.detail_mode = QLabel("—")
        self.detail_voice_id = QLabel("—")
        self.detail_language = QLabel("—")
        self.detail_gender = QLabel("—")
        self.detail_reference = QLabel("—")
        self.detail_backend = QLabel("—")
        self.detail_model = QLabel("—")
        self.detail_seed = QLabel("—")
        self.detail_anchor = QLabel("—")
        self.detail_authorization = QLabel("—")
        self.detail_description = QLabel("—")
        for label, widget in (
            ("Library", self.detail_library),
            ("Provider", self.detail_provider),
            ("Mode", self.detail_mode),
            ("Voice ID", self.detail_voice_id),
            ("Language", self.detail_language),
            ("Gender", self.detail_gender),
            ("Reference", self.detail_reference),
            ("Backend", self.detail_backend),
            ("Model", self.detail_model),
            ("Design seed", self.detail_seed),
            ("Voice anchor", self.detail_anchor),
            ("Authorization", self.detail_authorization),
            ("Description / style", self.detail_description),
        ):
            widget.setWordWrap(True)
            details.addRow(label, widget)
        profile.addWidget(details_box)

        actions = QHBoxLayout()
        self.save_profile_button = QPushButton("Save / Update Profile")
        self.save_profile_button.setObjectName("primary")
        self.save_profile_button.clicked.connect(self.save_profile)
        actions.addWidget(self.save_profile_button)
        actions.addStretch(1)
        profile.addLayout(actions)
        root.addWidget(profile_box)

        preview_box = QGroupBox("4  •  Preview")
        pv = QVBoxLayout(preview_box)

        target_box = QGroupBox("Current Preview Target")
        target_layout = QFormLayout(target_box)
        self.preview_library = QLabel("—")
        self.preview_provider = QLabel("—")
        self.preview_voice = QLabel("—")
        self.preview_model = QLabel("—")
        self.preview_profile = QLabel("—")
        for label, widget in (
            ("Library", self.preview_library),
            ("Provider", self.preview_provider),
            ("Voice", self.preview_voice),
            ("Model", self.preview_model),
            ("Profile", self.preview_profile),
        ):
            widget.setWordWrap(True)
            target_layout.addRow(label, widget)
        pv.addWidget(target_box)

        self.preview_text = QTextEdit()
        self._preview_text_is_auto = True
        self._preview_source_text = ""
        # Start with a full target-length demonstration script, then connect
        # the manual-edit signal. Setting the initial text after connecting
        # textChanged marked the editor as user-edited, which prevented the
        # workflow's selected chapter from replacing this short welcome sample.
        self.preview_text.setPlainText(self._qwen_preview_script(30))
        self.preview_text.textChanged.connect(lambda: setattr(self, "_preview_text_is_auto", False))
        self.preview_text.setMinimumHeight(78)
        self.preview_text.setMaximumHeight(125)
        pv.addWidget(QLabel("Preview text • will be trimmed to the selected preview length"))
        pv.addWidget(self.preview_text)

        settings = QHBoxLayout()
        settings.addWidget(QLabel("Preview length"))
        self.preview_duration = QComboBox()
        for seconds in PREVIEW_DURATION_OPTIONS:
            self.preview_duration.addItem(f"{seconds} seconds", seconds)
        self.preview_duration.setCurrentIndex(2)
        settings.addWidget(self.preview_duration)
        self.preview_engine_status = QLabel("Ready")
        self.preview_engine_status.setObjectName("muted")
        self.preview_engine_status.setWordWrap(True)
        self.preview_percent_bar = SmoothProgressBar()
        self.preview_percent_bar.setRange(0, 100)
        self.preview_percent_bar.setValue(0)
        self.preview_percent_bar.setTextVisible(True)
        self.preview_percent_bar.setFixedHeight(8)
        self.preview_activity_bar = SmoothProgressBar()
        self.preview_activity_bar.setRange(0, 0)
        self.preview_activity_bar.setTextVisible(False)
        self.preview_activity_bar.setFixedHeight(4)
        self.preview_activity_bar.setVisible(False)
        settings.addWidget(self.preview_engine_status, 1)
        pv.addLayout(settings)
        pv.addWidget(self.preview_percent_bar)
        pv.addWidget(self.preview_activity_bar)

        pa = QHBoxLayout()
        self.preview_button = QPushButton("▶  Generate Preview")
        self.preview_button.setObjectName("primary")
        self.preview_button.clicked.connect(self.preview)
        self.play_button = QPushButton("▶  Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_last_preview)
        self.stop_button = QPushButton("■  Stop / Cancel")
        self.stop_button.clicked.connect(self.stop_preview_or_playback)
        pa.addWidget(self.preview_button)
        pa.addWidget(self.play_button)
        pa.addWidget(self.stop_button)
        pa.addStretch(1)
        pv.addLayout(pa)

        progress = QHBoxLayout()
        self.preview_progress = QLabel("0:00 / 0:00")
        progress.addWidget(self.preview_progress)
        progress.addStretch(1)
        self.volume = QComboBox()
        self.volume.addItems(["Volume 50%", "Volume 70%", "Volume 85%", "Volume 100%"])
        self.volume.setCurrentIndex(2)
        self.volume.currentIndexChanged.connect(
            lambda i: self.audio_output.setVolume([0.5, 0.7, 0.85, 1.0][i])
        )
        progress.addWidget(self.volume)
        pv.addLayout(progress)
        root.addWidget(preview_box)

        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        # Recompose the existing four functional sections into the approved
        # HTML-guided workflow. All original controls stay alive; guided mode
        # only hides the inactive step and never discards unsaved selections.
        for widget in (source, library_config_box, profile_box, preview_box, self.status):
            root.removeWidget(widget)
        while root.count():
            root.takeAt(0)
        library_config_box.layout().removeWidget(self.neural_box)

        source.setTitle("1  •  Voice Library")
        library_config_box.setTitle("2  •  Configure Voice")
        profile_box.setTitle("3  •  Voice Profile")
        preview_box.setTitle("4  •  Preview & Assign")

        self.voice_step_pages = []
        step_specs = [
            ("Voice Library", [source, self.neural_box]),
            ("Configure", [library_config_box]),
            ("Voice Profile", [profile_box]),
            ("Preview & Assign", [preview_box]),
        ]
        step_content = QWidget()
        step_root = QVBoxLayout(step_content)
        step_root.setContentsMargins(0, 2, 4, 18)
        step_root.setSpacing(14)
        for index, (_label, widgets) in enumerate(step_specs):
            page = QWidget()
            page.setObjectName(f"voiceStepPage{index + 1}")
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(14)
            for widget in widgets:
                page_layout.addWidget(widget)
            page_layout.addStretch(1)
            self.voice_step_pages.append(page)
            step_root.addWidget(page)

        self.voice_step_index = 0
        step_nav = QHBoxLayout()
        step_nav.setSpacing(8)
        self.voice_step_buttons = []
        for index, (label, _widgets) in enumerate(step_specs):
            button = QPushButton(f"{index + 1:02d}  {label}")
            button.setCheckable(True)
            button.setToolTip(f"Open Voice Studio step {index + 1}: {label}")
            button.clicked.connect(
                lambda checked=False, step=index: self._set_voice_step(step)
            )
            self.voice_step_buttons.append(button)
            step_nav.addWidget(button, 1)
        self.show_all_steps_button = QPushButton("Show All Steps")
        self.show_all_steps_button.setCheckable(True)
        self.show_all_steps_button.setChecked(False)
        self.show_all_steps_button.setToolTip(
            "Toggle between the guided single-step workflow and the full Voice Studio page."
        )
        self.show_all_steps_button.toggled.connect(self._apply_voice_step_visibility)
        step_nav.addWidget(self.show_all_steps_button)
        outer.addLayout(step_nav)

        step_footer = QHBoxLayout()
        self.voice_step_back_button = QPushButton("← Back")
        self.voice_step_back_button.clicked.connect(
            lambda: self._set_voice_step(self.voice_step_index - 1)
        )
        self.voice_step_continue_button = QPushButton("Continue →")
        self.voice_step_continue_button.setObjectName("primary")
        self.voice_step_continue_button.clicked.connect(
            lambda: self._set_voice_step(self.voice_step_index + 1)
        )
        step_footer.addWidget(self.voice_step_back_button)
        step_footer.addStretch(1)
        step_footer.addWidget(self.voice_step_continue_button)
        step_root.addLayout(step_footer)

        self.voice_scroll = scroll
        scroll.setWidget(step_content)
        outer.addWidget(scroll, 1)
        self._apply_voice_step_visibility()

        self._populate_sapi_voices()
        self._update_profile_details(None)
        self.refresh_profiles()
        self._refresh_offline_catalog()
        self.update_mode()

    def _set_voice_step(self, index: int) -> None:
        """Select a Voice Studio step without rebuilding or losing its controls."""
        self.voice_step_index = max(0, min(3, int(index)))
        self._apply_voice_step_visibility()
        if not self.show_all_steps_button.isChecked():
            self.voice_scroll.ensureWidgetVisible(
                self.voice_step_pages[self.voice_step_index]
            )

    def _apply_voice_step_visibility(self, _checked: bool | None = None) -> None:
        """Keep the guided and all-steps views backed by the same live widgets."""
        show_all = self.show_all_steps_button.isChecked()
        for index, page in enumerate(self.voice_step_pages):
            page.setVisible(show_all or index == self.voice_step_index)
        for index, button in enumerate(self.voice_step_buttons):
            button.setChecked(index == self.voice_step_index)
            button.setObjectName("primary" if index == self.voice_step_index else "secondary")
            button.style().unpolish(button)
            button.style().polish(button)
        self.show_all_steps_button.setText("Guided Mode" if show_all else "Show All Steps")
        self.voice_step_back_button.setEnabled(self.voice_step_index > 0)
        self.voice_step_continue_button.setEnabled(self.voice_step_index < 3)
        self.voice_step_continue_button.setText(
            "Preview & Assign →" if self.voice_step_index == 2 else "Continue →"
        )

    @staticmethod
    def _voice_gender(profile: VoiceProfile) -> str:
        voice_id = (profile.voice_id or "").lower()
        if profile.provider == "kokoro":
            prefix = voice_id.split("_", 1)[0]
            if len(prefix) >= 2 and prefix[1] == "f":
                return "Female"
            if len(prefix) >= 2 and prefix[1] == "m":
                return "Male"
            return "Neutral"
        if profile.provider == "qwen-character":
            if voice_id in {"vivian", "serena", "ono_anna", "sohee"}:
                return "Female"
            if voice_id in {"ryan", "aiden", "uncle_fu", "dylan", "eric"}:
                return "Male"
        if "amy" in voice_id:
            return "Female"
        if any(name in voice_id for name in ("lessac", "ryan")):
            return "Male"
        return "Neutral"

    @staticmethod
    def _language_name(value: str) -> str:
        names = {
            "en": "English", "en-US": "English (US)", "en-GB": "English (UK)",
            "en-IN": "English (India)", "ja": "Japanese", "ko": "Korean",
            "zh": "Chinese", "de": "German", "fr": "French", "es": "Spanish",
            "ta": "Tamil", "hi": "Hindi",
        }
        return names.get(value, value.upper())

    def _populate_sapi_voices(self) -> None:
        self.sapi_voice.clear()
        for voice_id in self.sapi.voices():
            self.sapi_voice.addItem(voice_id.rsplit("\\", 1)[-1].replace("_", " "), voice_id)

    def _refresh_offline_catalog(self) -> None:
        self.offline_voices = builtin_voice_profiles()
        self._set_filter_values(self.offline_voices)
        self._refresh_voice_list()

    def _refresh_voice_source(self) -> None:
        mode = self.mode.currentData()
        if mode in {"offline-neural", "qwen-custom"}:
            self._refresh_offline_catalog()
        elif mode == "elevenlabs":
            self._refresh_premium_catalog()
        elif mode == "edge-tts":
            self._refresh_online_catalog()

    def _set_filter_values(self, profiles: list[VoiceProfile]) -> None:
        current_lang = self.language_filter.currentData()
        current_region = self.accent_filter.currentData()
        self.language_filter.blockSignals(True)
        self.accent_filter.blockSignals(True)
        self.language_filter.clear()
        self.language_filter.addItem("All languages", "")
        languages = sorted({(p.language or "en").split("-")[0] for p in profiles})
        for lang in languages:
            self.language_filter.addItem(self._language_name(lang), lang)
        self.accent_filter.clear()
        self.accent_filter.addItem("All regions", "")
        regions = sorted({
            p.voice_id.split("-", 1)[0] if "-" in p.voice_id else (p.language or "en")
            for p in profiles
        })
        for region in regions:
            self.accent_filter.addItem(region, region)
        if current_lang:
            i = self.language_filter.findData(current_lang)
            self.language_filter.setCurrentIndex(i if i >= 0 else 0)
        if current_region:
            i = self.accent_filter.findData(current_region)
            self.accent_filter.setCurrentIndex(i if i >= 0 else 0)
        self.language_filter.blockSignals(False)
        self.accent_filter.blockSignals(False)

    def _qwen_design_preset_changed(self) -> None:
        value = str(self.qwen_design_preset.currentData() or "")
        if value:
            self.qwen_design_prompt.setPlainText(value)

        # Selecting a new preset creates a separate unsaved VoiceDesign draft.
        # Clear the old saved-profile selection to prevent its identity anchor
        # or profile name from appearing active for the new prompt.
        if not hasattr(self, "saved_profiles"):
            return
        selected_name = str(self.saved_profiles.currentData() or "")
        if selected_name:
            self._clear_saved_profile_selection()

        preset_name = str(self.qwen_design_preset.currentText() or "").strip()
        if preset_name and preset_name != "Custom voice description":
            self.name.setText(f"Qwen VoiceDesign • {preset_name}")
            if hasattr(self, "profile_badge"):
                self.profile_badge.setText(f"Unsaved draft • {preset_name}")
        elif preset_name == "Custom voice description":
            if not self.name.text().strip() or self.name.text().strip() == selected_name:
                self.name.setText("Qwen VoiceDesign • Custom Description")
            if hasattr(self, "profile_badge"):
                self.profile_badge.setText("Unsaved VoiceDesign draft")

        if hasattr(self, "status"):
            self.status.setText(
                f"Preset '{preset_name}' selected. Preview this new voice, then save "
                "it as a separate profile; the previously saved voice is unchanged."
            )

    def _refresh_online_catalog(self) -> None:
        if self.mode.currentData() == "elevenlabs":
            self._refresh_premium_catalog()
            return
        try:
            self.edge_voices = EdgeTTSProvider.fetch_voice_metadata(refresh=True) or []
            if not self.edge_voices:
                self.status.setText(
                    "Online catalog could not be refreshed. Offline voices remain fully available."
                )
            self._set_filter_values_edge()
            self._refresh_voice_list()
        except Exception as exc:
            self.status.setText(
                f"Online catalog unavailable: {exc}. Offline voices remain available."
            )

    def design_character_voices(self, more: bool = False) -> None:
        if not ElevenLabsProvider.load_api_key():
            QMessageBox.warning(
                self,
                "Premium Voice Key Required",
                "Set your ElevenLabs API key first. Premium character voice design uses the online ElevenLabs service."
            )
            return
        if self.character_worker is not None and self.character_worker.isRunning():
            return
        if not more:
            self.character_previews = []
            self.character_preview_selector.clear()
        self.character_preview_selector.addItem(
            "Generating 3 more premium previews…" if more else "Generating premium previews…",
            None,
        )
        self.play_character_button.setEnabled(False)
        self.design_character_button.setEnabled(False)
        self.design_character_more_button.setEnabled(False)
        self.add_character_button.setEnabled(False)
        style = str(self.character_style.currentData() or "anime")
        gender = self.character_gender.currentText().casefold()
        age = self.character_age.currentText()
        temperament = self.character_temperament.currentText()
        archetype = str(self.character_archetype.currentData() or "heroine")
        seed = secrets.randbelow(2_147_483_647)
        self.character_status.setText(
            "Generating 3 premium character-voice options… "
            "The service is online; the rest of Ryu's Audiobook remains responsive."
        )
        self.character_worker = PremiumCharacterVoiceWorker(
            "design",
            {
                "style": style,
                "gender": gender,
                "age": age,
                "temperament": temperament,
                "archetype": archetype,
                "seed": seed,
            },
        )
        self.character_worker.previews_ready.connect(self._character_previews_ready)
        self.character_worker.failed.connect(self._character_worker_failed)
        self.character_worker.finished.connect(self._character_worker_finished)
        self.character_worker.start()

    def _character_previews_ready(self, previews: list[dict]) -> None:
        incoming = [dict(item) for item in (previews or []) if isinstance(item, dict)]
        offset = len(self.character_previews)
        for index, preview in enumerate(incoming, 1):
            preview["index"] = offset + index
        self.character_previews.extend(incoming)
        self.character_preview_selector.clear()
        for preview in self.character_previews:
            self.character_preview_selector.addItem(
                f"Preview {preview.get('index', 1)}  · "
                f"{str(preview.get('archetype') or preview.get('style') or 'Character').replace('_', ' ').title()}  · "
                f"{float(preview.get('duration_secs') or 0):.1f}s",
                preview.get("index"),
            )
        if self.character_previews:
            preview = self.character_previews[-len(incoming)] if incoming else self.character_previews[0]
            self.character_preview_selector.setCurrentIndex(
                max(0, self.character_preview_selector.count() - len(incoming))
            )
            style = str(preview.get("style") or "anime").title()
            gender = str(preview.get("gender") or "female").title()
            archetype = str(preview.get("archetype") or "").replace("_", " ").title()
            self.character_name.setText(
                f"{archetype or style + ' ' + gender} Character"
            )
            self.design_character_more_button.setEnabled(True)
            self.character_status.setText(
                f"Now holding {len(self.character_previews)} premium character voice previews. "
                "Play one, then add your selected option to ElevenLabs My Voices."
            )
            self.play_character_button.setEnabled(True)
        else:
            self.character_status.setText("ElevenLabs returned no usable character voice previews.")


    def _character_worker_finished(self) -> None:
        self.design_character_button.setEnabled(True)
        self.design_character_more_button.setEnabled(bool(self.character_previews))
        self.add_character_button.setEnabled(True)
        self.character_worker = None

    def _character_worker_failed(self, message: str) -> None:
        self.character_status.setText(f"Premium character voice operation failed: {message}")
        self.character_preview_selector.clear()
        self.character_preview_selector.addItem("No generated previews", None)
        self.play_character_button.setEnabled(False)

    def _selected_character_preview(self) -> dict | None:
        index = self.character_preview_selector.currentData()
        if index is None:
            return None
        try:
            numeric = int(index)
        except (TypeError, ValueError):
            return None
        return next(
            (preview for preview in self.character_previews if int(preview.get("index", 0)) == numeric),
            None,
        )

    def play_character_preview(self) -> None:
        preview = self._selected_character_preview()
        if not preview:
            self.character_status.setText("Generate a premium character preview first.")
            return
        try:
            import base64
            audio = base64.b64decode(str(preview.get("audio_base_64") or ""))
            output = Path(tempfile.gettempdir()) / f"ryu_character_preview_{preview.get('index', 1)}.mp3"
            output.write_bytes(audio)
            self.last_preview = output
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(output)))
            self.player.play()
            self.play_button.setEnabled(True)
            self.play_button.setText("Ⅱ  Pause")
            self.character_status.setText("Playing the selected premium character preview.")
        except Exception as exc:
            QMessageBox.warning(self, "Character Preview Failed", str(exc))

    def add_selected_character_voice(self) -> None:
        preview = self._selected_character_preview()
        if not preview:
            QMessageBox.warning(
                self,
                "No Character Preview",
                "Generate and select a premium anime or cartoon preview first."
            )
            return
        if not ElevenLabsProvider.load_api_key():
            QMessageBox.warning(
                self,
                "Premium Voice Key Required",
                "Set your ElevenLabs API key first."
            )
            return
        voice_name = self.character_name.text().strip()
        if not voice_name:
            QMessageBox.warning(self, "Voice Name Required", "Enter a name for the premium character voice.")
            return
        if self.character_worker is not None and self.character_worker.isRunning():
            return

        self.add_character_button.setEnabled(False)
        self.design_character_button.setEnabled(False)
        self.character_status.setText("Adding the selected voice to your ElevenLabs My Voices…")
        self.character_worker = PremiumCharacterVoiceWorker(
            "create",
            {
                "generated_voice_id": preview["generated_voice_id"],
                "voice_name": voice_name,
                "voice_description": str(preview.get("description") or "Premium English character voice"),
                "style": str(preview.get("style") or "anime"),
                "gender": str(preview.get("gender") or "female"),
                "age": str(preview.get("age") or "young adult"),
            },
        )
        self.character_worker.voice_created.connect(self._character_voice_created)
        self.character_worker.failed.connect(self._character_worker_failed)
        self.character_worker.finished.connect(self._character_worker_finished)
        self.character_worker.start()

    def _character_voice_created(self, result: dict) -> None:
        voice_id = str(result.get("voice_id") or "").strip()
        if not voice_id:
            self.character_status.setText("ElevenLabs created the voice but returned no voice ID.")
            return
        name = str(result.get("name") or self.character_name.text().strip() or "Premium Character Voice")
        style = str((self._selected_character_preview() or {}).get("style") or "anime")
        gender = str((self._selected_character_preview() or {}).get("gender") or "female")
        profile = VoiceProfile(
            name=name,
            provider="elevenlabs",
            voice_id=voice_id,
            language="en",
            notes=f"Premium {style.title()} character voice • ElevenLabs • {gender.title()}",
            authorized=True,
        )
        profiles = [
            p for p in self.profiles
            if p.name.casefold() != name.casefold()
        ]
        profiles.append(profile)
        save_profiles(profiles)
        self.profiles = profiles
        self.refresh_profiles()
        self.status.setText(
            f"Added premium character voice '{name}' to Ryu's Audiobook. "
            "It is now available as an ElevenLabs voice profile."
        )
        self.character_status.setText(
            f"✓ Added '{name}' to your ElevenLabs My Voices and Ryu's Audiobook."
        )
        self._refresh_premium_catalog()

    def _update_premium_key_status(self) -> None:
        configured = bool(ElevenLabsProvider.load_api_key())
        self.premium_key_status.setText(
            "Premium key: configured" if configured else "Premium key: not configured"
        )

    def _set_premium_api_key(self) -> None:
        current = ElevenLabsProvider.load_api_key()
        value, ok = QInputDialog.getText(
            self,
            "ElevenLabs API Key",
            "Enter your ElevenLabs API key. It is stored locally in the Ryu's Audiobook settings folder:",
            text=current,
            echo=QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        value = value.strip()
        if not value:
            ElevenLabsProvider.clear_api_key()
            self.premium_voices = []
            self._update_premium_key_status()
            self.status.setText("Premium ElevenLabs API key cleared.")
            return
        ElevenLabsProvider.save_api_key(value)
        self.premium_voices = []
        self._update_premium_key_status()
        self.status.setText("Premium ElevenLabs API key saved locally. Refreshing voices…")
        self._refresh_premium_catalog()

    def _refresh_premium_catalog(self) -> None:
        try:
            self.premium_voices = ElevenLabsProvider.fetch_voice_metadata(refresh=True) or []
            if not self.premium_voices:
                self.status.setText(
                    "No ElevenLabs voices were returned. Check the API key and account access."
                )
            else:
                self.status.setText(f"Loaded {len(self.premium_voices)} premium online voices.")
            self._set_filter_values_premium()
            self._refresh_voice_list()
        except Exception as exc:
            self.premium_voices = []
            self.status.setText(f"Premium voice catalog unavailable: {exc}")

    def _set_filter_values_premium(self) -> None:
        current_lang = self.language_filter.currentData()
        current_region = self.accent_filter.currentData()
        self.language_filter.blockSignals(True)
        self.accent_filter.blockSignals(True)
        self.language_filter.clear()
        self.language_filter.addItem("All languages", "")
        languages = sorted({
            str(v.get("language") or "en").split("-", 1)[0]
            for v in self.premium_voices
        })
        for lang in languages:
            self.language_filter.addItem(self._language_name(lang), lang)
        self.accent_filter.clear()
        self.accent_filter.addItem("All accents", "")
        for accent in sorted({
            str(v.get("accent") or "")
            for v in self.premium_voices if v.get("accent")
        }):
            self.accent_filter.addItem(accent, accent)
        if current_lang:
            i = self.language_filter.findData(current_lang)
            self.language_filter.setCurrentIndex(i if i >= 0 else 0)
        if current_region:
            i = self.accent_filter.findData(current_region)
            self.accent_filter.setCurrentIndex(i if i >= 0 else 0)
        self.language_filter.blockSignals(False)
        self.accent_filter.blockSignals(False)

    def _set_filter_values_edge(self) -> None:
        current_lang = self.language_filter.currentData()
        current_region = self.accent_filter.currentData()
        self.language_filter.blockSignals(True)
        self.accent_filter.blockSignals(True)
        self.language_filter.clear()
        self.language_filter.addItem("All languages", "")
        for lang in sorted({
            str(v.get("locale", "")).split("-", 1)[0]
            for v in self.edge_voices if v.get("locale")
        }):
            self.language_filter.addItem(self._language_name(lang), lang)
        self.accent_filter.clear()
        self.accent_filter.addItem("All regions", "")
        for region in sorted({
            str(v.get("locale", "")) for v in self.edge_voices if v.get("locale")
        }):
            self.accent_filter.addItem(region, region)
        if current_lang:
            i = self.language_filter.findData(current_lang)
            self.language_filter.setCurrentIndex(i if i >= 0 else 0)
        if current_region:
            i = self.accent_filter.findData(current_region)
            self.accent_filter.setCurrentIndex(i if i >= 0 else 0)
        self.language_filter.blockSignals(False)
        self.accent_filter.blockSignals(False)

    def _refresh_voice_list(self) -> None:
        if not hasattr(self, "neural_voice"):
            return
        language = self.language_filter.currentData() or ""
        gender = self.gender_filter.currentText()
        region = self.accent_filter.currentData() or ""
        matches = []

        if self.mode.currentData() in {"offline-neural", "qwen-custom"}:
            for profile in self.offline_voices:
                if self.mode.currentData() == "qwen-custom" and profile.provider != "qwen-character":
                    continue
                if self.mode.currentData() == "offline-neural" and profile.provider == "qwen-character":
                    continue
                voice_gender = self._voice_gender(profile)
                lang = (profile.language or "en").split("-")[0]
                reg = profile.voice_id.split("-", 1)[0] if "-" in profile.voice_id else ""
                if language and lang != language:
                    continue
                if gender != "All" and gender != voice_gender:
                    continue
                if region and region != reg:
                    continue
                matches.append((profile, voice_gender, lang, reg))
            matches.sort(key=lambda x: (
                0 if "Recommended" in x[0].notes else 1,
                x[0].name,
            ))
            self.neural_count.setText(f"{len(matches)} offline voices")
            self.neural_voice.clear()
            for profile, voice_gender, _, reg in matches:
                prefix = "★ " if "Recommended" in profile.notes else ""
                self.neural_voice.addItem(
                    f"{prefix}{profile.name.replace('Offline Neural • ', '')}  · "
                    f"{voice_gender}  ·  {reg}",
                    profile.voice_id,
                )
        elif self.mode.currentData() == "elevenlabs":
            for voice in self.premium_voices:
                language_value = str(voice.get("language") or "en")
                voice_gender = str(voice.get("gender") or "Neutral")
                accent = str(voice.get("accent") or "")
                if language and not language_value.lower().startswith(language.lower()):
                    continue
                if region and accent != region:
                    continue
                if gender != "All" and voice_gender != gender:
                    continue
                matches.append(voice)
            self.neural_count.setText(f"{len(matches)} premium voices")
            self.neural_voice.clear()
            for voice in matches:
                self.neural_voice.addItem(
                    f"{voice.get('name') or voice.get('voice_id')}  · "
                    f"{voice.get('language') or 'en'}  · {voice.get('accent') or 'Premium'}",
                    voice.get("voice_id"),
                )
        else:
            for voice in self.edge_voices:
                locale = str(voice.get("locale", ""))
                voice_gender = str(voice.get("gender", "Neutral"))
                if language and not locale.lower().startswith(language.lower() + "-"):
                    continue
                if region and locale != region:
                    continue
                if gender != "All" and voice_gender != gender:
                    continue
                matches.append(voice)
            self.neural_count.setText(f"{len(matches)} online voices")
            self.neural_voice.clear()
            for voice in matches:
                self.neural_voice.addItem(
                    f"{voice.get('friendly_name') or voice.get('name')}  · "
                    f"{voice.get('locale', '')}  · {voice.get('gender', 'Neutral')}",
                    voice.get("name"),
                )

        if not matches:
            self.neural_voice.addItem("No matching voices", None)
        self._neural_voice_changed()

    def _neural_voice_changed(self) -> None:
        voice_id = self.neural_voice.currentData()
        if not voice_id:
            return
        if self.mode.currentData() in {"offline-neural", "qwen-custom"}:
            profile = next(
                (
                    x for x in self.offline_voices
                    if x.voice_id == voice_id
                    and (
                        (self.mode.currentData() == "qwen-custom" and x.provider == "qwen-character")
                        or (self.mode.currentData() == "offline-neural" and x.provider != "qwen-character")
                    )
                ),
                None,
            )
            if profile:
                self.name.setText(profile.name)
                self.profile_badge.setText(profile.name)
                self._update_profile_details(profile)
                self._clear_saved_profile_selection()
        elif self.mode.currentData() == "elevenlabs":
            voice = next(
                (x for x in self.premium_voices if x.get("voice_id") == voice_id), None
            )
            if voice:
                label = voice.get("name") or voice_id
                profile = VoiceProfile(
                    name=label,
                    provider="elevenlabs",
                    voice_id=voice_id,
                    language=voice.get("language") or "en",
                    notes=(
                        "Premium online voice • ElevenLabs. "
                        f"{voice.get('description') or voice.get('use_case') or ''}"
                    ).strip(),
                    authorized=True,
                )
                self.name.setText(label)
                self.profile_badge.setText(label)
                self._update_profile_details(profile)
                self._clear_saved_profile_selection()
        else:
            voice = next(
                (x for x in self.edge_voices if x.get("name") == voice_id), None
            )
            if voice:
                label = voice.get("friendly_name") or voice_id
                profile = VoiceProfile(
                    name=label,
                    provider="edge-tts",
                    voice_id=voice_id,
                    language=voice.get("locale"),
                    authorized=True,
                )
                self.name.setText(label)
                self.profile_badge.setText(label)
                self._update_profile_details(profile)
                self._clear_saved_profile_selection()

    def _sapi_voice_changed(self) -> None:
        if self.mode.currentData() == "windows-sapi" and self.sapi_voice.currentText():
            voice_id = self.sapi_voice.currentData() or self.sapi_voice.currentText()
            label = self.sapi_voice.currentText()
            profile = VoiceProfile(
                name=label,
                provider="windows-sapi",
                voice_id=voice_id,
                authorized=True,
            )
            self.name.setText(label)
            self.profile_badge.setText(label)
            self._update_profile_details(profile)
            self._clear_saved_profile_selection()

    @staticmethod
    def _provider_label(profile: VoiceProfile) -> str:
        labels = {
            "piper": "Built-in Offline Neural • Piper",
            "kokoro": "Built-in Offline Natural • Kokoro",
            "windows-sapi": "Windows SAPI",
            "edge-tts": "Online Neural • Edge TTS",
            "elevenlabs": "Premium Online Natural • ElevenLabs",
            "chatterbox": "Custom Voice • Chatterbox",
            "qwen-character": {
                "custom": "Qwen3-TTS • CustomVoice",
                "design": "Qwen3-TTS • VoiceDesign",
                "clone": "Qwen3-TTS • Voice Clone",
            }.get(profile.qwen_mode or "custom", "Qwen3-TTS"),
        }
        return labels.get(profile.provider, profile.provider)

    @staticmethod
    def _profile_category(profile: VoiceProfile) -> str:
        if profile.provider in {"piper", "kokoro"}:
            return "builtin"
        if profile.provider == "qwen-character":
            return "qwen3-tts"
        return profile.provider

    @staticmethod
    def _reference_label(profile: VoiceProfile) -> str:
        if profile.provider == "qwen-character" and (profile.qwen_mode or "custom") == "clone":
            if not profile.sample_path:
                return "Missing • no Qwen reference recorded"
            path = Path(profile.sample_path)
            if not path.exists():
                return f"Missing • {path.name}"
            suffix = " • ICL transcript saved" if profile.reference_text.strip() else " • speaker embedding mode"
            return f"✓ Local reference • {path.name}{suffix}"
        if profile.provider != "chatterbox":
            return "Not required"
        if not profile.sample_path:
            return "Missing • no reference recorded"
        path = Path(profile.sample_path)
        if not path.exists():
            return f"Missing • {path.name}"
        return f"✓ Local reference • {path.name}"

    def _update_profile_details(self, profile: VoiceProfile | None) -> None:
        fields = (
            "detail_library", "detail_provider", "detail_mode", "detail_voice_id",
            "detail_language", "detail_gender", "detail_reference", "detail_backend",
            "detail_model", "detail_seed", "detail_anchor", "detail_authorization",
            "detail_description",
        )
        if profile is None:
            for field in fields:
                getattr(self, field).setText("—")
            return

        library_labels = {
            "builtin": "Offline Neural",
            "qwen3-tts": "Qwen3-TTS",
            "windows-sapi": "Windows SAPI",
            "edge-tts": "Edge TTS",
            "elevenlabs": "ElevenLabs",
            "chatterbox": "Custom Voice",
        }
        library = library_labels.get(self._profile_category(profile), self._profile_category(profile))
        if profile.provider == "qwen-character":
            mode = {
                "custom": "CustomVoice • reusable speaker",
                "design": "VoiceDesign • design once + Base voice lock",
                "clone": "Voice Clone • authorized reference",
                "design-preview": "VoiceDesign preview",
            }.get(profile.qwen_mode or "custom", "Qwen3-TTS")
        elif profile.provider == "chatterbox":
            mode = profile.style_preset or "Natural"
        elif profile.provider in {"piper", "kokoro"}:
            mode = "Built-in offline"
        else:
            mode = "Standard provider"

        language = profile.language or "Not specified"
        model = profile.model_id or "automatic"
        if profile.provider == "qwen-character" and (profile.qwen_mode or "custom") == "design":
            model = (
                f"VoiceDesign {profile.model_id or 'design-1.7b'} "
                "→ Base model selected in the background for this GPU"
            )

        anchor = "Not used"
        if profile.qwen_anchor_path:
            path = Path(profile.qwen_anchor_path)
            anchor = f"✓ {path.name}" if path.exists() else f"⚠ Missing • {path.name}"

        self.detail_library.setText(library)
        self.detail_provider.setText(self._provider_label(profile))
        self.detail_mode.setText(mode)
        self.detail_voice_id.setText(profile.voice_id or "—")
        self.detail_language.setText(self._language_name(language) if language else "Not specified")
        self.detail_gender.setText(self._voice_gender(profile))
        self.detail_reference.setText(self._reference_label(profile))
        self.detail_backend.setText(profile.backend or "automatic")
        self.detail_model.setText(model)
        self.detail_seed.setText(
            str(profile.qwen_seed) if profile.qwen_seed not in (None, 0) else "Automatic / natural variation"
        )
        self.detail_anchor.setText(anchor)
        self.detail_authorization.setText(
            "✓ Authorized" if profile.authorized else "⚠ Permission not confirmed"
        )
        self.detail_description.setText(profile.qwen_prompt or profile.notes or profile.style_preset or "—")

        if hasattr(self, "style_preset") and profile.provider == "chatterbox":
            idx = self.style_preset.findData(
                (profile.style_preset or "Natural", float(profile.exaggeration), float(profile.cfg_weight))
            )
            if idx >= 0:
                self.style_preset.setCurrentIndex(idx)

    def _clear_saved_profile_selection(self) -> None:
        if not hasattr(self, "saved_profiles"):
            return
        self.saved_profiles.blockSignals(True)
        self.saved_profiles.setCurrentIndex(-1)
        self.saved_profiles.blockSignals(False)

    def refresh_profiles(self) -> None:
        self.profiles = load_profiles()
        current = self.saved_profiles.currentData() if hasattr(self, "saved_profiles") else None
        category = self.library_filter.currentData() if hasattr(self, "library_filter") else "all"
        query = self.library_search.text().strip().casefold() if hasattr(self, "library_search") else ""
        self.saved_profiles.blockSignals(True)
        self.saved_profiles.clear()

        matches = []
        for profile in self.profiles:
            profile_category = self._profile_category(profile)
            if category not in {"all", profile_category}:
                continue
            searchable = " ".join(
                (
                    profile.name,
                    profile.voice_id,
                    profile.provider,
                    profile.language or "",
                    profile.notes or "",
                )
            ).casefold()
            if query and query not in searchable:
                continue
            matches.append(profile)

        for profile in matches:
            label = f"{profile.name}  ·  {self._provider_label(profile)}"
            self.saved_profiles.addItem(label, profile.name)

        selected_index = -1
        if current:
            selected_index = self.saved_profiles.findData(current)
        if selected_index >= 0:
            self.saved_profiles.setCurrentIndex(selected_index)
        elif self.saved_profiles.count():
            self.saved_profiles.setCurrentIndex(0)

        self.saved_profiles.blockSignals(False)
        self._saved_profile_changed()

    def _saved_profile_changed(self) -> None:
        # Selecting a saved profile must make it the active profile, not just
        # change the badge. This is especially important for custom Chatterbox
        # profiles because the provider and reference audio live in the profile.
        if self.saved_profiles.currentData():
            self.load_selected_profile()

    def load_selected_profile(self) -> None:
        name = self.saved_profiles.currentData()
        profile = next((p for p in self.profiles if p.name == name), None)
        if not profile:
            self.status.setText("Select a saved profile first.")
            return

        if profile.provider in {"piper", "kokoro"}:
            source_provider = "offline-neural"
        elif profile.provider == "qwen-character":
            source_provider = {
                "custom": "qwen-custom",
                "design": "qwen-design",
                "clone": "qwen-clone",
            }.get(profile.qwen_mode or "custom", "qwen-custom")
        else:
            source_provider = profile.provider
        index = self.mode.findData(source_provider)
        if index >= 0:
            self.mode.setCurrentIndex(index)
        self.name.setText(profile.name)
        self.authorized.setChecked(profile.authorized)
        self.sample_path = Path(profile.sample_path) if profile.sample_path else None
        if self.sample_path and self.sample_path.exists():
            self.sample_label.setText(f"✓ {self.sample_path.name}")
        elif profile.provider == "chatterbox":
            self.sample_label.setText("⚠ Saved reference audio is missing from this PC.")

        if profile.provider == "qwen-character":
            self.qwen_design_prompt.setPlainText(
                (profile.qwen_prompt or profile.notes).replace("Qwen VoiceDesign • ", "")
            )
            if profile.qwen_seed:
                self.qwen_design_seed.setValue(int(profile.qwen_seed))
            self.qwen_reference_text.setText(profile.reference_text or "")
            self.qwen_clone_authorized.setChecked(profile.authorized)
            if self.sample_path and self.sample_path.exists():
                self.qwen_clone_sample_label.setText(f"✓ {self.sample_path.name}")

        if profile.provider == "windows-sapi":
            i = self.sapi_voice.findData(profile.voice_id)
            if i >= 0:
                self.sapi_voice.setCurrentIndex(i)
        elif profile.provider in {"piper", "kokoro", "edge-tts"} or (
            profile.provider == "qwen-character" and (profile.qwen_mode or "custom") == "custom"
        ):
            self._refresh_voice_list()
            i = self.neural_voice.findData(profile.voice_id)
            if i >= 0:
                self.neural_voice.setCurrentIndex(i)

        self.profile_badge.setText(profile.name)
        self._update_profile_details(profile)
        provider_label = self._provider_label(profile)
        reference = self._reference_label(profile)
        self.status.setText(
            f"Loaded voice profile: {profile.name} • {provider_label} • {reference}"
        )

    def delete_selected_profile(self) -> None:
        name = self.saved_profiles.currentData()
        profile = next((p for p in self.profiles if p.name == name), None)
        if not profile or profile.provider in {"piper", "kokoro"}:
            return
        if QMessageBox.question(
            self, "Delete Voice Profile", f"Delete '{name}'?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.profiles = [p for p in self.profiles if p.name != name]
        save_profiles(self.profiles)
        self.refresh_profiles()
        self.status.setText(f"Deleted voice profile: {name}")

    def open_offline_character_models(self) -> None:
        window = self.window()
        if hasattr(window, "select_section"):
            window.select_section("Models")
            self.status.setText(
                "Models opened. Choose the Qwen3-TTS phase to install: CustomVoice, VoiceDesign, Voice Clone, or Full Voice Studio."
            )
        else:
            self.status.setText(
                "Open Models → Install Qwen Voice Studio and choose the Qwen3-TTS phase you need."
            )

    def open_custom_engine_installer(self) -> None:
        window = self.window()
        if hasattr(window, "select_section"):
            window.select_section("Models")
            self.status.setText(
                "Models opened. Click Install / Repair Custom Voice Engine to install the local cloning runtime."
            )
        else:
            self.status.setText(
                "Open Models → Install / Repair Custom Voice Engine to install the local cloning runtime."
            )

    def update_mode(self) -> None:
        mode = self.mode.currentData()
        premium_visible = mode == "elevenlabs"
        self.premium_key_button.setVisible(premium_visible)
        self.premium_key_help_button.setVisible(premium_visible)
        self.premium_key_status.setVisible(premium_visible)
        self.character_box.setVisible(premium_visible)

        qwen_visible = mode in {"qwen-custom", "qwen-design", "qwen-clone"}
        self.install_character_voices_button.setVisible(qwen_visible)
        self.qwen_phase_box.setVisible(qwen_visible)
        self.qwen_design_box.setVisible(mode == "qwen-design")
        self.qwen_clone_box.setVisible(mode == "qwen-clone")
        self.neural_box.setVisible(mode in {"offline-neural", "qwen-custom", "edge-tts", "elevenlabs"})
        self.sapi_box.setVisible(mode == "windows-sapi")
        self.custom_box.setVisible(mode == "chatterbox")

        if mode == "offline-neural":
            self.source_hint.setText(
                "Built-in local neural voices. No internet connection is used for preview or generation."
            )
            self._refresh_offline_catalog()
            self._set_filter_values([
                profile for profile in self.offline_voices
                if profile.provider != "qwen-character"
            ])
            self._refresh_voice_list()

        elif mode == "qwen-custom":
            self._refresh_offline_catalog()
            qwen_profiles = [
                profile for profile in self.offline_voices
                if profile.provider == "qwen-character"
                and (profile.qwen_mode or "custom") == "custom"
            ]
            self._set_filter_values(qwen_profiles)
            self._refresh_voice_list()
            ready = qwen_runtime_ready()
            # UI status must not start nvidia-smi. Use a conservative fast
            # filesystem-only choice here; the provider makes the true GPU-aware
            # choice in its worker thread before generation.
            kind = best_custom_kind(vram_gb=0.0)
            installed = ready and qwen_model_installed(kind)
            self.source_hint.setText(
                "Qwen3-TTS CustomVoice • reusable named speakers with local style instructions on the 1.7B path. "
                "Ryan and Aiden are the native-English Qwen speakers."
            )
            self.offline_character_status.setText(
                f"{'✓' if installed else '○'} CustomVoice model: {kind} • "
                + ("ready" if installed else "not installed")
            )
            self.qwen_phase_status.setText(
                "Phase 1 • CustomVoice — stable reusable speakers. The 1.7B model is the quality path."
            )

        elif mode == "qwen-design":
            current_name = self.name.text().strip()
            if not current_name or current_name.startswith("Offline Character"):
                preset_name = self.qwen_design_preset.currentText()
                self.name.setText(
                    "Qwen VoiceDesign • " + (
                        "Custom Description"
                        if preset_name == "Custom voice description"
                        else preset_name
                    )
                )
            ready = qwen_runtime_ready()
            design_installed = ready and qwen_model_installed(best_voice_design_kind())
            installed = design_installed
            self.source_hint.setText(
                "Qwen3-TTS VoiceDesign • the same VoiceDesign engine is used for preview and audiobook narration, keeping the selected voice identity and expression consistent."
            )
            self.offline_character_status.setText(
                f"{'✓' if installed else '○'} VoiceDesign model • "
                + ("ready" if installed else "not installed")
            )
            self.qwen_phase_status.setText(
                "Phase 2 • VoiceDesign — ideal for anime heroines, heroes, villains, narrators and cinematic character voices. "
                "On 4GB GPUs it may fall back to CPU."
            )

        elif mode == "qwen-clone":
            ready = qwen_runtime_ready()
            # Keep hardware detection out of the Qt event loop.
            kind = best_clone_kind(vram_gb=0.0)
            installed = ready and qwen_model_installed(kind)
            self.source_hint.setText(
                "Qwen3-TTS Base • authorized voice cloning from a short local reference recording."
            )
            self.offline_character_status.setText(
                f"{'✓' if installed else '○'} Clone model: {kind} • "
                + ("ready" if installed else "not installed")
            )
            self.qwen_phase_status.setText(
                "Phase 3 • Voice Clone — provide the exact reference transcript for Qwen's higher-fidelity ICL mode."
            )

        elif mode == "edge-tts":
            self.source_hint.setText(
                "Microsoft Edge online neural catalog. Internet is required for synthesis."
            )
            if not self.edge_voices:
                self._refresh_online_catalog()
            else:
                self._set_filter_values_edge()
                self._refresh_voice_list()

        elif mode == "elevenlabs":
            self.source_hint.setText(
                "Premium online natural voices powered by ElevenLabs. Internet and a personal API key are required. "
                "The key stays local and is never bundled with Ryu's Audiobook."
            )
            self._update_premium_key_status()
            if ElevenLabsProvider.load_api_key():
                if not self.premium_voices:
                    self._refresh_premium_catalog()
                else:
                    self._set_filter_values_premium()
                    self._refresh_voice_list()

        elif mode == "windows-sapi":
            self.source_hint.setText("Uses voices already installed in Windows. Fully offline.")

        else:
            self.source_hint.setText(
                "Use only a reference recording you are authorized to use. The reference remains local. "
                f"Custom voice engine: {runtime_status()}. Install or repair it from Models before preview/generation."
            )

    def select_qwen_clone_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Qwen Clone Reference",
            "",
            "Audio (*.wav *.mp3 *.m4a *.flac *.aac *.ogg *.opus *.wma);;All files (*.*)",
        )
        if not path:
            return
        source = Path(path)
        name = self.name.text().strip() or source.stem
        try:
            idx = self.mode.findData("qwen-clone")
            if idx >= 0:
                self.mode.setCurrentIndex(idx)
            self.sample_path = import_reference_audio(source, name, minimum_seconds=3.0)
            self.qwen_clone_sample_label.setText(
                f"✓ {source.name} → {self.sample_path.name}"
            )
            self.name.setText(name)
            self.qwen_clone_authorized.setChecked(False)
            self._clear_saved_profile_selection()
            self.status.setText(
                "Qwen clone reference imported locally. Add the exact transcript and confirm permission before saving."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Qwen Clone Import Failed", str(exc))

    def select_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Voice",
            "",
            "Audio (*.wav *.mp3 *.m4a *.flac *.aac *.ogg *.opus *.wma);;All files (*.*)",
        )
        if not path:
            return
        source = Path(path)
        name = self.name.text().strip()
        if (
            not name
            or name.startswith("Offline Neural •")
            or name.startswith("Microsoft ")
        ):
            name = source.stem
        try:
            # Importing a reference is an explicit switch to the custom voice
            # workflow. This prevents the previous Piper/Edge selection from
            # remaining the active provider while a custom sample is displayed.
            custom_index = self.mode.findData("chatterbox")
            if custom_index >= 0:
                self.mode.setCurrentIndex(custom_index)
            self.sample_path = import_reference_audio(source, name)
            self.sample_label.setText(
                f"✓ {source.name} → {self.sample_path.name}"
            )
            # Do not inherit a previous built-in/online profile name when the
            # user selects a reference file. That used to save a custom voice
            # under names such as "Offline Neural • Lessac", which then collided
            # with the bundled profile and made the custom voice appear missing.
            self.name.setText(name)
            self.authorized.setChecked(False)
            draft = VoiceProfile(
                name=name,
                provider="chatterbox",
                voice_id=self.sample_path.stem,
                sample_path=str(self.sample_path),
                model_id="chatterbox-turbo",
                backend="automatic",
                language="en",
                authorized=False,
                style_preset="Natural",
                exaggeration=0.50,
                cfg_weight=0.35,
            )
            self._update_profile_details(draft)
            self._clear_saved_profile_selection()
            self.status.setText(
                "Reference imported locally. Confirm permission before saving. "
                f"Custom voice profile name: {self.name.text().strip()}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Voice Import Failed", str(exc))

    def _stable_qwen_design_profile_id(
        self,
        name: str,
        prompt: str,
        language: str,
        seed: int,
        anchor_text: str,
    ) -> str:
        """Reuse the saved identity for unchanged settings; derive a stable ID for edits.

        The anchor cache is keyed by this ID. A random ID for every preview
        would re-design the same character repeatedly and could change its
        timbre/gender between the Voice Studio and Generate screens.
        """
        saved_name = self.saved_profiles.currentData() if hasattr(self, "saved_profiles") else None
        saved = next(
            (
                item for item in load_saved_profiles()
                if item.provider == "qwen-character"
                and item.qwen_mode == "design"
                and item.name.casefold() == str(name).casefold()
            ),
            None,
        )
        if saved and saved.qwen_profile_id and saved.name == saved_name:
            saved_prompt = (saved.qwen_prompt or saved.notes).replace("Qwen VoiceDesign • ", "")
            if (
                saved_prompt.strip() == prompt.strip()
                and (saved.language or "English") == language
                and int(saved.qwen_seed or 3101) == int(seed or 3101)
                and (saved.qwen_anchor_text or anchor_text) == anchor_text
            ):
                return saved.qwen_profile_id

        identity = "\\0".join(
            (
                str(name).strip().casefold(),
                str(language).strip().casefold(),
                str(prompt).strip(),
                str(int(seed or 3101)),
                str(anchor_text).strip(),
                "qwen-design-profile-v2",
            )
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    def _stable_qwen_clone_profile_id(
        self, clone_name: str, sample_path: Path, reference_text: str
    ) -> str:
        """Reuse a saved or draft clone identity across preview and profile save."""
        selected_name = str(self.saved_profiles.currentData() or "")
        resolved_sample = str(Path(sample_path).expanduser().resolve())
        existing_clone = next(
            (
                profile for profile in self.profiles
                if profile.provider == "qwen-character"
                and (profile.qwen_mode or "custom") == "clone"
                and profile.name.casefold()
                in {selected_name.casefold(), clone_name.casefold()}
                and profile.sample_path
                and str(Path(profile.sample_path).expanduser().resolve()) == resolved_sample
            ),
            None,
        )
        if existing_clone and existing_clone.qwen_profile_id:
            return existing_clone.qwen_profile_id

        draft_key = (resolved_sample, str(reference_text or "").strip())
        if draft_key not in self._draft_qwen_clone_profile_ids:
            self._draft_qwen_clone_profile_ids[draft_key] = uuid.uuid4().hex
        return self._draft_qwen_clone_profile_ids[draft_key]

    def _profile_from_ui(self) -> VoiceProfile | None:
        provider = self.mode.currentData()
        name = self.name.text().strip()

        if provider == "qwen-custom":
            voice_id = self.neural_voice.currentData()
            profile = next(
                (
                    x for x in self.offline_voices
                    if x.provider == "qwen-character"
                    and x.voice_id == voice_id
                    and (x.qwen_mode or "custom") == "custom"
                ),
                None,
            )
            if not profile:
                self.status.setText("Select a Qwen CustomVoice speaker first.")
                return None
            return VoiceProfile(
                name=name or profile.name,
                provider="qwen-character",
                voice_id=profile.voice_id,
                model_id=profile.model_id,
                backend="automatic",
                language=profile.language,
                notes=profile.notes,
                authorized=True,
                qwen_mode="custom",
                qwen_prompt=profile.qwen_prompt or profile.notes,
                qwen_seed=profile.qwen_seed,
            )

        if provider == "qwen-design":
            prompt = self.qwen_design_prompt.toPlainText().strip()
            if not prompt:
                self.status.setText("Describe the Qwen VoiceDesign voice first.")
                return None
            design_name = name or "Qwen VoiceDesign Voice"
            safe_id = "".join(
                c.lower() if c.isalnum() else "-"
                for c in design_name
            ).strip("-")[:50]
            seed = int(self.qwen_design_seed.value()) or 3101
            language = self.qwen_design_language.currentText()
            anchor_text = DEFAULT_VOICE_DESIGN_ANCHOR_TEXT
            profile_id = self._stable_qwen_design_profile_id(
                design_name, prompt, language, seed, anchor_text
            )
            return VoiceProfile(
                name=design_name,
                provider="qwen-character",
                voice_id=f"design-{safe_id or 'voice'}",
                model_id="design-1.7b",
                backend="automatic",
                language=language,
                notes=f"Qwen VoiceDesign • {prompt}",
                authorized=True,
                qwen_mode="design",
                qwen_prompt=prompt,
                qwen_seed=seed,
                qwen_anchor_text=anchor_text,
                qwen_profile_id=profile_id,
            )

        if provider == "qwen-clone":
            if not self.sample_path or not self.sample_path.exists():
                self.status.setText("Choose an authorized Qwen clone reference first.")
                return None
            if not self.qwen_clone_authorized.isChecked():
                self.status.setText("Confirm that you have permission to use this voice reference.")
                return None
            clone_name = name or self.sample_path.stem
            profile_id = self._stable_qwen_clone_profile_id(
                clone_name,
                self.sample_path,
                self.qwen_reference_text.text(),
            )
            return VoiceProfile(
                name=clone_name,
                provider="qwen-character",
                voice_id=self.sample_path.stem,
                sample_path=str(self.sample_path),
                model_id="auto",
                backend="automatic",
                language="English",
                authorized=True,
                qwen_mode="clone",
                reference_text=self.qwen_reference_text.text().strip(),
                qwen_profile_id=profile_id,
            )

        if provider == "offline-neural":
            voice_id = self.neural_voice.currentData()
            profile = next(
                (
                    x for x in self.offline_voices
                    if x.voice_id == voice_id and x.provider != "qwen-character"
                ),
                None,
            )
            if not profile:
                self.status.setText("Select an offline neural voice first.")
                return None
            return VoiceProfile(
                name=name or profile.name,
                provider=profile.provider,
                voice_id=profile.voice_id,
                model_id=profile.model_id,
                backend=profile.backend,
                language=profile.language,
                notes=profile.notes,
                authorized=profile.authorized,
            )

        if provider == "windows-sapi":
            voice_id = self.sapi_voice.currentData()
            if not voice_id:
                self.status.setText("No Windows voice is available.")
                return None
            return VoiceProfile(
                name=name or self.sapi_voice.currentText(),
                provider=provider,
                voice_id=voice_id,
                authorized=True,
            )

        if provider == "edge-tts":
            voice_id = self.neural_voice.currentData()
            voice = next(
                (x for x in self.edge_voices if x.get("name") == voice_id), None
            )
            if not voice:
                self.status.setText("Select an online neural voice first.")
                return None
            return VoiceProfile(
                name=name or voice.get("friendly_name") or voice_id,
                provider=provider,
                voice_id=voice_id,
                language=voice.get("locale"),
                authorized=True,
            )

        if provider == "elevenlabs":
            voice_id = self.neural_voice.currentData()
            voice = next(
                (x for x in self.premium_voices if x.get("voice_id") == voice_id), None
            )
            if not voice:
                self.status.setText("Select a premium online voice first.")
                return None
            return VoiceProfile(
                name=name or voice.get("name") or voice_id,
                provider=provider,
                voice_id=voice_id,
                language=voice.get("language") or "en",
                notes=(
                    "Premium online voice • ElevenLabs. "
                    f"{voice.get('description') or voice.get('use_case') or ''}"
                ).strip(),
                authorized=True,
            )

        if not self.sample_path or not self.sample_path.exists():
            self.status.setText("Choose a reference audio file first, or load a custom profile with a valid local reference.")
            return None
        if not self.authorized.isChecked():
            self.status.setText("Confirm that you have permission to use this voice.")
            return None
        custom_name = name or self.sample_path.stem
        preset = self.style_preset.currentData() if hasattr(self, "style_preset") else ("Natural", 0.50, 0.35)
        return VoiceProfile(
            name=custom_name,
            provider="chatterbox",
            voice_id=self.sample_path.stem,
            sample_path=str(self.sample_path),
            model_id="chatterbox-turbo",
            backend="automatic",
            language="en",
            authorized=True,
            style_preset=str(preset[0]),
            exaggeration=float(preset[1]),
            cfg_weight=float(preset[2]),
        )

    @staticmethod
    def _qwen_preview_script(seconds: int) -> str:
        script = (
            "Welcome to Ryu's Audiobook. "
            "Tonight, the world is quieter than usual, and every small sound seems to carry a meaning. "
            "The speaker pauses, takes a calm breath, and continues with confidence. "
            "Some moments should feel warm and gentle, while others should carry a little tension, curiosity, or wonder. "
            "The important thing is that the voice remains recognizable and natural from one sentence to the next. "
            "This short sample is only a voice test, designed to let you hear the character clearly before you save the profile. "
            "Thank you for listening, and welcome to the story."
        )
        target_words = max(25, int(seconds * 2.4))
        words = script.split()
        if len(words) >= target_words:
            return " ".join(words[:target_words])
        output = []
        while len(output) < target_words:
            output.extend(words)
        return " ".join(output[:target_words])

    @staticmethod
    def _preview_text_for_duration(text: str, seconds: int) -> str:
        words = text.split()
        if not words:
            return ""
        # Supply enough source text to reach the requested duration. The
        # preview renderer stops on actual audio duration, so this is only a
        # safety margin rather than a fixed word-count target.
        max_words = max(24, int(seconds * 14.0))
        if len(words) <= max_words:
            return text.strip()
        shortened = " ".join(words[:max_words]).strip()
        matches = list(re.finditer(r"[.!?…](?=\s|$)", shortened))
        if matches:
            return shortened[:matches[-1].end()].strip()
        return shortened + "…"

    def test_qwen_design_voice(self) -> None:
        if self.mode.currentData() != "qwen-design":
            index = self.mode.findData("qwen-design")
            if index >= 0:
                self.mode.setCurrentIndex(index)
        self.preview()

    def set_preview_source(self, text: str, title: str = "") -> None:
        """Load chapter text for duration-targeted voice previews."""
        value = str(text or "").strip()
        if not value:
            return
        self._preview_source_text = value
        self._preview_source_title = title or ""
        if getattr(self, "_preview_text_is_auto", True):
            self.preview_text.blockSignals(True)
            self.preview_text.setPlainText(value[:20000])
            self.preview_text.blockSignals(False)
            self._preview_text_is_auto = True

    def preview(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return

        seconds = int(self.preview_duration.currentData() or 30)
        raw_text = self.preview_text.toPlainText().strip()
        if getattr(self, "_preview_text_is_auto", False) and getattr(self, "_preview_source_text", ""):
            raw_text = self._preview_source_text
        if not raw_text:
            raw_text = self._qwen_preview_script(seconds)
        text = self._preview_text_for_duration(raw_text, seconds)
        if not text:
            self.status.setText("Enter preview text first.")
            return

        preview_profile = profile
        preview_library = self._provider_label(profile)
        preview_model = profile.model_id or "automatic"

        if profile.provider == "qwen-character":
            from app.tts.qwen_character_runtime import (
                runtime_ready, model_installed,
                best_custom_kind, best_clone_kind, best_voice_design_kind,
            )
            if not runtime_ready():
                QMessageBox.warning(
                    self,
                    "Qwen3-TTS Not Ready",
                    "Open Models and install the Qwen3-TTS local runtime first.",
                )
                return

            if profile.qwen_mode == "design":
                # Preview and audiobook use the same stable Design -> Base
                # identity pipeline so the selected voice is trustworthy.
                kind = best_voice_design_kind()
                if not model_installed(kind):
                    QMessageBox.warning(
                        self,
                        "Qwen VoiceDesign Not Ready",
                        "Install the Qwen VoiceDesign model from Models first.",
                    )
                    return
                # This check must remain instant on the UI thread. Actual
                # model choice is recalculated in the Qwen worker using VRAM.
                base_kind = best_long_form_clone_kind(vram_gb=0.0)
                if not qwen_model_installed(base_kind):
                    QMessageBox.warning(
                        self,
                        "Qwen Stable Voice Model Not Ready",
                        f"VoiceDesign preview and audiobook require the local Qwen Base model ({base_kind}) "
                        "for consistent character identity. Open Models and install that Base phase.",
                    )
                    return
                preview_profile = replace(
                    profile,
                    qwen_mode="design",
                    model_id=kind,
                )
                preview_model = f"{kind} • VoiceDesign • stable identity preview"
            elif profile.qwen_mode == "clone":
                kind = best_clone_kind(vram_gb=0.0)
                if not model_installed(kind):
                    QMessageBox.warning(
                        self,
                        "Qwen Voice Clone Not Ready",
                        f"Install the Qwen Base model ({kind}) from Models first.",
                    )
                    return
                preview_model = f"{kind} • Base voice clone"
            else:
                kind = best_custom_kind(vram_gb=0.0)
                if not model_installed(kind):
                    QMessageBox.warning(
                        self,
                        "Qwen CustomVoice Not Ready",
                        f"Install the Qwen CustomVoice model ({kind}) from Models first.",
                    )
                    return
                preview_model = f"{kind} • CustomVoice"

        elif profile.provider == "chatterbox":
            if not runtime_ready():
                QMessageBox.warning(
                    self,
                    "Custom Voice Engine Not Ready",
                    "Install / Repair the Custom Voice Engine first, then return here and test the voice.",
                )
                return

        self.preview_library.setText(preview_library)
        self.preview_provider.setText(self._provider_label(preview_profile))
        self.preview_voice.setText(profile.name or profile.voice_id or "Unnamed voice")
        self.preview_model.setText(preview_model)
        self.preview_profile.setText(profile.name or "Unsaved profile")
        self.preview_engine_status.setText(
            f"Queued • target {seconds}s • {len(text.split()):,} words"
        )
        self.status.setText(
            f"Generating preview • {preview_library} • {profile.name or profile.voice_id} • target {seconds}s"
        )

        output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
        self.preview_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.preview_activity_bar.setVisible(True)
        self.preview_target_seconds = seconds
        self.preview_worker = VoicePreviewWorker(preview_profile, text, output, seconds)
        self.preview_worker.status.connect(self._preview_worker_status)
        self.preview_worker.progress.connect(self.preview_percent_bar.setValue)
        self.preview_worker.finished_ok.connect(self._preview_worker_ok)
        self.preview_worker.failed.connect(self._preview_worker_failed)
        self.preview_worker.cancelled.connect(self._preview_worker_cancelled)
        self.preview_worker.finished.connect(self._preview_worker_finished)
        self.preview_worker.start()

    def _preview_worker_status(self, message: str) -> None:
        self.preview_engine_status.setText(message)
        self.status.setText(message)

    def _preview_worker_ok(self, path: str, elapsed_seconds: float = 0.0) -> None:
        self.last_preview = Path(path)
        self.last_preview_elapsed_seconds = max(0.0, float(elapsed_seconds))
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.play_button.setEnabled(True)
        self.play_button.setText("▶  Play")
        self.preview_percent_bar.setValue(100)
        self.preview_activity_bar.setVisible(False)
        actual_seconds = None
        try:
            with wave.open(str(self.last_preview), "rb") as reader:
                actual_seconds = reader.getnframes() / float(max(1, reader.getframerate()))
        except (OSError, wave.Error):
            pass
        target = getattr(self, "preview_target_seconds", None)
        elapsed = self.last_preview_elapsed_seconds or 0.0
        elapsed_label = f"generated in {int(elapsed) // 60}:{int(elapsed) % 60:02d}"
        rtf_label = (
            f" • RTF {elapsed / actual_seconds:.2f}"
            if actual_seconds is not None and actual_seconds > 0 and elapsed > 0
            else ""
        )
        if actual_seconds is not None and target:
            qualifier = "target reached" if actual_seconds + 0.25 >= target else "shorter than target"
            self.preview_engine_status.setText(
                f"100% • Ready • {actual_seconds:.1f}s / {int(target)}s • {qualifier} "
                f"• {elapsed_label}{rtf_label} • press Play"
            )
        else:
            self.preview_engine_status.setText(
                f"100% • Preview ready • {elapsed_label}{rtf_label} • press Play"
            )
        self.status.setText(
            f"Preview ready • {self.preview_provider.text()} • {self.preview_voice.text()}"
        )

    def _preview_worker_failed(self, message: str) -> None:
        self.preview_percent_bar.setValue(0)
        self.preview_activity_bar.setVisible(False)
        self.preview_engine_status.setText(f"0% • Preview failed • {message}")
        self.status.setText(f"Preview failed: {message}")
        self.preview_button.setEnabled(True)
        self.play_button.setEnabled(False)
        QMessageBox.warning(self, "Voice Preview Failed", message)

    def _preview_worker_cancelled(self) -> None:
        self.preview_percent_bar.setValue(0)
        self.preview_activity_bar.setVisible(False)
        self.preview_engine_status.setText("0% • Preview cancelled")
        self.status.setText("Voice preview cancelled.")
        self.preview_button.setEnabled(True)
        self.play_button.setEnabled(False)

    def _preview_worker_finished(self) -> None:
        self.preview_button.setEnabled(True)
        self.preview_worker = None

    def save_profile(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return

        default_name = profile.name.strip() or (
            "Qwen VoiceDesign Voice"
            if profile.qwen_mode == "design"
            else "Voice Profile"
        )
        entered, ok = QInputDialog.getText(
            self,
            "Save Voice Profile",
            "Profile name:",
            text=default_name,
        )
        if not ok:
            return
        entered = entered.strip()
        if not entered:
            self.status.setText("A profile name is required before saving.")
            return

        profile.name = entered
        existing = next(
            (
                p for p in self.profiles
                if p.name.casefold() == entered.casefold()
                and not p.name.startswith("Offline Neural •")
            ),
            None,
        )
        if existing and (
            existing.provider != profile.provider
            or existing.voice_id.casefold() != profile.voice_id.casefold()
            or existing.qwen_mode != profile.qwen_mode
        ):
            answer = QMessageBox.question(
                self,
                "Replace Voice Profile?",
                f"A voice profile named '{entered}' already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        profiles = [
            p for p in self.profiles
            if p.name.casefold() != entered.casefold()
            or p.name.startswith("Offline Neural •")
        ]
        profiles.append(profile)
        save_profiles(profiles)
        self.refresh_profiles()
        # Make the saved profile the active profile immediately. This keeps
        # the UI, preview, Voice Cast and later generation on the same provider.
        self.library_filter.setCurrentIndex(0)
        self.library_search.clear()
        self.refresh_profiles()
        self.saved_profiles.setCurrentIndex(self.saved_profiles.findData(profile.name))
        self.load_selected_profile()
        self.profile_badge.setText(profile.name)
        self._update_profile_details(profile)
        self.status.setText(f"Saved voice profile '{profile.name}' • {self._provider_label(profile)}.")

    def stop_preview_or_playback(self) -> None:
        self.player.stop()
        self.play_button.setText("▶  Play")
        worker = self.preview_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self.status.setText("Stopping voice preview…")

    def play_last_preview(self) -> None:
        if not self.last_preview or not self.last_preview.exists():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("▶  Play")
        else:
            self.player.play()
            self.play_button.setText("Ⅱ  Pause")

    def _player_error(self, _error, error_string):
        if error_string:
            self.status.setText(f"Preview playback error: {error_string}")

    def _duration_changed(self, duration):
        self._update_preview_time(0, duration)

    def _position_changed(self, position):
        self._update_preview_time(position, self.player.duration())

    def _update_preview_time(self, position, duration):
        def fmt(ms):
            seconds = max(0, ms // 1000)
            return f"{seconds // 60}:{seconds % 60:02d}"
        self.preview_progress.setText(f"{fmt(position)} / {fmt(duration)}")
