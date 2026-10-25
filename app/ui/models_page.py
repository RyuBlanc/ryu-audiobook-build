from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import ssl

try:
    import certifi
except ImportError:
    certifi = None

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QScrollArea,
    QFrame, QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox,
    QInputDialog
)

from app.core.paths import models_root, ensure_roots
from app.tts.chatterbox_runtime import install_runtime, runtime_status, RUNTIME_DIR as CHATTERBOX_RUNTIME_DIR
from app.tts.model_registry import BUILTIN_CATALOG, installed_models, mark_installed
from app.tts.providers.piper import PiperProvider
from app.tts.providers.kokoro import KokoroProvider
from app.tts.qwen_character_runtime import (
    install_runtime as install_qwen_runtime,
    install_model as install_qwen_model,
    model_installed as qwen_model_installed,
    runtime_ready as qwen_runtime_ready,
    best_custom_kind,
    best_clone_kind,
    best_voice_design_kind,
    repair_runtime as repair_qwen_runtime,
    MODEL_DIRS as QWEN_MODEL_DIRS,
    RUNTIME_ROOT as QWEN_RUNTIME_ROOT,
    PYTHON_ROOT as QWEN_PYTHON_ROOT,
    VENV_ROOT as QWEN_VENV_ROOT,
    MARKER as QWEN_MARKER,
    INSTALLER_PATH as QWEN_INSTALLER_PATH,
    INSTALLER_LOG as QWEN_INSTALLER_LOG,
)
from app.ai.model_runtime import brain_root, install_runtime as install_audiobook_ai, recommended_model, self_test as test_audiobook_ai


KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"

def _file_ready(path: Path) -> bool:
    """Cheap integrity check for large local assets; never opens or loads the model."""
    try:
        return path.is_file() and path.stat().st_size >= 1024
    except OSError:
        return False


from app.ui.stable_refresh import stable_view_refresh


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

    def __init__(self, selection: str):
        super().__init__()
        self.selection = selection

    def run(self) -> None:
        try:
            self.progress.emit("Installing isolated Qwen3-TTS runtime…")
            install_qwen_runtime(self.progress.emit)

            choices = {
                "CustomVoice": [best_custom_kind()],
                "VoiceDesign": [best_voice_design_kind(), best_clone_kind()],
                "Voice Clone": [best_clone_kind()],
            }
            if self.selection == "Full Qwen Voice Studio":
                targets = []
                for kind in [
                    best_custom_kind(),
                    best_voice_design_kind(),
                    best_clone_kind(),
                ]:
                    if kind not in targets:
                        targets.append(kind)
            else:
                targets = choices[self.selection]

            for kind in targets:
                self.progress.emit(f"Preparing Qwen3-TTS {self.selection} model: {kind}…")
                install_qwen_model(kind, self.progress.emit)
            self.finished_ok.emit(
                f"{self.selection}|{','.join(targets)}"
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class QwenCacheResetWorker(QThread):
    finished_ok = Signal(int)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:
        try:
            count = reset_qwen_voice_cache(self.progress.emit)
            self.finished_ok.emit(count)
        except Exception as exc:
            self.failed.emit(str(exc))


class QwenRepairWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:
        try:
            self.progress.emit("Repairing isolated Qwen3-TTS runtime…")
            detail = repair_qwen_runtime(self.progress.emit)
            self.finished_ok.emit(detail)
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


class UninstallComponentWorker(QThread):
    """Remove one explicitly selected, app-managed local component."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, component_id: str):
        super().__init__()
        self.component_id = str(component_id)

    @staticmethod
    def _remove_path(target: Path, allowed_root: Path) -> None:
        root = Path(allowed_root).resolve()
        candidate = Path(target).resolve()
        # Do not delete the root itself, follow paths outside it, or touch
        # any user's Library/Voices/Audiobooks folders.
        if candidate == root or root not in candidate.parents:
            raise RuntimeError(
                f"Refusing to remove a path outside the selected component root: {target}"
            )
        if candidate.is_dir():
            shutil.rmtree(candidate)
        elif candidate.exists():
            candidate.unlink()

    def run(self) -> None:
        try:
            component_id = self.component_id
            root = models_root()

            if component_id.startswith("piper:"):
                relative_name = component_id.split(":", 1)[1]
                piper_root = root / "piper"
                candidate = (piper_root / relative_name).resolve()
                if piper_root.resolve() not in candidate.parents or candidate.suffix.lower() != ".onnx":
                    raise RuntimeError("Invalid Piper voice selection.")
                if not candidate.is_file():
                    raise RuntimeError("That user-installed Piper voice is no longer present.")
                self._remove_path(candidate, piper_root)
                sidecar = candidate.with_suffix(candidate.suffix + ".json")
                if sidecar.exists():
                    self._remove_path(sidecar, piper_root)
                mark_installed(
                    "piper",
                    piper_root.exists() and any(piper_root.rglob("*.onnx")),
                )

            elif component_id == "kokoro":
                self._remove_path(root / "kokoro", root)
                mark_installed("kokoro", False)

            elif component_id == "chatterbox-runtime":
                self._remove_path(CHATTERBOX_RUNTIME_DIR, root)
                mark_installed("chatterbox", False)
                mark_installed("chatterbox-multilingual", False)

            elif component_id.startswith("qwen-model:"):
                kind = component_id.split(":", 1)[1]
                if kind not in QWEN_MODEL_DIRS:
                    raise RuntimeError("Unknown Qwen model selection.")
                self._remove_path(QWEN_MODEL_DIRS[kind], QWEN_RUNTIME_ROOT)

            elif component_id == "qwen-runtime":
                # Preserve downloaded model folders, Hugging Face cache and
                # generated voice anchors; remove only the isolated Python runtime.
                for target in (
                    QWEN_VENV_ROOT,
                    QWEN_PYTHON_ROOT,
                    QWEN_MARKER,
                    QWEN_INSTALLER_PATH,
                    QWEN_INSTALLER_LOG,
                ):
                    if target.exists():
                        self._remove_path(target, QWEN_RUNTIME_ROOT)

            elif component_id == "audiobook-ai":
                self._remove_path(root / "audiobook-ai", root)

            else:
                raise RuntimeError("The selected item is not a removable installed component.")

            self.finished_ok.emit(component_id)
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
        self.qwen_repair_worker: QwenRepairWorker | None = None
        self.qwen_cache_worker: QwenCacheResetWorker | None = None
        self.audiobook_ai_worker: AudiobookAIInstallWorker | None = None
        self.uninstall_worker: UninstallComponentWorker | None = None
        self._active_operation: str | None = None
        self._operation_buttons: tuple[QPushButton, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(QLabel("<h2>Models & Voice Engines</h2>"))
        intro = QLabel(
            "Manage local narration voices and optional AI engines in one place. "
            "Removing a component keeps your books, generated audiobooks, voice profiles, "
            "and project settings. Models may need to be reinstalled before their profiles can be used again."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 8, 2)
        content_layout.setSpacing(12)

        installed_group = QGroupBox("Installed components")
        installed_layout = QVBoxLayout(installed_group)
        self.list = QListWidget()
        self.list.setMaximumHeight(205)
        self.list.setToolTip("Select one installed, app-managed component to uninstall.")
        self.list.currentItemChanged.connect(self._update_uninstall_button)
        installed_layout.addWidget(self.list)
        installed_actions = QHBoxLayout()
        self.uninstall_button = QPushButton("Uninstall selected component")
        self.uninstall_button.setEnabled(False)
        self.uninstall_button.clicked.connect(self.uninstall_selected_component)
        installed_actions.addWidget(self.uninstall_button)
        installed_actions.addStretch(1)
        installed_layout.addLayout(installed_actions)
        content_layout.addWidget(installed_group)

        self.install_kokoro = QPushButton("Download Natural Voices")
        self.install_piper = QPushButton("Download Piper Voice")
        self.install_chatterbox = QPushButton("Install / Repair Custom Voice Engine")
        self.install_qwen_character = QPushButton("Install / Repair Qwen Voice Studio")
        self.repair_qwen = QPushButton("Repair Qwen3-TTS Runtime")
        self.reset_qwen_cache = QPushButton("Reset Qwen Voice Cache")
        self.install_audiobook_ai = QPushButton("Install Audiobook AI")
        self.refresh_button = QPushButton("Refresh")

        voice_group = QGroupBox("Offline narration voices")
        voice_grid = QGridLayout(voice_group)
        voice_grid.addWidget(self.install_kokoro, 0, 0)
        voice_grid.addWidget(self.install_piper, 0, 1)
        content_layout.addWidget(voice_group)

        character_group = QGroupBox("Character voices & voice cloning")
        character_grid = QGridLayout(character_group)
        character_grid.addWidget(self.install_qwen_character, 0, 0)
        character_grid.addWidget(self.install_chatterbox, 0, 1)
        character_grid.addWidget(self.repair_qwen, 1, 0)
        character_grid.addWidget(self.reset_qwen_cache, 1, 1)
        content_layout.addWidget(character_group)

        ai_group = QGroupBox("Book analysis")
        ai_grid = QGridLayout(ai_group)
        ai_grid.addWidget(self.install_audiobook_ai, 0, 0)
        ai_grid.addWidget(self.refresh_button, 0, 1)
        content_layout.addWidget(ai_group)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.install_kokoro.clicked.connect(self.download_kokoro)
        self.install_piper.clicked.connect(self.download_piper)
        self.install_chatterbox.clicked.connect(self.install_chatterbox_runtime)
        self.install_qwen_character.clicked.connect(self.install_qwen_character_runtime)
        self.repair_qwen.clicked.connect(self.repair_qwen_runtime)
        self.reset_qwen_cache.clicked.connect(self.reset_qwen_voice_cache)
        self.install_audiobook_ai.clicked.connect(self.install_audiobook_ai_runtime)
        self.refresh_button.clicked.connect(self.refresh)
        self._operation_buttons = (
            self.install_kokoro,
            self.install_piper,
            self.install_chatterbox,
            self.install_qwen_character,
            self.repair_qwen,
            self.reset_qwen_cache,
            self.install_audiobook_ai,
            self.refresh_button,
        )
        self._update_operation_controls()
        self.status.setText("Model inventory loads when this screen opens.")


    @stable_view_refresh
    def refresh(self) -> None:
        selected = self.list.currentItem()
        selected_label = selected.text() if selected else None
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        scroll = self.list.verticalScrollBar()
        previous_scroll = scroll.value()
        desired_rows: list[tuple[str, str | None, str]] = []

        def add_component(label: str, component_id: str | None = None) -> None:
            tooltip = (
                "This item is bundled, not installed separately, or not currently removable."
                if component_id is None else ""
            )
            desired_rows.append((label, component_id, tooltip))

        piper_root = models_root() / "piper"
        user_voices = [
            voice for voice in PiperProvider.model_paths()
            if piper_root.resolve() in voice.resolve().parents
        ]
        if user_voices:
            for voice in user_voices:
                relative = voice.resolve().relative_to(piper_root.resolve()).as_posix()
                add_component(f"Piper voice • {voice.stem} — Installed", f"piper:{relative}")
        elif PiperProvider.model_paths():
            add_component("Piper voice — bundled with the application (managed by installer)")
        else:
            add_component("Piper — no local voice installed")

        # Only files in the user Models folder are removable here. A bundled
        # Kokoro pack ships inside the application and must not offer an uninstall
        # button that appears to succeed but cannot remove the bundled assets.
        local_kokoro_root = models_root() / "kokoro"
        try:
            local_kokoro_present = (
                local_kokoro_root.is_dir()
                and any(path.is_file() for path in local_kokoro_root.iterdir())
            )
        except OSError:
            local_kokoro_present = True
        local_kokoro_models = [
            path for path in local_kokoro_root.glob("*.onnx")
        ] if local_kokoro_root.is_dir() else []
        local_kokoro_voicepacks = [
            local_kokoro_root / "voices-v1.0.bin",
            local_kokoro_root / "voices.bin",
        ]
        local_kokoro_ready = (
            any(_file_ready(path) for path in local_kokoro_models)
            and any(_file_ready(path) for path in local_kokoro_voicepacks)
        )
        if local_kokoro_ready:
            add_component(
                f"Kokoro 82M — User-installed • {len(KokoroProvider().voices())} voices available",
                "kokoro",
            )
        elif local_kokoro_present:
            add_component("Kokoro 82M — Incomplete • retry download or remove partial files", "kokoro")
        elif KokoroProvider.assets_available():
            add_component("Kokoro 82M — Bundled with application (not individually removable)")
        else:
            add_component("Kokoro 82M — Not installed")

        chat_status = runtime_status()
        if CHATTERBOX_RUNTIME_DIR.exists():
            add_component(f"Chatterbox voice engine — {chat_status}", "chatterbox-runtime")
        else:
            add_component(f"Chatterbox voice engine — {chat_status}")

        qwen_labels = {
            "custom-0.6b": "CustomVoice 0.6B",
            "custom-1.7b": "CustomVoice 1.7B",
            "design-1.7b": "VoiceDesign 1.7B",
            "base-0.6b": "Voice Clone Base 0.6B",
            "base-1.7b": "Voice Clone Base 1.7B",
        }
        any_qwen_model = False
        for kind in QWEN_MODEL_DIRS:
            if qwen_model_installed(kind):
                any_qwen_model = True
                add_component(
                    f"Qwen3-TTS • {qwen_labels.get(kind, kind)} — Installed",
                    f"qwen-model:{kind}",
                )
        if not any_qwen_model:
            add_component("Qwen3-TTS Voice Studio — no model installed")

        qwen_runtime_present = any(
            path.exists()
            for path in (
                QWEN_RUNTIME_ROOT, QWEN_VENV_ROOT, QWEN_PYTHON_ROOT,
                QWEN_MARKER, QWEN_INSTALLER_PATH, QWEN_INSTALLER_LOG,
            )
        )
        if qwen_runtime_ready():
            add_component("Qwen3-TTS Python runtime — Ready", "qwen-runtime")
        elif qwen_runtime_present:
            add_component("Qwen3-TTS Python runtime — Incomplete • repair required", "qwen-runtime")
        else:
            add_component("Qwen3-TTS Python runtime — Not installed")

        # Use cheap filesystem checks here. The full readiness helper invokes
        # recommended_model(), which can launch nvidia-smi; that must not run
        # from the Qt refresh path because a missing/slow driver can freeze UI.
        ai_root = models_root() / "audiobook-ai"
        try:
            ai_root_present = ai_root.is_dir() and any(ai_root.iterdir())
        except OSError:
            ai_root_present = True
        ai_server = ai_root / "llama-server.exe"
        ai_models = (
            ai_root / "Qwen3-1.7B-Q5_K_M.gguf",
            ai_root / "Qwen3-4B-Q4_K_M.gguf",
        )
        ai_ready = _file_ready(ai_server) and any(_file_ready(path) for path in ai_models)
        if ai_ready:
            add_component("Audiobook AI — Ready (local runtime and model files present)", "audiobook-ai")
        elif ai_root_present:
            add_component("Audiobook AI — Incomplete • install/repair required", "audiobook-ai")
        else:
            add_component("Audiobook AI — Not installed")

        was_blocked = self.list.blockSignals(True)
        updates_were_enabled = self.list.updatesEnabled()
        if updates_were_enabled:
            self.list.setUpdatesEnabled(False)
        try:
            # Reuse existing rows in their current order. The previous clear/add
            # cycle discarded selection and item data every time inventory refreshed.
            for index, (label, component_id, tooltip) in enumerate(desired_rows):
                if index < self.list.count():
                    item = self.list.item(index)
                    if item.text() != label:
                        item.setText(label)
                    if item.data(Qt.ItemDataRole.UserRole) != component_id:
                        item.setData(Qt.ItemDataRole.UserRole, component_id)
                    if item.toolTip() != tooltip:
                        item.setToolTip(tooltip)
                else:
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, component_id)
                    item.setToolTip(tooltip)
                    self.list.addItem(item)

            while self.list.count() > len(desired_rows):
                self.list.takeItem(self.list.count() - 1)

            target_row = -1
            for index, (label, component_id, _tooltip) in enumerate(desired_rows):
                if selected_id is not None and component_id == selected_id:
                    target_row = index
                    break
                if selected_id is None and selected_label == label and component_id is None:
                    target_row = index
                    break
            self.list.setCurrentRow(target_row)
        finally:
            self.list.blockSignals(was_blocked)
            if updates_were_enabled:
                self.list.setUpdatesEnabled(True)
            scroll.setValue(
                min(max(previous_scroll, scroll.minimum()), scroll.maximum())
            )
            if updates_were_enabled:
                self.list.viewport().update()

        self._update_uninstall_button()
        self.status.setText("Model inventory refreshed from this PC.")

    def _update_operation_controls(self) -> None:
        """Allow only one model/runtime mutation at a time in the desktop UI."""
        busy = self._active_operation is not None
        for button in self._operation_buttons:
            button.setEnabled(not busy)
        if hasattr(self, "list"):
            self.list.setEnabled(not busy)
        self._update_uninstall_button()

    def _begin_operation(self, label: str) -> bool:
        """Acquire the single-flight model operation slot before starting a worker."""
        if self._active_operation is not None:
            self.status.setText(
                f"Cannot start {label}: {self._active_operation} is still running. "
                "Wait for it to finish, then retry."
            )
            return False
        self._active_operation = label
        self._update_operation_controls()
        return True

    def _end_operation(self, *_args) -> None:
        """Release the model operation slot after a worker fully exits."""
        if self._active_operation is None:
            return
        self._active_operation = None
        self._update_operation_controls()

    def _update_uninstall_button(self, *_args) -> None:
        item = self.list.currentItem() if hasattr(self, "list") else None
        component_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        running = bool(self.uninstall_worker and self.uninstall_worker.isRunning())
        busy = getattr(self, "_active_operation", None) is not None
        if hasattr(self, "uninstall_button"):
            self.uninstall_button.setEnabled(bool(component_id) and not running and not busy)

    def uninstall_selected_component(self) -> None:
        item = self.list.currentItem()
        component_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not component_id:
            self.status.setText("Select an installed, removable component first.")
            return
        answer = QMessageBox.question(
            self,
            "Uninstall selected component",
            f"Remove {item.text()}?\n\n"
            "Only the selected app-managed component will be removed. The Library, source books, "
            "generated audiobooks, projects, voice profiles, and settings will be kept. "
            "If another profile uses this model, reinstall it before generating with that profile.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._begin_operation(f"Uninstall {item.text()}"):
            return
        self.status.setText(f"Uninstalling {item.text()}…")
        self.uninstall_worker = UninstallComponentWorker(str(component_id))
        self.uninstall_worker.finished.connect(self._end_operation)
        self.uninstall_worker.finished_ok.connect(self._uninstall_component_ok)
        self.uninstall_worker.failed.connect(self._uninstall_component_failed)
        self.uninstall_worker.finished.connect(self._update_uninstall_button)
        self.uninstall_worker.start()

    def _uninstall_component_ok(self, component_id: str) -> None:
        self.refresh()
        self.status.setText(f"Removed component: {component_id}")
        self._update_uninstall_button()

    def _uninstall_component_failed(self, message: str) -> None:
        self.status.setText("Uninstall failed. Unrelated files were not intentionally removed.")
        QMessageBox.warning(self, "Uninstall failed", message)
        self._update_uninstall_button()

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
        if not self._begin_operation("download Kokoro natural voices"):
            return
        self.status.setText("Preparing Kokoro natural voices…")
        self.kokoro_worker = KokoroDownloadWorker()
        self.kokoro_worker.finished.connect(self._end_operation)
        self.kokoro_worker.finished_ok.connect(self._kokoro_ok)
        self.kokoro_worker.failed.connect(self._kokoro_failed)
        self.kokoro_worker.progress.connect(self.status.setText)
        self.kokoro_worker.start()

    def _kokoro_ok(self) -> None:
        self.status.setText("Kokoro natural offline voices installed.")
        self.refresh()

    def _kokoro_failed(self, message: str) -> None:
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

        if not self._begin_operation(f"download Piper voice {voice.strip()}"):
            return
        self.status.setText(f"Downloading {voice.strip()}...")
        self.worker = PiperDownloadWorker(voice.strip())
        self.worker.finished.connect(self._end_operation)
        self.worker.finished_ok.connect(self._download_ok)
        self.worker.failed.connect(self._download_failed)
        self.worker.start()

    def _download_ok(self, voice: str) -> None:
        self.status.setText(f"Installed Piper voice: {voice}")
        self.refresh()

    def _download_failed(self, message: str) -> None:
        self.status.setText("Download failed")
        QMessageBox.warning(self, "Piper Download Failed", message)

    def install_qwen_character_runtime(self) -> None:
        choices = [
            "CustomVoice",
            "VoiceDesign",
            "Voice Clone",
            "Full Qwen Voice Studio",
        ]
        selection, ok = QInputDialog.getItem(
            self,
            "Install Qwen Voice Studio",
            "Choose the Qwen3-TTS phase to install:",
            choices,
            0,
            False,
        )
        if not ok:
            return
        if not self._begin_operation(f"install Qwen {selection}"):
            return
        self.status.setText(f"Preparing Qwen {selection}…")
        self.qwen_character_worker = QwenCharacterInstallWorker(selection)
        self.qwen_character_worker.finished.connect(self._end_operation)
        self.qwen_character_worker.finished_ok.connect(self._qwen_character_ok)
        self.qwen_character_worker.failed.connect(self._qwen_character_failed)
        self.qwen_character_worker.progress.connect(self.status.setText)
        self.qwen_character_worker.start()

    def _qwen_character_ok(self, detail: str) -> None:
        parts = detail.split("|", 1)
        selection = parts[0]
        models = parts[1] if len(parts) > 1 else ""
        self.status.setText(
            f"Qwen {selection} installed • {models}. "
            "Return to Voice & Narration to preview the selected phase."
        )
        self.refresh()

    def _qwen_character_failed(self, message: str) -> None:
        self.status.setText("Offline character voice installation failed.")
        QMessageBox.warning(self, "Offline Character Voice Installation Failed", message)

    def reset_qwen_voice_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset Qwen Voice Cache",
            "This removes only generated Qwen VoiceDesign reference-cache audio. "
            "Downloaded Qwen models and saved voice profiles are kept. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._begin_operation("reset Qwen voice cache"):
            return
        self.status.setText("Resetting generated Qwen voice cache…")
        self.qwen_cache_worker = QwenCacheResetWorker()
        self.qwen_cache_worker.finished.connect(self._end_operation)
        self.qwen_cache_worker.progress.connect(self.status.setText)
        self.qwen_cache_worker.finished_ok.connect(self._qwen_cache_reset_ok)
        self.qwen_cache_worker.failed.connect(self._qwen_cache_reset_failed)
        self.qwen_cache_worker.start()

    def _qwen_cache_reset_ok(self, count: int) -> None:
        self.status.setText(f"Qwen voice cache reset • removed {count} generated reference file(s).")
        self.refresh()

    def _qwen_cache_reset_failed(self, message: str) -> None:
        self.status.setText("Qwen voice cache reset failed; saved profiles and downloaded models were kept.")
        QMessageBox.warning(self, "Qwen Voice Cache Reset Failed", message)

    def repair_qwen_runtime(self) -> None:
        answer = QMessageBox.question(
            self,
            "Repair Qwen3-TTS Runtime",
            "This will rebuild Ryu's isolated Qwen3-TTS Python environment and reinstall "
            "PyTorch, torchaudio and qwen-tts. Your downloaded Qwen model files will NOT be deleted. "
            "Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._begin_operation("repair Qwen3-TTS runtime"):
            return
        self.status.setText("Repairing Qwen3-TTS runtime…")
        self.qwen_repair_worker = QwenRepairWorker()
        self.qwen_repair_worker.finished.connect(self._end_operation)
        self.qwen_repair_worker.finished_ok.connect(self._qwen_repair_ok)
        self.qwen_repair_worker.failed.connect(self._qwen_repair_failed)
        self.qwen_repair_worker.progress.connect(self.status.setText)
        self.qwen_repair_worker.start()

    def _qwen_repair_ok(self, detail: str) -> None:
        self.status.setText(f"Qwen3-TTS runtime repaired and verified • {detail}")
        self.refresh()

    def _qwen_repair_failed(self, message: str) -> None:
        self.status.setText("Qwen3-TTS runtime repair failed.")
        QMessageBox.warning(self, "Qwen3-TTS Runtime Repair Failed", message)

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
        if not self._begin_operation("install Audiobook AI"):
            return
        self.status.setText("Installing local Audiobook AI…")
        self.audiobook_ai_worker = AudiobookAIInstallWorker()
        self.audiobook_ai_worker.finished.connect(self._end_operation)
        self.audiobook_ai_worker.finished_ok.connect(self._audiobook_ai_ok)
        self.audiobook_ai_worker.failed.connect(self._audiobook_ai_failed)
        self.audiobook_ai_worker.progress.connect(self.status.setText)
        self.audiobook_ai_worker.start()

    def _audiobook_ai_ok(self, detail: str) -> None:
        parts = detail.split("|", 3)
        result = parts[3] if len(parts) > 3 else "ready"
        self.status.setText(f"Audiobook AI installed and self-tested successfully • {result}")
        self.refresh()

    def _audiobook_ai_failed(self, message: str) -> None:
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
        if not self._begin_operation("install Chatterbox custom voice engine"):
            return
        self.status.setText("Installing Chatterbox custom voice engine…")
        self.chatterbox_worker = ChatterboxInstallWorker()
        self.chatterbox_worker.finished.connect(self._end_operation)
        self.chatterbox_worker.finished_ok.connect(self._chatterbox_ok)
        self.chatterbox_worker.failed.connect(self._chatterbox_failed)
        self.chatterbox_worker.progress.connect(self.status.setText)
        self.chatterbox_worker.start()

    def _chatterbox_ok(self, name: str) -> None:
        self.status.setText("Custom voice engine installed. Its model will download when first used.")
        self.refresh()

    def _chatterbox_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Custom Voice Engine Installation Failed", message)
        self.status.setText("Custom voice engine installation failed.")
