from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QLabel, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget, QLineEdit, QCheckBox
)

from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import (
    VoiceProfile, import_reference_audio, load_profiles, save_profiles
)


class VoicePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.sapi = SystemSAPIProvider()
        self.profiles = load_profiles()
        self.sample_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Voice Profiles</h2>"))

        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("Windows SAPI", "windows-sapi")
        self.mode.addItem("Custom Voice / Chatterbox", "chatterbox")
        form.addRow("Voice type:", self.mode)

        self.name = QLineEdit()
        form.addRow("Profile name:", self.name)

        self.sapi_voice = QComboBox()
        self.sapi_voice.addItems(self.sapi.voices())
        form.addRow("Windows voice:", self.sapi_voice)

        self.sample_button = QPushButton("Select Reference Audio")
        self.sample_button.clicked.connect(self.select_sample)
        form.addRow("Custom voice:", self.sample_button)

        self.language = QLineEdit("en")
        form.addRow("Language:", self.language)

        self.authorized = QCheckBox("I have permission to use this reference voice")
        form.addRow("", self.authorized)

        layout.addLayout(form)

        self.preview_text = QTextEdit()
        self.preview_text.setPlainText(
            "Welcome to Ryu's Audiobook. This is a voice preview. "
            "The selected voice profile can be reused for audiobook generation."
        )
        layout.addWidget(QLabel("Preview Text"))
        layout.addWidget(self.preview_text)

        self.preview_button = QPushButton("Preview Voice")
        self.save_button = QPushButton("Save Voice Profile")
        layout.addWidget(self.preview_button)
        layout.addWidget(self.save_button)

        self.status = QLabel("Select a voice type.")
        layout.addWidget(self.status)

        self.mode.currentIndexChanged.connect(self.update_mode)
        self.preview_button.clicked.connect(self.preview)
        self.save_button.clicked.connect(self.save_profile)
        self.update_mode()

    def update_mode(self):
        custom = self.mode.currentData() == "chatterbox"
        self.sapi_voice.setEnabled(not custom)
        self.sample_button.setEnabled(custom)
        self.language.setEnabled(custom)
        self.authorized.setEnabled(custom)

    def select_sample(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Voice",
            "", "Audio (*.wav *.mp3 *.m4a *.flac)"
        )
        if not path:
            return
        source = Path(path)
        name = self.name.text().strip() or source.stem
        try:
            self.sample_path = import_reference_audio(source, name)
            self.status.setText(f"Reference copied locally: {self.sample_path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Voice Import Failed", str(exc))

    def _profile_from_ui(self) -> VoiceProfile | None:
        provider = self.mode.currentData()
        name = self.name.text().strip()

        if provider == "windows-sapi":
            voice_id = self.sapi_voice.currentText().strip()
            if not voice_id:
                return None
            return VoiceProfile(
                name=name or voice_id.split("\\")[-1],
                provider=provider,
                voice_id=voice_id,
                backend="automatic",
                authorized=True,
            )

        if not self.sample_path:
            self.status.setText("Select a reference voice sample first.")
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

    def preview(self):
        profile = self._profile_from_ui()
        if not profile:
            return
        text = self.preview_text.toPlainText().strip()
        if not text:
            return

        try:
            import tempfile
            output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"

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
            self.status.setText(f"Preview generated: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))

    def save_profile(self):
        profile = self._profile_from_ui()
        if not profile:
            return
        profiles = [p for p in self.profiles if p.name != profile.name]
        profiles.append(profile)
        save_profiles(profiles)
        self.profiles = profiles
        self.status.setText(f"Saved voice profile: {profile.name}")
