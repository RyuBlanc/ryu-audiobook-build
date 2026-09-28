from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.tts.profile_provider import provider_from_profile
from app.tts.chatterbox_runtime import runtime_ready, runtime_status
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import (
    VoiceProfile, builtin_voice_profiles, import_reference_audio,
    load_profiles, save_profiles,
)
from app.tts.providers.edge_tts import EdgeTTSProvider


class VoicePage(QWidget):
    """Offline-first voice library and reusable narration profiles."""

    def __init__(self) -> None:
        super().__init__()
        self.profiles = load_profiles()
        self.sapi = SystemSAPIProvider()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None
        self.edge_voices: list[dict] = []
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
        self.mode = QComboBox()
        self.mode.addItem("Offline Neural Voices  ·  built into this app", "piper")
        self.mode.addItem("Windows SAPI  ·  installed offline voices", "windows-sapi")
        self.mode.addItem("Online Neural Voices  ·  Edge TTS", "edge-tts")
        self.mode.addItem("Custom Voice  ·  authorized reference audio", "chatterbox")
        self.mode.currentIndexChanged.connect(self.update_mode)
        source_layout.addWidget(self.mode)
        self.source_hint = QLabel()
        self.source_hint.setObjectName("muted")
        self.source_hint.setWordWrap(True)
        source_layout.addWidget(self.source_hint)
        root.addWidget(source)

        self.neural_box = QGroupBox("2  •  Neural Voice")
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
        self.refresh_neural.clicked.connect(self._refresh_online_catalog)
        voice_row.addWidget(self.refresh_neural)
        self.neural_count = QLabel("")
        self.neural_count.setObjectName("muted")
        voice_row.addWidget(self.neural_count)
        neural.addLayout(voice_row)
        root.addWidget(self.neural_box)

        self.sapi_box = QGroupBox("2  •  Windows Voice")
        sapi_layout = QHBoxLayout(self.sapi_box)
        sapi_layout.addWidget(QLabel("Installed voice"))
        self.sapi_voice = QComboBox()
        sapi_layout.addWidget(self.sapi_voice, 1)
        self.sapi_voice.currentIndexChanged.connect(self._sapi_voice_changed)
        root.addWidget(self.sapi_box)

        self.custom_box = QGroupBox("2  •  Custom Authorized Voice")
        custom = QVBoxLayout(self.custom_box)
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
            "for the voice engine."
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
        self.stop_button.clicked.connect(self.player.stop)
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

    def _refresh_online_catalog(self) -> None:
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

        if self.mode.currentData() == "piper":
            for profile in self.offline_voices:
                lower = profile.voice_id.lower()
                voice_gender = (
                    "Female" if "amy" in lower
                    else "Male" if any(x in lower for x in ("lessac", "ryan"))
                    else "Neutral"
                )
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
        if self.mode.currentData() == "piper":
            profile = next(
                (x for x in self.offline_voices if x.voice_id == voice_id), None
            )
            if profile:
                self.name.setText(profile.name)
                self.profile_badge.setText(profile.name)
        else:
            voice = next(
                (x for x in self.edge_voices if x.get("name") == voice_id), None
            )
            if voice:
                label = voice.get("friendly_name") or voice_id
                self.name.setText(label)
                self.profile_badge.setText(label)

    def _sapi_voice_changed(self) -> None:
        if self.mode.currentData() == "windows-sapi" and self.sapi_voice.currentText():
            self.name.setText(self.sapi_voice.currentText())
            self.profile_badge.setText(self.sapi_voice.currentText())

    @staticmethod
    def _provider_label(profile: VoiceProfile) -> str:
        labels = {
            "piper": "Built-in Offline Neural",
            "windows-sapi": "Windows SAPI",
            "edge-tts": "Online Neural • Edge TTS",
            "chatterbox": "Custom Voice • Chatterbox",
        }
        return labels.get(profile.provider, profile.provider)

    @staticmethod
    def _profile_category(profile: VoiceProfile) -> str:
        if profile.provider == "piper":
            return "builtin"
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
        self.detail_authorization.setText(
            "✓ Authorized" if profile.authorized else "⚠ Permission not confirmed"
        )

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

        index = self.mode.findData(profile.provider)
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
        elif profile.provider in {"piper", "edge-tts"}:
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
        if not profile or profile.provider == "piper":
            return
        if QMessageBox.question(
            self, "Delete Voice Profile", f"Delete '{name}'?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.profiles = [p for p in self.profiles if p.name != name]
        save_profiles(self.profiles)
        self.refresh_profiles()
        self.status.setText(f"Deleted voice profile: {name}")

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
        self.neural_box.setVisible(mode in {"piper", "edge-tts"})
        self.sapi_box.setVisible(mode == "windows-sapi")
        self.custom_box.setVisible(mode == "chatterbox")

        if mode == "piper":
            self.source_hint.setText(
                "Built-in local neural voices. No internet connection is used for preview or generation."
            )
            self._refresh_offline_catalog()
        elif mode == "edge-tts":
            self.source_hint.setText(
                "Online neural catalog. Internet is required for synthesis; this is optional "
                "and not used by the offline voices."
            )
            if not self.edge_voices:
                self._refresh_online_catalog()
            else:
                self._set_filter_values_edge()
                self._refresh_voice_list()
        elif mode == "windows-sapi":
            self.source_hint.setText("Uses voices already installed in Windows. Fully offline.")
        else:
            self.source_hint.setText(
                "Use only a reference recording you are authorized to use. The reference remains local. "
                f"Custom voice engine: {runtime_status()}. Install or repair it from Models before preview/generation."
            )

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
            self.status.setText(
                "Reference imported locally. Confirm permission before saving. "
                f"Custom voice profile name: {self.name.text().strip()}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Voice Import Failed", str(exc))

    def _profile_from_ui(self) -> VoiceProfile | None:
        provider = self.mode.currentData()
        name = self.name.text().strip()

        if provider == "piper":
            voice_id = self.neural_voice.currentData()
            profile = next(
                (x for x in self.offline_voices if x.voice_id == voice_id), None
            )
            if not profile:
                self.status.setText("Select an offline neural voice first.")
                return None
            return VoiceProfile(
                name=name or profile.name,
                provider="piper",
                voice_id=profile.voice_id,
                model_id="piper",
                backend="automatic",
                language=profile.language,
                notes=profile.notes,
                authorized=True,
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
        return VoiceProfile(
            name=custom_name,
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
            self.status.setText("Enter preview text first.")
            return

        output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
        try:
            if profile.provider == "chatterbox" and not runtime_ready():
                raise RuntimeError(
                    "The custom voice engine is not installed. Open Models → Install / Repair Custom Voice Engine, "
                    "then return here and try the preview again."
                )
            self.preview_button.setEnabled(False)
            self.status.setText("Generating preview…")
            provider, voice = provider_from_profile(profile)
            provider.synthesize(text, output, voice)
            if not output.exists() or output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce valid audio.")
            self.last_preview = output
            self.player.setSource(QUrl.fromLocalFile(str(output)))
            self.play_button.setEnabled(True)
            self.status.setText("Preview ready. Playing locally.")
            self.player.play()
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))
            self.status.setText(f"Preview failed: {exc}")
        finally:
            self.preview_button.setEnabled(True)

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
