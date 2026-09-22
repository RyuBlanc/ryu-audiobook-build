from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QMessageBox, QInputDialog
)

from app.core.paths import models_root, ensure_roots
from app.tts.model_registry import BUILTIN_CATALOG, installed_models, mark_installed
from app.tts.providers.piper import PiperProvider


class PiperDownloadWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, voice_name: str):
        super().__init__()
        self.voice_name = voice_name

    def run(self) -> None:
        try:
            target = models_root() / "piper"
            target.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable, "-m", "piper.download_voices",
                self.voice_name, "--data-dir", str(target)
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip() or "Voice download failed.")
            mark_installed("piper", True)
            self.finished_ok.emit(self.voice_name)
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelsPage(QWidget):
    def __init__(self):
        super().__init__()
        ensure_roots()
        self.worker: PiperDownloadWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Local TTS Models</h2>"))
        layout.addWidget(QLabel(
            "Models stay on this PC. The application installer does not contain large model files."
        ))

        self.list = QListWidget()
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.install_piper = QPushButton("Download Piper Voice")
        self.refresh_button = QPushButton("Refresh")
        row.addWidget(self.install_piper)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        self.install_piper.clicked.connect(self.download_piper)
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        installed = {m.model_id for m in installed_models()}
        for spec in BUILTIN_CATALOG:
            state = "Installed" if spec.model_id in installed else "Not installed"
            clone = " • Voice cloning" if spec.voice_cloning else ""
            self.list.addItem(f"{spec.display_name} — {state}{clone}")

        voices = PiperProvider.model_paths()
        if voices:
            self.list.addItem("")
            self.list.addItem("Installed Piper voices:")
            for voice in voices:
                self.list.addItem(f"  • {voice.stem}")

    def download_piper(self) -> None:
        voice, ok = QInputDialog.getText(
            self,
            "Download Piper Voice",
            "Piper voice name:",
            text="en_US-lessac-medium",
        )
        if not ok or not voice.strip():
            return

        self.install_piper.setEnabled(False)
        self.status.setText(f"Downloading {voice.strip()}...")
        self.worker = PiperDownloadWorker(voice.strip())
        self.worker.finished_ok.connect(self._download_ok)
        self.worker.failed.connect(self._download_failed)
        self.worker.start()

    def _download_ok(self, voice: str) -> None:
        self.install_piper.setEnabled(True)
        self.status.setText(f"Installed Piper voice: {voice}")
        self.refresh()

    def _download_failed(self, message: str) -> None:
        self.install_piper.setEnabled(True)
        self.status.setText("Download failed")
        QMessageBox.warning(self, "Piper Download Failed", message)
