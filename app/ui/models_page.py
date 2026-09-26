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


class ChatterboxInstallWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        try:
            if getattr(sys, "frozen", False):
                python_cmd = ["py", "-m", "pip"]
                if subprocess.run(
                    ["py", "--version"], capture_output=True, text=True
                ).returncode != 0:
                    raise RuntimeError(
                        "The Windows Python launcher (py.exe) is required to install the "
                        "optional custom voice engine from the packaged app. "
                        "Install Python 3.11/3.12 with the launcher, then retry."
                    )
            else:
                python_cmd = [sys.executable, "-m", "pip"]
            result = subprocess.run(
                python_cmd + ["install", "-r", "requirements-voice-cloning.txt"],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip()[-3000:] or "Chatterbox installation failed.")
            mark_installed("chatterbox-multilingual", True)
            self.finished_ok.emit("Chatterbox")
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelsPage(QWidget):
    def __init__(self):
        super().__init__()
        ensure_roots()
        self.worker: PiperDownloadWorker | None = None
        self.chatterbox_worker: ChatterboxInstallWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Local TTS Models</h2>"))
        layout.addWidget(QLabel(
            "Models stay on this PC. The application installer does not contain large model files."
        ))

        self.list = QListWidget()
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.install_piper = QPushButton("Download Piper Voice")
        self.install_chatterbox = QPushButton("Install Custom Voice Engine")
        self.refresh_button = QPushButton("Refresh")
        row.addWidget(self.install_piper)
        row.addWidget(self.install_chatterbox)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        self.install_piper.clicked.connect(self.download_piper)
        self.install_chatterbox.clicked.connect(self.install_chatterbox_runtime)
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


    def install_chatterbox_runtime(self) -> None:
        answer = QMessageBox.question(
            self,
            "Install Custom Voice Engine",
            "This installs the optional Chatterbox voice-cloning runtime and its dependencies. "
            "It requires an internet connection and may need several GB of disk space for the "
            "runtime and model files. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_chatterbox.setEnabled(False)
        self.status.setText("Installing Chatterbox custom voice engine…")
        self.chatterbox_worker = ChatterboxInstallWorker()
        self.chatterbox_worker.finished_ok.connect(self._chatterbox_ok)
        self.chatterbox_worker.failed.connect(self._chatterbox_failed)
        self.chatterbox_worker.start()

    def _chatterbox_ok(self, name: str) -> None:
        self.install_chatterbox.setEnabled(True)
        self.status.setText("Custom voice engine installed. Its model will download when first used.")
        self.refresh()

    def _chatterbox_failed(self, message: str) -> None:
        self.install_chatterbox.setEnabled(True)
        QMessageBox.warning(self, "Custom Voice Engine Installation Failed", message)
        self.status.setText("Custom voice engine installation failed.")
