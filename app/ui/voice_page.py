from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import (
    VoiceProfile,
    import_reference_audio,
    load_profiles,
    save_profiles,
)
from app.tts.providers.edge_tts import EdgeTTSProvider


class VoicePage(QWidget):
    """Voice & Narration studio.

    The page is intentionally organized as a simple creative workflow:
    source -> language -> gender -> voice -> preview -> save profile.
    Custom reference recordings use the same profile workflow and accept MP3,
    WAV, M4A, FLAC, AAC, OGG, OPUS and WMA.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sapi = SystemSAPIProvider()
        self.profiles = load_profiles()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None
        self.edge_voices: list[dict] = []

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(self._player_error)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(QLabel("<h1>Voice & Narration</h1>"))
        subtitle = QLabel(
            "Choose a narrator, preview the voice, then save it as a reusable profile."
        )
        subtitle.setObjectName("muted")
        title_col.addWidget(subtitle)
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

        source_box = QGroupBox("1  •  Voice source")
        source_layout = QVBoxLayout(source_box)
        source_layout.setSpacing(8)
        self.mode = QComboBox()
        self.mode.addItem("Windows SAPI  ·  installed offline voices", "windows-sapi")
        self.mode.addItem("Neural Voices  ·  multilingual catalog", "edge-tts")
        self.mode.addItem("Custom Voice  ·  authorized reference audio", "chatterbox")
        source_layout.addWidget(self.mode)
        self.source_hint = QLabel()
        self.source_hint.setObjectName("muted")
        self.source_hint.setWordWrap(True)
        source_layout.addWidget(self.source_hint)
        root.addWidget(source_box)

        self.neural_box = QGroupBox("2  •  Neural voice")
        neural_layout = QVBoxLayout(self.neural_box)
        neural_layout.setSpacing(10)

        language_row = QHBoxLayout()
        language_col = QVBoxLayout()
        language_col.addWidget(QLabel("Language"))
        self.language_filter = QComboBox()
        self.language_filter.addItem("All languages", "")
        self.language_filter.currentIndexChanged.connect(self._refresh_voice_catalog_filters)
        language_col.addWidget(self.language_filter)
        language_row.addLayout(language_col, 2)

        gender_col = QVBoxLayout()
        gender_col.addWidget(QLabel("Gender"))
        self.gender_filter = QComboBox()
        self.gender_filter.addItems(["All", "Female", "Male", "Neutral"])
        self.gender_filter.currentIndexChanged.connect(self._refresh_voice_catalog_filters)
        gender_col.addWidget(self.gender_filter)
        language_row.addLayout(gender_col, 1)

        accent_col = QVBoxLayout()
        accent_col.addWidget(QLabel("Accent / region"))
        self.accent_filter = QComboBox()
        self.accent_filter.addItem("All regions", "")
        self.accent_filter.currentIndexChanged.connect(self._refresh_voice_catalog_filters)
        accent_col.addWidget(self.accent_filter)
        language_row.addLayout(accent_col, 2)
        neural_layout.addLayout(language_row)

        self.recommended_label = QLabel("Recommended voices")
        self.recommended_label.setObjectName("muted")
        neural_layout.addWidget(self.recommended_label)

        voice_row = QHBoxLayout()
        self.neural_voice = QComboBox()
        self.neural_voice.currentIndexChanged.connect(self._neural_voice_changed)
        voice_row.addWidget(self.neural_voice, 1)
        self.refresh_neural = QPushButton("Refresh catalog")
        self.refresh_neural.clicked.connect(lambda: self.load_edge_voices(True))
        voice_row.addWidget(self.refresh_neural)
        self.neural_count = QLabel("")
        self.neural_count.setObjectName("muted")
        voice_row.addWidget(self.neural_count)
        neural_layout.addLayout(voice_row)

        self.sapi_voice = QComboBox()
        self.sapi_voice.currentIndexChanged.connect(self._sapi_voice_changed)
        sapi_row = QHBoxLayout()
        sapi_row.addWidget(QLabel("Installed Windows voice"))
        sapi_row.addWidget(self.sapi_voice, 1)
        neural_layout.addLayout(sapi_row)

        root.addWidget(self.neural_box)

        self.custom_box = QGroupBox("Custom authorized voice")
        custom_layout = QVBoxLayout(self.custom_box)
        custom_layout.setSpacing(8)
        custom_row = QHBoxLayout()
        self.sample_button = QPushButton("Choose MP3 / audio reference…")
        self.sample_button.clicked.connect(self.select_sample)
        custom_row.addWidget(self.sample_button)
        self.sample_label = QLabel("No reference selected")
        self.sample_label.setWordWrap(True)
        custom_row.addWidget(self.sample_label, 1)
        custom_layout.addLayout(custom_row)

        custom_info = QLabel(
            "Your original file is kept locally and a normalized reference.wav is created "
            "for the local voice engine. The selected reference is stored with this profile."
        )
        custom_info.setObjectName("muted")
        custom_info.setWordWrap(True)
        custom_layout.addWidget(custom_info)

        self.authorized = QCheckBox(
            "I have permission to use this reference recording."
        )
        custom_layout.addWidget(self.authorized)
        root.addWidget(self.custom_box)

        profile_box = QGroupBox("3  •  Voice profile")
        profile_layout = QVBoxLayout(profile_box)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile name"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Main Narrator")
        profile_row.addWidget(self.name, 1)
        profile_layout.addLayout(profile_row)

        saved_row = QHBoxLayout()
        saved_row.addWidget(QLabel("Saved profiles"))
        self.saved_profiles = QComboBox()
        self.saved_profiles.currentIndexChanged.connect(self._saved_profile_changed)
        saved_row.addWidget(self.saved_profiles, 1)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_selected_profile)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected_profile)
        saved_row.addWidget(self.load_button)
        saved_row.addWidget(self.delete_button)
        profile_layout.addLayout(saved_row)

        profile_actions = QHBoxLayout()
        self.save_profile_button = QPushButton("Save / Update This Profile")
        self.save_profile_button.setObjectName("primary")
        self.save_profile_button.clicked.connect(self.save_profile)
        self.test_profile_button = QPushButton("Test Current Voice")
        self.test_profile_button.clicked.connect(self.preview)
        profile_actions.addWidget(self.save_profile_button)
        profile_actions.addWidget(self.test_profile_button)
        profile_actions.addStretch(1)
        profile_layout.addLayout(profile_actions)

        root.addWidget(profile_box)

        preview_box = QGroupBox("4  •  Preview")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_text = QTextEdit()
        self.preview_text.setPlaceholderText("Type a short sentence to preview this voice…")
        self.preview_text.setPlainText(
            "Welcome to Ryu's Audiobook. This is a short voice preview."
        )
        self.preview_text.setMinimumHeight(78)
        self.preview_text.setMaximumHeight(125)
        preview_layout.addWidget(self.preview_text)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("▶  Generate Preview")
        self.preview_button.setObjectName("primary")
        self.preview_button.clicked.connect(self.preview)
        self.play_button = QPushButton("▶  Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_last_preview)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.clicked.connect(self.player.stop)
        self.save_button = QPushButton("Save Voice Profile")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_profile)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.play_button)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        preview_layout.addLayout(actions)

        progress_row = QHBoxLayout()
        self.preview_progress = QLabel("0:00 / 0:00")
        progress_row.addWidget(self.preview_progress)
        progress_row.addStretch(1)
        self.volume = QComboBox()
        self.volume.addItems(["Volume 50%", "Volume 70%", "Volume 85%", "Volume 100%"])
        self.volume.setCurrentIndex(2)
        self.volume.currentIndexChanged.connect(
            lambda i: self.audio_output.setVolume([0.5, 0.7, 0.85, 1.0][i])
        )
        progress_row.addWidget(self.volume)
        preview_layout.addLayout(progress_row)
        root.addWidget(preview_box)

        next_box = QGroupBox("5  •  Ready for generation")
        next_layout = QVBoxLayout(next_box)
        next_layout.addWidget(
            QLabel(
                "Save the selected voice as a profile. The same profile can then be "
                "selected from Generate and reused for future books."
            )
        )
        root.addWidget(next_box)

        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.player.durationChanged.connect(self._duration_changed)
        self.player.positionChanged.connect(self._position_changed)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.refresh_profiles()
        self._populate_sapi_voices()
        self.load_edge_voices(False)
        self.update_mode()

    def _populate_sapi_voices(self) -> None:
        current = self.sapi_voice.currentData()
        self.sapi_voice.blockSignals(True)
        self.sapi_voice.clear()
        for voice_id in self.sapi.voices():
            normalized_id = voice_id.replace("\\", "/")
            display = (
                normalized_id.rsplit("/", 1)[-1].replace("_", " ")
                if "/" in normalized_id
                else voice_id
            )
            self.sapi_voice.addItem(display, voice_id)
        if current:
            index = self.sapi_voice.findData(current)
            if index >= 0:
                self.sapi_voice.setCurrentIndex(index)
        self.sapi_voice.blockSignals(False)

    @staticmethod
    def _language_name(code: str) -> str:
        names = {
            "en": "English",
            "de": "German",
            "fr": "French",
            "es": "Spanish",
            "it": "Italian",
            "pt": "Portuguese",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "hi": "Hindi",
            "ta": "Tamil",
            "te": "Telugu",
            "ar": "Arabic",
            "ru": "Russian",
            "nl": "Dutch",
            "pl": "Polish",
            "tr": "Turkish",
        }
        return names.get(code.lower(), code.upper())

    def load_edge_voices(self, refresh: bool = False) -> None:
        try:
            self.edge_voices = EdgeTTSProvider.fetch_voice_metadata(refresh=refresh)
            self.neural_count.setText(f"{len(self.edge_voices)} voices")

            languages = sorted(
                {
                    str(v.get("locale", "")).split("-", 1)[0].lower()
                    for v in self.edge_voices
                    if v.get("locale")
                }
            )
            accents = sorted(
                {str(v.get("locale", "")) for v in self.edge_voices if v.get("locale")}
            )

            current_lang = self.language_filter.currentData()
            current_accent = self.accent_filter.currentData()
            self.language_filter.blockSignals(True)
            self.accent_filter.blockSignals(True)
            self.language_filter.clear()
            self.language_filter.addItem("All languages", "")
            for code in languages:
                self.language_filter.addItem(self._language_name(code), code)

            self.accent_filter.clear()
            self.accent_filter.addItem("All regions", "")
            for locale in accents:
                self.accent_filter.addItem(locale, locale)

            if current_lang:
                idx = self.language_filter.findData(current_lang)
                if idx >= 0:
                    self.language_filter.setCurrentIndex(idx)
            if current_accent:
                idx = self.accent_filter.findData(current_accent)
                if idx >= 0:
                    self.accent_filter.setCurrentIndex(idx)
            self.language_filter.blockSignals(False)
            self.accent_filter.blockSignals(False)
            self._refresh_voice_catalog_filters()
        except Exception as exc:
            self.neural_count.setText("Catalog unavailable")
            self.status.setText(f"Neural catalog unavailable: {exc}")
            self._refresh_voice_catalog_filters()

    def _refresh_voice_catalog_filters(self) -> None:
        if not hasattr(self, "neural_voice"):
            return

        language = self.language_filter.currentData() or ""
        gender = self.gender_filter.currentText()
        locale = self.accent_filter.currentData() or ""
        current = self.neural_voice.currentData()

        matches = []
        for voice in self.edge_voices:
            voice_locale = str(voice.get("locale", ""))
            voice_gender = str(voice.get("gender", "")).lower()
            language_ok = not language or voice_locale.lower().startswith(language + "-")
            accent_ok = not locale or voice_locale == locale
            if gender == "Neutral":
                gender_ok = voice_gender not in {"male", "female"}
            else:
                gender_ok = gender == "All" or voice_gender == gender.lower()
            if language_ok and accent_ok and gender_ok:
                matches.append(voice)

        matches.sort(
            key=lambda v: (
                0 if self._is_recommended(v) else 1,
                str(v.get("locale", "")),
                str(v.get("friendly_name") or v.get("name", "")),
            )
        )

        self.neural_voice.blockSignals(True)
        self.neural_voice.clear()
        if not matches:
            self.neural_voice.addItem("No matching neural voices", None)
        else:
            for voice in matches:
                name = voice.get("name", "")
                label = voice.get("friendly_name") or name
                locale = voice.get("locale", "")
                voice_gender = voice.get("gender", "Neutral")
                prefix = "★ " if self._is_recommended(voice) else ""
                self.neural_voice.addItem(
                    f"{prefix}{label}  ·  {locale}  ·  {voice_gender}",
                    name,
                )
        if current:
            idx = self.neural_voice.findData(current)
            if idx >= 0:
                self.neural_voice.setCurrentIndex(idx)
        self.neural_voice.blockSignals(False)
        self._neural_voice_changed()

    @staticmethod
    def _is_recommended(voice: dict) -> bool:
        locale = str(voice.get("locale", "")).lower()
        return locale in {"en-us", "en-gb", "en-in"} and bool(voice.get("name"))

    def _neural_voice_changed(self) -> None:
        voice_id = self.neural_voice.currentData()
        if not voice_id:
            return
        voice = next((v for v in self.edge_voices if v.get("name") == voice_id), None)
        if not voice:
            return
        self.name.setText(voice.get("friendly_name") or voice_id)
        self.language_filter.blockSignals(True)
        locale = str(voice.get("locale", ""))
        language = locale.split("-", 1)[0] if locale else "en"
        idx = self.language_filter.findData(language)
        if idx >= 0:
            self.language_filter.setCurrentIndex(idx)
        self.language_filter.blockSignals(False)
        self.language = locale or "en"
        self.profile_badge.setText(voice.get("friendly_name") or voice_id)

    def _sapi_voice_changed(self) -> None:
        if self.mode.currentData() == "windows-sapi":
            self.name.setText(self.sapi_voice.currentText().strip())
            self.profile_badge.setText(self.sapi_voice.currentText().strip() or "No profile selected")

    def refresh_profiles(self) -> None:
        current = self.saved_profiles.currentData() if hasattr(self, "saved_profiles") else None
        self.saved_profiles.blockSignals(True)
        self.saved_profiles.clear()
        for profile in self.profiles:
            self.saved_profiles.addItem(profile.name, profile.name)
        if current:
            index = self.saved_profiles.findData(current)
            if index >= 0:
                self.saved_profiles.setCurrentIndex(index)
        self.saved_profiles.blockSignals(False)

    def _saved_profile_changed(self) -> None:
        name = self.saved_profiles.currentData()
        if name:
            self.profile_badge.setText(str(name))
            # Selection itself is enough to identify the intended profile.
            # Loading is explicit so changing a dropdown cannot unexpectedly
            # overwrite a reference sample or current edits.

    def load_selected_profile(self) -> None:
        name = self.saved_profiles.currentData()
        if not name:
            self.status.setText("Select a saved profile first.")
            return
        profile = next((p for p in self.profiles if p.name == name), None)
        if not profile:
            self.status.setText("The selected profile is no longer available.")
            self.refresh_profiles()
            return

        mode_index = self.mode.findData(profile.provider)
        if mode_index >= 0:
            self.mode.setCurrentIndex(mode_index)

        self.name.setText(profile.name)
        self.authorized.setChecked(profile.authorized)
        self.sample_path = None
        self.sample_label.setText("No reference selected")

        if profile.provider == "windows-sapi":
            index = self.sapi_voice.findData(profile.voice_id)
            if index >= 0:
                self.sapi_voice.setCurrentIndex(index)
        elif profile.provider == "edge-tts":
            voice_index = self.neural_voice.findData(profile.voice_id)
            if voice_index < 0:
                self._refresh_voice_catalog_filters()
                voice_index = self.neural_voice.findData(profile.voice_id)
            if voice_index >= 0:
                self.neural_voice.setCurrentIndex(voice_index)
            else:
                self.status.setText(
                    f"Saved voice '{profile.voice_id}' is not in the current catalog. "
                    "Refresh the neural catalog."
                )
                return
        elif profile.provider == "chatterbox":
            if not profile.sample_path:
                self.status.setText("This custom profile has no reference path.")
                return
            sample = Path(profile.sample_path)
            if not sample.exists():
                self.status.setText(f"Reference file not found: {sample}")
                return
            self.sample_path = sample
            self.sample_label.setText(f"✓ {sample.name}")

        self.profile_badge.setText(profile.name)
        self.status.setText(f"Loaded voice profile: {profile.name}")

    def delete_selected_profile(self) -> None:
        name = self.saved_profiles.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Delete Voice Profile",
            f"Delete the saved profile '{name}'? Reference audio files are kept.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.profiles = [p for p in self.profiles if p.name != name]
        save_profiles(self.profiles)
        self.refresh_profiles()
        self.profile_badge.setText("No profile selected")
        self.status.setText(f"Deleted voice profile: {name}")

    def update_mode(self) -> None:
        provider = self.mode.currentData()
        is_edge = provider == "edge-tts"
        custom = provider == "chatterbox"

        self.neural_box.setVisible(is_edge)
        self.custom_box.setVisible(custom)
        if custom:
            self.sample_button.setToolTip("Select an MP3, WAV, M4A, FLAC, AAC, OGG, OPUS or WMA reference.")
            self.authorized.setToolTip("Required before a custom voice profile can be saved or tested.")
        self.sapi_voice.setVisible(provider == "windows-sapi")
        self.sapi_voice.parentWidget().setVisible(provider == "windows-sapi")
        self.neural_voice.setVisible(is_edge)
        self.language_filter.setVisible(is_edge)
        self.gender_filter.setVisible(is_edge)
        self.accent_filter.setVisible(is_edge)
        self.refresh_neural.setVisible(is_edge)
        self.neural_count.setVisible(is_edge)
        self.recommended_label.setVisible(is_edge)
        self.sample_button.setVisible(custom)
        self.sample_label.setVisible(custom)
        self.authorized.setVisible(custom)
        self.source_hint.setText(
            "Runs locally using voices installed in Windows."
            if provider == "windows-sapi"
            else (
                "Large multilingual neural catalog. Voice synthesis requires internet access."
                if is_edge
                else "Use a reference recording you are authorized to use. MP3 and common audio formats are supported."
            )
        )

        self.language_filter.setEnabled(is_edge)
        self.gender_filter.setEnabled(is_edge)
        self.accent_filter.setEnabled(is_edge)
        self.name.setEnabled(True)

    def select_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Voice",
            "",
            "Audio files (*.wav *.mp3 *.m4a *.flac *.aac *.ogg *.opus *.wma);;All files (*.*)",
        )
        if not path:
            return
        source = Path(path)
        name = self.name.text().strip() or source.stem
        try:
            self.sample_path = import_reference_audio(source, name)
            self.sample_label.setText(f"✓ {source.name}  →  {self.sample_path.name}")
            self.name.setText(name)
            self.authorized.setChecked(False)
            self.profile_badge.setText(name)
            self.status.setText(
                "Reference imported locally. Confirm permission, then save the voice profile."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Voice Import Failed", str(exc))

    def _profile_from_ui(self) -> VoiceProfile | None:
        provider = self.mode.currentData()
        name = self.name.text().strip()

        if provider == "windows-sapi":
            voice_id = self.sapi_voice.currentData() or self.sapi_voice.currentText().strip()
            if not voice_id:
                self.status.setText("No Windows voice is available.")
                return None
            return VoiceProfile(
                name=name or self.sapi_voice.currentText().strip(),
                provider=provider,
                voice_id=voice_id,
                backend="automatic",
                authorized=True,
            )

        if provider == "edge-tts":
            voice_id = self.neural_voice.currentData()
            if not voice_id:
                self.status.setText("Select a neural voice first.")
                return None
            voice = next((v for v in self.edge_voices if v.get("name") == voice_id), {})
            return VoiceProfile(
                name=name or voice_id,
                provider="edge-tts",
                voice_id=voice_id,
                backend="automatic",
                language=voice.get("locale") or "en",
                authorized=True,
            )

        if not self.sample_path or not self.sample_path.exists():
            self.status.setText("Choose a reference audio file first.")
            return None
        if not self.authorized.isChecked():
            self.status.setText("Confirm that you have permission to use this voice.")
            return None

        return VoiceProfile(
            name=name or self.sample_path.stem,
            provider="chatterbox",
            voice_id=self.sample_path.stem,
            sample_path=str(self.sample_path),
            model_id="chatterbox-multilingual",
            backend="automatic",
            language="en",
            authorized=True,
        )

    def preview(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return
        text = self.preview_text.toPlainText().strip()
        if not text:
            self.status.setText("Enter some preview text first.")
            return

        output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
        try:
            self.preview_button.setEnabled(False)
            self.status.setText("Generating preview…")

            if profile.provider == "windows-sapi":
                provider = self.sapi
            elif profile.provider == "edge-tts":
                provider = EdgeTTSProvider()
            else:
                from app.tts.providers.chatterbox import ChatterboxProvider

                reference = Path(profile.sample_path or "")
                if not reference.exists():
                    raise RuntimeError(
                        "The saved custom voice reference is missing. "
                        "Load the profile again or choose the MP3/audio reference."
                    )
                provider = ChatterboxProvider(
                    reference_audio=reference,
                    backend="automatic",
                    language=profile.language,
                    multilingual=True,
                )

            provider.synthesize(text, output, profile.voice_id)
            if not output.exists() or output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce a valid audio file.")

            self.last_preview = output
            self.play_button.setEnabled(True)
            self._set_player_source(output)
            self.status.setText("Preview ready.")
            self.player.play()
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))
            self.status.setText(f"Preview failed: {exc}")
        finally:
            self.preview_button.setEnabled(True)

    def _set_player_source(self, path: Path) -> None:
        self.player.setSource(QUrl.fromLocalFile(str(path)))

    def play_last_preview(self) -> None:
        if not self.last_preview or not self.last_preview.exists():
            self.status.setText("No preview audio is available yet.")
            return
        if self.player.source().toLocalFile() != str(self.last_preview):
            self._set_player_source(self.last_preview)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("▶  Play")
        else:
            self.player.play()
            self.play_button.setText("Ⅱ  Pause")

    def _player_error(self, _error, error_string: str) -> None:
        if error_string:
            self.status.setText(f"Preview playback error: {error_string}")

    def _duration_changed(self, duration: int) -> None:
        self._update_preview_time(0, duration)

    def _position_changed(self, position: int) -> None:
        self._update_preview_time(position, self.player.duration())

    def _update_preview_time(self, position: int, duration: int) -> None:
        def fmt(ms: int) -> str:
            seconds = max(0, ms // 1000)
            return f"{seconds // 60}:{seconds % 60:02d}"

        self.preview_progress.setText(f"{fmt(position)} / {fmt(duration)}")

    def save_profile(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return

        profiles = [
            p for p in self.profiles if p.name.strip().lower() != profile.name.strip().lower()
        ]
        profiles.append(profile)

        try:
            save_profiles(profiles)
        except OSError as exc:
            QMessageBox.critical(self, "Save Voice Profile Failed", str(exc))
            return

        self.profiles = profiles
        self.refresh_profiles()
        index = self.saved_profiles.findData(profile.name)
        if index >= 0:
            self.saved_profiles.setCurrentIndex(index)
        self.profile_badge.setText(profile.name)
        self.status.setText(
            f"Saved voice profile '{profile.name}'. It is now available in Generate."
        )
