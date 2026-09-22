from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget
)

from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import VoiceProfile, import_reference_audio, load_profiles, save_profiles
from app.tts.providers.edge_tts import EdgeTTSProvider


class VoicePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.sapi = SystemSAPIProvider()
        self.profiles = load_profiles()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None
        self.edge_voices: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(QLabel(
            "<h2>Voice Profiles</h2>"
            "<span>Choose from installed voices, a large multilingual neural catalog, "
            "or an authorized custom voice.</span>"
        ))

        voice_box = QGroupBox("Voice setup")
        form = QFormLayout(voice_box)
        form.setContentsMargins(16, 16, 16, 16)
        form.setVerticalSpacing(10)

        self.mode = QComboBox()
        self.mode.addItem("Windows SAPI — offline installed voices", "windows-sapi")
        self.mode.addItem("Neural Voices — 400+ multilingual voices", "edge-tts")
        self.mode.addItem("Custom Voice — authorized reference audio", "chatterbox")
        form.addRow("Voice source", self.mode)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Ryu Narrator")
        form.addRow("Profile name", self.name)

        self.sapi_voice = QComboBox()
        self._populate_sapi_voices()
        form.addRow("Windows voice", self.sapi_voice)

        self.gender = QComboBox()
        self.gender.addItems(["All", "Female", "Male"])
        self.gender.currentIndexChanged.connect(self.filter_edge_voices)
        form.addRow("Gender", self.gender)

        self.accent = QComboBox()
        self.accent.addItem("All accents / regions", "")
        self.accent.currentIndexChanged.connect(self.filter_edge_voices)
        form.addRow("Accent / region", self.accent)

        self.neural_voice = QComboBox()
        self.neural_voice.currentIndexChanged.connect(self._neural_voice_changed)
        form.addRow("Neural voice", self.neural_voice)

        neural_actions = QHBoxLayout()
        self.refresh_neural = QPushButton("Refresh voice catalog")
        self.refresh_neural.clicked.connect(lambda: self.load_edge_voices(True))
        neural_actions.addWidget(self.refresh_neural)
        self.neural_count = QLabel("")
        neural_actions.addWidget(self.neural_count)
        neural_actions.addStretch(1)
        form.addRow("", neural_actions)

        sample_row = QHBoxLayout()
        self.sample_button = QPushButton("Choose reference audio…")
        self.sample_button.clicked.connect(self.select_sample)
        self.sample_label = QLabel("No reference selected")
        self.sample_label.setWordWrap(True)
        sample_row.addWidget(self.sample_button)
        sample_row.addWidget(self.sample_label, 1)
        form.addRow("Custom voice", sample_row)

        self.language = QLineEdit("en")
        self.language.setPlaceholderText("Language code, e.g. en")
        form.addRow("Language", self.language)

        self.authorized = QCheckBox("I have permission to use this reference voice")
        form.addRow("", self.authorized)
        root.addWidget(voice_box)

        saved_box = QGroupBox("Saved profiles")
        saved_row = QHBoxLayout(saved_box)
        self.saved_profiles = QComboBox()
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_selected_profile)
        saved_row.addWidget(self.saved_profiles, 1)
        saved_row.addWidget(self.load_button)
        root.addWidget(saved_box)
        self.refresh_profiles()

        preview_box = QGroupBox("Voice preview")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_text = QTextEdit()
        self.preview_text.setPlaceholderText("Enter a short sentence to preview the selected voice…")
        self.preview_text.setPlainText("Welcome to Ryu's Audiobook. This is a short voice preview.")
        self.preview_text.setMinimumHeight(90)
        self.preview_text.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_text)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("▶  Preview Voice")
        self.preview_button.clicked.connect(self.preview)
        self.play_button = QPushButton("▶  Play Last Preview")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_last_preview)
        self.save_button = QPushButton("Save Voice Profile")
        self.save_button.clicked.connect(self.save_profile)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.play_button)
        actions.addWidget(self.save_button)
        preview_layout.addLayout(actions)
        root.addWidget(preview_box)

        self.status = QLabel("Ready. Neural voice catalog can be refreshed when online.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()
        self.load_edge_voices(False)

    def _populate_sapi_voices(self) -> None:
        self.sapi_voice.clear()
        for voice_id in self.sapi.voices():
            display = voice_id
            if "\\Tokens\\TTS_MS_" in voice_id:
                display = voice_id.rsplit("\\", 1)[-1].replace("_", " ")
            self.sapi_voice.addItem(display, voice_id)

    def load_edge_voices(self, refresh: bool = False) -> None:
        try:
            self.edge_voices = EdgeTTSProvider.fetch_voice_metadata(refresh=refresh)
            self.neural_count.setText(f"{len(self.edge_voices)} voices")
            accents = sorted({v.get("locale", "") for v in self.edge_voices if v.get("locale")})
            current = self.accent.currentData() if self.accent.count() else ""
            self.accent.blockSignals(True)
            self.accent.clear()
            self.accent.addItem("All accents / regions", "")
            for locale in accents:
                self.accent.addItem(locale, locale)
            idx = self.accent.findData(current)
            self.accent.setCurrentIndex(max(0, idx))
            self.accent.blockSignals(False)
            self.filter_edge_voices()
        except Exception as exc:
            self.neural_count.setText("Catalog unavailable")
            self.status.setText(f"Neural catalog unavailable: {exc}")

    def filter_edge_voices(self) -> None:
        if not hasattr(self, "neural_voice"):
            return
        gender = self.gender.currentText() if self.gender.count() else "All"
        locale = self.accent.currentData() if self.accent.count() else ""
        current = self.neural_voice.currentData()
        self.neural_voice.blockSignals(True)
        self.neural_voice.clear()

        matches = [
            v for v in self.edge_voices
            if (gender == "All" or v.get("gender", "").lower() == gender.lower())
            and (not locale or v.get("locale") == locale)
        ]
        for voice in matches:
            name = voice.get("name", "")
            label = voice.get("friendly_name") or name
            if voice.get("locale"):
                label = f"{label}  ·  {voice['locale']}  ·  {voice.get('gender', 'Unknown')}"
            self.neural_voice.addItem(label, name)

        if current:
            idx = self.neural_voice.findData(current)
            if idx >= 0:
                self.neural_voice.setCurrentIndex(idx)
        self.neural_voice.blockSignals(False)
        self._neural_voice_changed()

    def _neural_voice_changed(self) -> None:
        voice_id = self.neural_voice.currentData()
        if voice_id and self.mode.currentData() == "edge-tts":
            voice = next((v for v in self.edge_voices if v.get("name") == voice_id), None)
            if voice:
                self.name.setText(voice.get("friendly_name") or voice_id)
                self.language.setText(voice.get("locale", "en"))

    def refresh_profiles(self) -> None:
        self.saved_profiles.clear()
        for profile in self.profiles:
            self.saved_profiles.addItem(profile.name, profile.name)

    def load_selected_profile(self) -> None:
        name = self.saved_profiles.currentData()
        if not name:
            return
        profile = next((p for p in self.profiles if p.name == name), None)
        if not profile:
            return

        index = self.mode.findData(profile.provider)
        if index >= 0:
            self.mode.setCurrentIndex(index)

        self.name.setText(profile.name)
        self.language.setText(profile.language or "en")
        self.authorized.setChecked(profile.authorized)

        if profile.provider == "windows-sapi":
            index = self.sapi_voice.findData(profile.voice_id)
            if index >= 0:
                self.sapi_voice.setCurrentIndex(index)
        elif profile.provider == "edge-tts":
            index = self.neural_voice.findData(profile.voice_id)
            if index >= 0:
                self.neural_voice.setCurrentIndex(index)
        elif profile.sample_path:
            self.sample_path = Path(profile.sample_path)
            self.sample_label.setText(self.sample_path.name)

        self.status.setText(f"Loaded voice profile: {profile.name}")

    def update_mode(self) -> None:
        provider = self.mode.currentData()
        is_edge = provider == "edge-tts"
        custom = provider == "chatterbox"

        self.sapi_voice.setVisible(provider == "windows-sapi")
        self.gender.setVisible(is_edge)
        self.accent.setVisible(is_edge)
        self.neural_voice.setVisible(is_edge)
        self.refresh_neural.setVisible(is_edge)
        self.neural_count.setVisible(is_edge)
        self.sample_button.setEnabled(custom)
        self.sample_button.setVisible(custom)
        self.sample_label.setVisible(custom)
        self.language.setEnabled(custom)
        self.authorized.setEnabled(custom)

        if provider == "windows-sapi":
            self.status.setText("Windows SAPI runs locally and offline.")
        elif is_edge:
            self.status.setText("Neural catalog provides many male/female voices and regional accents. Internet is required to synthesize.")
        else:
            self.status.setText("Custom voice requires an authorized reference recording.")

    def select_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Voice", "", "Audio (*.wav *.mp3 *.m4a *.flac)"
        )
        if not path:
            return
        source = Path(path)
        name = self.name.text().strip() or source.stem
        try:
            self.sample_path = import_reference_audio(source, name)
            self.sample_label.setText(self.sample_path.name)
            self.status.setText("Reference audio copied to your local Voices folder.")
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
            return VoiceProfile(name=name or self.sapi_voice.currentText().strip(), provider=provider, voice_id=voice_id, backend="automatic", authorized=True)

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
                language=voice.get("locale") or self.language.text().strip() or "en",
                authorized=True,
            )

        if not self.sample_path:
            self.status.setText("Choose a reference voice sample first.")
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
            language=self.language.text().strip() or "en",
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
                provider = ChatterboxProvider(
                    reference_audio=Path(profile.sample_path),
                    backend="cpu",
                    language=profile.language,
                    multilingual=True,
                )

            provider.synthesize(text, output, profile.voice_id)
            if not output.exists() or output.stat().st_size < 1024:
                raise RuntimeError("The voice engine did not produce a valid audio file.")

            self.last_preview = output
            self.play_button.setEnabled(True)
            self.status.setText("Preview ready. Playing it now…")
            self.play_last_preview()
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))
            self.status.setText(f"Preview failed: {exc}")
        finally:
            self.preview_button.setEnabled(True)

    def play_last_preview(self) -> None:
        if not self.last_preview or not self.last_preview.exists():
            self.status.setText("No preview audio is available yet.")
            return
        if os.name == "nt":
            os.startfile(str(self.last_preview))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_preview)))

    def save_profile(self) -> None:
        profile = self._profile_from_ui()
        if not profile:
            return
        profiles = [p for p in self.profiles if p.name.lower() != profile.name.lower()]
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
        self.status.setText(f"Saved voice profile: {profile.name}")
