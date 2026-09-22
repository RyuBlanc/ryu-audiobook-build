from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QLabel, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget
)

from app.tts.system_sapi import SystemSAPIProvider
from app.tts.voice_profile import VoiceProfile, load_profiles, save_profiles

class VoicePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.provider = SystemSAPIProvider()
        self.profiles = load_profiles()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Voice Selection & Preview"))

        form = QFormLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.provider.voices())
        form.addRow("Installed Windows voice:", self.voice_combo)
        layout.addLayout(form)

        self.preview_text = QTextEdit()
        self.preview_text.setPlainText(
            "Welcome to Ryu's Audiobook. This is a voice preview. "
            "The selected voice will be used by the local narration engine."
        )
        layout.addWidget(QLabel("Preview Text"))
        layout.addWidget(self.preview_text)

        self.preview_button = QPushButton("Preview Voice")
        self.save_button = QPushButton("Save Voice Profile")
        self.sample_button = QPushButton("Select Voice Sample")
        layout.addWidget(self.preview_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.sample_button)

        self.status = QLabel("Offline Windows voices are available in this first build.")
        layout.addWidget(self.status)

        self.preview_button.clicked.connect(self.preview)
        self.save_button.clicked.connect(self.save_profile)
        self.sample_button.clicked.connect(self.select_sample)

        self.sample_path: Path | None = None

    def preview(self) -> None:
        text = self.preview_text.toPlainText().strip()
        if not text:
            return
        try:
            import tempfile
            output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
            self.provider.synthesize(text, output, self.voice_combo.currentText())
            self.status.setText(f"Preview generated: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))

    def save_profile(self) -> None:
        voice_id = self.voice_combo.currentText()
        if not voice_id:
            return
        name = voice_id.split("\\")[-1] or voice_id
        profiles = [p for p in self.profiles if p.voice_id != voice_id]
        profiles.append(VoiceProfile(name=name, provider="windows-sapi", voice_id=voice_id, sample_path=str(self.sample_path) if self.sample_path else None))
        save_profiles(profiles)
        self.profiles = profiles
        self.status.setText(f"Saved voice profile: {name}")

    def select_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Voice Sample", "", "Audio (*.wav *.mp3 *.m4a *.flac)")
        if path:
            self.sample_path = Path(path)
            self.status.setText(f"Voice sample selected: {self.sample_path.name}")
