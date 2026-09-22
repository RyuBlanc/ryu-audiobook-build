from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import VoiceProfile, import_reference_audio, load_profiles, save_profiles


class VoicePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.sapi = SystemSAPIProvider()
        self.profiles = load_profiles()
        self.sample_path: Path | None = None
        self.last_preview: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QLabel(
            "<h2>Voice Profiles</h2>"
            "<span>Select, preview and save voices for your audiobooks.</span>"
        )
        root.addWidget(header)

        voice_box = QGroupBox("Voice setup")
        form = QFormLayout(voice_box)
        form.setContentsMargins(16, 16, 16, 16)
        form.setVerticalSpacing(10)

        self.mode = QComboBox()
        self.mode.addItem("Windows SAPI — installed Windows voice", "windows-sapi")
        self.mode.addItem("Custom Voice — authorized reference audio", "chatterbox")
        form.addRow("Voice type", self.mode)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Ryu Narrator")
        form.addRow("Profile name", self.name)

        self.sapi_voice = QComboBox()
        self._populate_sapi_voices()
        form.addRow("Windows voice", self.sapi_voice)

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
        preview_layout.setContentsMargins(16, 16, 16, 16)

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

        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def _populate_sapi_voices(self) -> None:
        self.sapi_voice.clear()
        for voice_id in self.sapi.voices():
            display = voice_id
            if "\Tokens\TTS_MS_" in voice_id:
                display = voice_id.rsplit("\", 1)[-1].replace("_", " ")
            self.sapi_voice.addItem(display, voice_id)

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
        elif profile.sample_path:
            self.sample_path = Path(profile.sample_path)
            self.sample_label.setText(self.sample_path.name)

        self.status.setText(f"Loaded voice profile: {profile.name}")

    def update_mode(self) -> None:
        custom = self.mode.currentData() == "chatterbox"
        self.sapi_voice.setEnabled(not custom)
        self.sample_button.setEnabled(custom)
        self.language.setEnabled(custom)
        self.authorized.setEnabled(custom)

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
            return VoiceProfile(
                name=name or self.sapi_voice.currentText().strip(),
                provider=provider,
                voice_id=voice_id,
                backend="automatic",
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
