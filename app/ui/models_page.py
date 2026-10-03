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
from app.tts.qwen_character_runtime import install_runtime as install_qwen_runtime, install_model as install_qwen_model, model_installed as qwen_model_installed, best_custom_kind
from app.ai.model_runtime import brain_root, install_runtime as install_audiobook_ai, recommended_model, installed as audiobook_ai_installed, self_test as test_audiobook_ai


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




class QwenCharacterInstallWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:
        try:
            self.progress.emit("Installing isolated Qwen3-TTS runtime…")
            install_qwen_runtime(self.progress.emit)
            # Keep the 0.6B model compatible with the RTX 3050 4GB target.
            # On the RTX 4060 8GB target we also install the 1.7B CustomVoice
            # model for higher-quality local character timbre.
            vram_gb = 0.0
            # Main Ryu environment intentionally does not depend on PyTorch.
            # Detect NVIDIA VRAM through nvidia-smi when available so the
            # installer can choose 1.7B on the 8GB RTX 4060 and 0.6B on the
            # 4GB RTX 3050.
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    values = [
                        float(line.strip())
                        for line in result.stdout.splitlines()
                        if line.strip().replace(".", "", 1).isdigit()
                    ]
                    if values:
                        vram_gb = max(values) / 1024.0
            except Exception:
                pass
            kind = "custom-1.7b" if vram_gb >= 7.0 else "custom-0.6b"
            self.progress.emit(
                f"Preparing offline character voices using {'1.7B' if kind.endswith('1.7b') else '0.6B'} Qwen3-TTS…"
            )
            install_qwen_model(kind, self.progress.emit)
            self.finished_ok.emit(kind)
        except Exception as exc:
            self.failed.emit(str(exc))


class AudiobookAIInstallWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:
        try:
            model_id, filename, size = recommended_model()
            install_audiobook_ai(self.progress.emit)
            self.progress.emit("Testing local Audiobook AI inference…")
            test_result = test_audiobook_ai()
            self.finished_ok.emit(f"{model_id}|{filename}|{size}|{test_result}")
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
        self.qwen_character_worker: QwenCharacterInstallWorker | None = None
        self.audiobook_ai_worker: AudiobookAIInstallWorker | None = None

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
        self.install_qwen_character = QPushButton("Download Offline Character Voices")
        self.install_audiobook_ai = QPushButton("Install Audiobook AI")
        self.refresh_button = QPushButton("Refresh")
        row.addWidget(self.install_kokoro)
        row.addWidget(self.install_piper)
        row.addWidget(self.install_chatterbox)
        row.addWidget(self.install_qwen_character)
        row.addWidget(self.install_audiobook_ai)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        self.install_kokoro.clicked.connect(self.download_kokoro)
        self.install_piper.clicked.connect(self.download_piper)
        self.install_chatterbox.clicked.connect(self.install_chatterbox_runtime)
        self.install_qwen_character.clicked.connect(self.install_qwen_character_runtime)
        self.install_audiobook_ai.clicked.connect(self.install_audiobook_ai_runtime)
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
        qwen_status = []
        if qwen_model_installed("custom-1.7b"):
            qwen_status.append("1.7B")
        if qwen_model_installed("custom-0.6b"):
            qwen_status.append("0.6B")
        self.list.addItem(
            "Offline character voices: " + (", ".join(qwen_status) if qwen_status else "Not installed")
        )

        model_id, filename, size = recommended_model()
        ai_state = "Installed" if audiobook_ai_installed() else "Not installed"
        size_gb = size / (1024 ** 3)
        self.list.addItem(f"Audiobook AI: {ai_state} • {model_id} • ~{size_gb:.1f} GB model")
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

    def install_qwen_character_runtime(self) -> None:
        answer = QMessageBox.question(
            self,
            "Download Offline Character Voices",
            "Ryu's Audiobook will install the Qwen3-TTS offline character engine and a "
            "compatible local voice model. No API key is required and generation remains "
            "on this PC after installation. The model download may be several GB. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_qwen_character.setEnabled(False)
        self.status.setText("Preparing offline character voices…")
        self.qwen_character_worker = QwenCharacterInstallWorker()
        self.qwen_character_worker.finished_ok.connect(self._qwen_character_ok)
        self.qwen_character_worker.failed.connect(self._qwen_character_failed)
        self.qwen_character_worker.progress.connect(self.status.setText)
        self.qwen_character_worker.start()

    def _qwen_character_ok(self, kind: str) -> None:
        self.install_qwen_character.setEnabled(True)
        label = "1.7B premium" if kind.endswith("1.7b") else "0.6B compatible"
        self.status.setText(
            f"Offline character voices installed • {label} Qwen3-TTS model. "
            "Return to Voice & Narration and select an Offline Character voice."
        )
        self.refresh()

    def _qwen_character_failed(self, message: str) -> None:
        self.install_qwen_character.setEnabled(True)
        self.status.setText("Offline character voice installation failed.")
        QMessageBox.warning(self, "Offline Character Voice Installation Failed", message)

    def install_audiobook_ai_runtime(self) -> None:
        model_id, filename, size = recommended_model()
        size_gb = size / (1024 ** 3)
        answer = QMessageBox.question(
            self,
            "Install Audiobook AI",
            f"Ryu's Audiobook will install a local analysis engine using {model_id}. "
            f"The model download is about {size_gb:.1f} GB. "
            "After installation, book analysis works offline and the AI does not modify your source text. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_audiobook_ai.setEnabled(False)
        self.status.setText("Installing local Audiobook AI…")
        self.audiobook_ai_worker = AudiobookAIInstallWorker()
        self.audiobook_ai_worker.finished_ok.connect(self._audiobook_ai_ok)
        self.audiobook_ai_worker.failed.connect(self._audiobook_ai_failed)
        self.audiobook_ai_worker.progress.connect(self.status.setText)
        self.audiobook_ai_worker.start()

    def _audiobook_ai_ok(self, detail: str) -> None:
        self.install_audiobook_ai.setEnabled(True)
        parts = detail.split("|", 3)
        result = parts[3] if len(parts) > 3 else "ready"
        self.status.setText(f"Audiobook AI installed and self-tested successfully • {result}")
        self.refresh()

    def _audiobook_ai_failed(self, message: str) -> None:
        self.install_audiobook_ai.setEnabled(True)
        self.status.setText("Audiobook AI installation failed.")
        QMessageBox.warning(self, "Audiobook AI Installation Failed", message)

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
