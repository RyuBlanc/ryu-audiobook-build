from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import urllib.request
import ssl

try:
    import certifi
except ImportError:
    certifi = None

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QMessageBox, QInputDialog
)

from app.core.paths import models_root, ensure_roots
from app.tts.chatterbox_runtime import install_runtime, runtime_status
from app.tts.model_registry import BUILTIN_CATALOG, installed_models, mark_installed
from app.tts.providers.piper import PiperProvider
from app.tts.providers.kokoro import KokoroProvider


KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"


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


class KokoroDownloadWorker(QThread):
    finished_ok = Signal()
    failed = Signal(str)
    progress = Signal(str)

    def _download(self, url: str, target: Path, label: str) -> None:
        temp = target.with_suffix(target.suffix + ".part")
        try:
            self.progress.emit(f"Downloading {label}…")
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Ryu-Audiobook/1.1",
                    "Accept": "application/octet-stream",
                },
            )
            # Some Windows Python installations do not have a usable local
            # CA bundle even though browsers work normally. Use certifi's
            # maintained CA bundle when available; never disable TLS
            # verification for model downloads.
            context = (
                ssl.create_default_context(cafile=certifi.where())
                if certifi is not None
                else ssl.create_default_context()
            )
            with urllib.request.urlopen(request, timeout=90, context=context) as response, temp.open("wb") as handle:
                total = int(response.headers.get("Content-Length", "0") or 0)
                received = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    received += len(block)
                    if total:
                        self.progress.emit(f"Downloading {label}… {received * 100 // total}%")
            if not temp.exists() or temp.stat().st_size < 1024:
                raise RuntimeError(f"Downloaded {label} is incomplete.")
            temp.replace(target)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)

    def run(self) -> None:
        try:
            target = models_root() / "kokoro"
            target.mkdir(parents=True, exist_ok=True)
            self._download(KOKORO_MODEL_URL, target / "kokoro-v1.0.onnx", "Kokoro model (~326 MB)")
            self._download(KOKORO_VOICES_URL, target / "voices-v1.0.bin", "Kokoro voice pack (~28 MB)")
            mark_installed("kokoro", True)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class ChatterboxInstallWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:
        try:
            install_runtime(self.progress.emit)
            mark_installed("chatterbox-multilingual", True)
            self.finished_ok.emit("Chatterbox")
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelsPage(QWidget):
    def __init__(self):
        super().__init__()
        ensure_roots()
        self.worker: PiperDownloadWorker | None = None
        self.kokoro_worker: KokoroDownloadWorker | None = None
        self.chatterbox_worker: ChatterboxInstallWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Local TTS Models</h2>"))
        layout.addWidget(QLabel(
            "Models stay on this PC. Kokoro provides a larger natural-voice catalogue for offline audiobook generation; Piper remains the lightweight fallback."
        ))

        self.list = QListWidget()
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.install_kokoro = QPushButton("Download Natural Voices")
        self.install_piper = QPushButton("Download Piper Voice")
        self.install_chatterbox = QPushButton("Install / Repair Custom Voice Engine")
        self.refresh_button = QPushButton("Refresh")
        row.addWidget(self.install_kokoro)
        row.addWidget(self.install_piper)
        row.addWidget(self.install_chatterbox)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        self.install_kokoro.clicked.connect(self.download_kokoro)
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

        kokoro_voices = KokoroProvider().voices()
        if "kokoro" in installed:
            self.list.addItem(f"Kokoro voices available: {len(kokoro_voices)}")

        self.list.addItem(f"Custom voice runtime: {runtime_status()}")
        voices = PiperProvider.model_paths()
        if voices:
            self.list.addItem("")
            self.list.addItem("Installed Piper voices:")
            for voice in voices:
                self.list.addItem(f"  • {voice.stem}")

    def download_kokoro(self) -> None:
        if KokoroProvider.assets_available():
            self.status.setText("Kokoro natural voices are already installed.")
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "Download Natural Offline Voices",
            "Kokoro adds a roughly 354 MB offline model and voice pack. It stays on this PC and does not require an online TTS service after installation. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_kokoro.setEnabled(False)
        self.status.setText("Preparing Kokoro natural voices…")
        self.kokoro_worker = KokoroDownloadWorker()
        self.kokoro_worker.finished_ok.connect(self._kokoro_ok)
        self.kokoro_worker.failed.connect(self._kokoro_failed)
        self.kokoro_worker.progress.connect(self.status.setText)
        self.kokoro_worker.start()

    def _kokoro_ok(self) -> None:
        self.install_kokoro.setEnabled(True)
        self.status.setText("Kokoro natural offline voices installed.")
        self.refresh()

    def _kokoro_failed(self, message: str) -> None:
        self.install_kokoro.setEnabled(True)
        self.status.setText("Kokoro download failed")
        detail = str(message)
        if "CERTIFICATE_VERIFY_FAILED" in detail or "CERTIFICATE_VERIFY_FAILED".casefold() in detail.casefold():
            detail += (
                "\n\nRyu's Audiobook now uses a bundled CA certificate store for this download. "
                "Please retry after installing this build. If a corporate antivirus/proxy intercepts HTTPS, "
                "use a normal browser to download the two Kokoro files and place them in "
                "Models\\kokoro."
            )
        QMessageBox.warning(self, "Natural Voice Download Failed", detail)

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
        self.chatterbox_worker.progress.connect(self.status.setText)
        self.chatterbox_worker.start()

    def _chatterbox_ok(self, name: str) -> None:
        self.install_chatterbox.setEnabled(True)
        self.status.setText("Custom voice engine installed. Its model will download when first used.")
        self.refresh()

    def _chatterbox_failed(self, message: str) -> None:
        self.install_chatterbox.setEnabled(True)
        QMessageBox.warning(self, "Custom Voice Engine Installation Failed", message)
        self.status.setText("Custom voice engine installation failed.")
