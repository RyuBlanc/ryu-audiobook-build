from __future__ import annotations

import tempfile
from pathlib import Path
import webbrowser
import secrets

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

from app.tts.profile_provider import provider_from_profile
from app.tts.chatterbox_runtime import runtime_ready, runtime_status
from app.tts.qwen_character_runtime import (
    runtime_ready as qwen_runtime_ready,
    model_installed as qwen_model_installed,
    best_clone_kind,
    best_custom_kind,
    best_voice_design_kind,
)
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import (
    VoiceProfile, builtin_voice_profiles, import_reference_audio,
    load_profiles, save_profiles,
)
from app.tts.providers.edge_tts import EdgeTTSProvider
from app.tts.providers.elevenlabs import ElevenLabsProvider


class VoicePreviewWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)
    cancelled = Signal()


    def __init__(self, profile: VoiceProfile, text: str, output: Path):
        super().__init__()
        self.profile = profile
        self.text = text
        self.output = output
        self.provider = None
        self.cancel_requested = False

    def run(self) -> None:
        try:
            self.provider, voice = provider_from_profile(self.profile)
            self.output.parent.mkdir(parents=True, exist_ok=True)
            if self.cancel_requested:
                self.cancelled.emit()
                return
            self.provider.synthesize(self.text, self.output, voice)
            if self.cancel_requested:
                self.cancelled.emit()
                return
            if not self.output.exists() or self.output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce valid audio.")
            self.finished_ok.emit(str(self.output))
        except Exception as exc:
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
        provider = self.provider
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
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
        self.sapi = SystemSAPIProvider()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None
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

        self.install_character_voices_button = QPushButton("Install / Repair Qwen Voice Studio")
        self.install_character_voices_button.clicked.connect(self.open_offline_character_models)
        self.install_character_voices_button.setVisible(False)
        source_layout.addWidget(self.install_character_voices_button)
        self.offline_character_status = QLabel()
        self.offline_character_status.setObjectName('muted')
        self.offline_character_status.setWordWrap(True)
        source_layout.addWidget(self.offline_character_status)

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
        source_layout.addLayout(premium_row)
        self.premium_key_button.setVisible(False)
        self.premium_key_help_button.setVisible(False)
        self.premium_key_status.setVisible(False)

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
        source_layout.addWidget(self.character_box)
        root.addWidget(source)

        self.neural_box = QGroupBox("2  •  Neural / Character Voice")
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
        root.addWidget(self.neural_box)

        self.qwen_phase_box = QGroupBox("2  •  Qwen3-TTS Voice Studio")
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

        root.addWidget(self.qwen_phase_box)

        self.sapi_box = QGroupBox("2  •  Windows Voice")
        sapi_layout = QHBoxLayout(self.sapi_box)
        sapi_layout.addWidget(QLabel("Installed voice"))
        self.sapi_voice = QComboBox()
        sapi_layout.addWidget(self.sapi_voice, 1)
        self.sapi_voice.currentIndexChanged.connect(self._sapi_voice_changed)
        root.addWidget(self.sapi_box)

        self.custom_box = QGroupBox("2  •  Custom Authorized Voice")
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
        root.addWidget(self.custom_box)

        profile_box = QGroupBox("3  •  Voice Profile")
        profile = QVBoxLayout(profile_box)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Main Narrator")
        form.addRow("Profile name", self.name)
        profile.addLayout(form)

        library_filters = QHBoxLayout()
        self.library_filter = QComboBox()
        self.library_filter.addItem("All voices", "all")
        self.library_filter.addItem("Built-in offline", "builtin")
        self.library_filter.addItem("Saved custom", "custom")
        self.library_filter.addItem("Windows", "windows-sapi")
        self.library_filter.addItem("Online", "edge-tts")
        self.library_filter.addItem("Premium Online", "elevenlabs")
        self.library_filter.currentIndexChanged.connect(self.refresh_profiles)
        library_filters.addWidget(QLabel("Library"))
        library_filters.addWidget(self.library_filter)
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search saved voices…")
        self.library_search.textChanged.connect(self.refresh_profiles)
        library_filters.addWidget(self.library_search, 1)
        profile.addLayout(library_filters)

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
        self.detail_provider = QLabel("—")
        self.detail_language = QLabel("—")
        self.detail_voice_id = QLabel("—")
        self.detail_reference = QLabel("—")
        self.detail_backend = QLabel("—")
        self.detail_authorization = QLabel("—")
        for label, widget in (
            ("Provider", self.detail_provider),
            ("Language", self.detail_language),
            ("Voice ID", self.detail_voice_id),
            ("Reference", self.detail_reference),
            ("Backend", self.detail_backend),
            ("Authorization", self.detail_authorization),
        ):
            widget.setWordWrap(True)
            details.addRow(label, widget)
        profile.addWidget(details_box)

        actions = QHBoxLayout()
        self.save_profile_button = QPushButton("Save / Update Profile")
        self.save_profile_button.setObjectName("primary")
        self.save_profile_button.clicked.connect(self.save_profile)
        self.test_profile_button = QPushButton("Test Current Voice")
        self.test_profile_button.clicked.connect(self.preview)
        actions.addWidget(self.save_profile_button)
        actions.addWidget(self.test_profile_button)
        actions.addStretch(1)
        profile.addLayout(actions)
        root.addWidget(profile_box)

        preview_box = QGroupBox("4  •  Preview")
        pv = QVBoxLayout(preview_box)
        self.preview_text = QTextEdit()
        self.preview_text.setPlainText("Welcome to Ryu's Audiobook. This is a short voice preview.")
        self.preview_text.setMinimumHeight(78)
        self.preview_text.setMaximumHeight(125)
        pv.addWidget(self.preview_text)

        pa = QHBoxLayout()
        self.preview_button = QPushButton("▶  Generate Preview")
        self.preview_button.setObjectName("primary")
        self.preview_button.clicked.connect(self.preview)
        self.play_button = QPushButton("▶  Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_last_preview)
        self.stop_button = QPushButton("■  Stop")
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

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self._populate_sapi_voices()
        self._update_profile_details(None)
        self.refresh_profiles()
        self._refresh_offline_catalog()
        self.update_mode()

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
            if voice_id in {"Vivian", "Serena", "Ono_Anna", "Sohee"}:
                return "Female"
            if voice_id in {"Ryan", "Aiden", "Uncle_Fu", "Dylan", "Eric"}:
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
            "qwen-character": "Offline Character • Qwen3-TTS",
        }
        return labels.get(profile.provider, profile.provider)

    @staticmethod
    def _profile_category(profile: VoiceProfile) -> str:
        if profile.provider in {"piper", "kokoro"}:
            return "builtin"
        if profile.provider == "qwen-character":
            return "offline-character"
        return profile.provider

    @staticmethod
    def _reference_label(profile: VoiceProfile) -> str:
        if profile.provider != "chatterbox":
            return "Not required"
        if not profile.sample_path:
            return "Missing • no reference recorded"
        path = Path(profile.sample_path)
        if not path.exists():
            return f"Missing • {path.name}"
        return f"✓ Local reference • {path.name}"

    def _update_profile_details(self, profile: VoiceProfile | None) -> None:
        if profile is None:
            self.detail_provider.setText("—")
            self.detail_language.setText("—")
            self.detail_voice_id.setText("—")
            self.detail_reference.setText("—")
            self.detail_backend.setText("—")
            self.detail_authorization.setText("—")
            return
        language = profile.language or "Not specified"
        self.detail_provider.setText(self._provider_label(profile))
        self.detail_language.setText(self._language_name(language) if language else "Not specified")
        self.detail_voice_id.setText(profile.voice_id or "—")
        self.detail_reference.setText(self._reference_label(profile))
        self.detail_backend.setText(profile.backend or "automatic")
        if hasattr(self, "style_preset") and profile.provider == "chatterbox":
            idx = self.style_preset.findData(
                (profile.style_preset or "Natural", float(profile.exaggeration), float(profile.cfg_weight))
            )
            if idx >= 0:
                self.style_preset.setCurrentIndex(idx)
        self.detail_authorization.setText(
            "✓ Authorized" if profile.authorized else "⚠ Permission not confirmed"
        )

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

        source_provider = "offline-neural" if profile.provider in {"piper", "kokoro"} else profile.provider
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

        if profile.provider == "windows-sapi":
            i = self.sapi_voice.findData(profile.voice_id)
            if i >= 0:
                self.sapi_voice.setCurrentIndex(i)
        elif profile.provider in {"piper", "kokoro", "qwen-character", "edge-tts"}:
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
                "Models opened. Click Download Offline Character Voices to install the local Qwen3-TTS character pack."
            )
        else:
            self.status.setText(
                "Open Models → Download Offline Character Voices to install the local Qwen3-TTS character pack."
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
            kind = best_custom_kind()
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
            ready = qwen_runtime_ready()
            installed = ready and qwen_model_installed(best_voice_design_kind())
            self.source_hint.setText(
                "Qwen3-TTS VoiceDesign • create a brand-new fictional voice from a natural-language description. "
                "VoiceDesign uses the 1.7B model."
            )
            self.offline_character_status.setText(
                f"{'✓' if installed else '○'} VoiceDesign model: design-1.7b • "
                + ("ready" if installed else "not installed")
            )
            self.qwen_phase_status.setText(
                "Phase 2 • VoiceDesign — ideal for anime heroines, heroes, villains, narrators and cinematic character voices. "
                "On 4GB GPUs it may fall back to CPU."
            )

        elif mode == "qwen-clone":
            ready = qwen_runtime_ready()
            kind = best_clone_kind()
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

    def _profile_from_ui(self) -> VoiceProfile | None:
        provider = self.mode.currentData()
        name = self.name.text().strip()

        if provider in {"offline-neural", "offline-character"}:
            voice_id = self.neural_voice.currentData()
            profile = next(
                (
                    x for x in self.offline_voices
                    if x.voice_id == voice_id
                    and (
                        (provider == "offline-character" and x.provider == "qwen-character")
                        or (provider == "offline-neural" and x.provider != "qwen-character")
                    )
                ),
                None,
            )
            if not profile:
                self.status.setText(
                    "Select an offline character voice first."
                    if provider == "offline-character"
                    else "Select an offline neural voice first."
                )
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
            self.status.setText(
                "Choose a reference audio file first, or load a custom profile with a valid local reference."
            )
            return None
        if not self.authorized.isChecked():
            self.status.setText(
                "Confirm that you have permission to use this voice."
            )
            return None
        custom_name = name or self.sample_path.stem
        if custom_name.startswith("Offline Neural •") or custom_name.startswith("Microsoft "):
            custom_name = self.sample_path.stem
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

    def preview(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return
        text = self.preview_text.toPlainText().strip()
        if not text:
            self.status.setText("Enter preview text first.")
            return

        if profile.provider == "qwen-character":
            from app.tts.qwen_character_runtime import runtime_ready, model_installed, best_custom_kind
            if not runtime_ready() or not model_installed(best_custom_kind()):
                QMessageBox.warning(
                    self,
                    "Offline Character Voices Not Ready",
                    "Open Models → Download Offline Character Voices first."
                )
                return
        if profile.provider == "chatterbox" and not runtime_ready():
            QMessageBox.warning(
                self,
                "Custom Voice Engine Not Ready",
                "Install / Repair the Custom Voice Engine first, then return here and test the voice."
            )
            return

        output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
        self.preview_button.setEnabled(False)
        self.test_profile_button.setEnabled(False)
        self.status.setText(
            "Preparing voice preview… "
            "the interface remains responsive while the voice engine loads."
        )
        self.preview_worker = VoicePreviewWorker(profile, text, output)
        self.preview_worker.finished_ok.connect(self._preview_worker_ok)
        self.preview_worker.failed.connect(self._preview_worker_failed)
        self.preview_worker.cancelled.connect(self._preview_worker_cancelled)
        self.preview_worker.finished.connect(self._preview_worker_finished)
        self.preview_worker.start()

    def _preview_worker_ok(self, path: str) -> None:
        self.last_preview = Path(path)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.play_button.setEnabled(True)
        self.play_button.setText("▶  Play")
        self.status.setText("Preview ready. Press Play to listen.")

    def _preview_worker_failed(self, message: str) -> None:
        self.status.setText(f"Preview failed: {message}")
        QMessageBox.warning(self, "Voice Preview Failed", message)

    def _preview_worker_cancelled(self) -> None:
        self.status.setText("Voice preview cancelled.")
        self.preview_button.setEnabled(True)
        self.test_profile_button.setEnabled(True)

    def _preview_worker_finished(self) -> None:
        self.preview_button.setEnabled(True)
        self.test_profile_button.setEnabled(True)
        self.preview_worker = None

    def save_profile(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return
        profiles = [
            p for p in self.profiles
            if p.name.casefold() != profile.name.casefold()
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
