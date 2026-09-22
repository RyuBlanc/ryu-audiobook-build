from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget, QComboBox
)

from app.chapters.detector import Chapter
from app.core.state import load_state, save_state
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import load_profiles, VoiceProfile
from app.tts.providers.piper import PiperProvider
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.benchmark import benchmark_provider


class GenerationSignals(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)


class GenerationPage(QWidget):
    def __init__(self, chapters: list[Chapter], audio_root: Path, project_folder: Path | None = None) -> None:
        super().__init__()
        self.chapters = chapters
        self.audio_root = audio_root
        self.project_folder = project_folder
        self.profiles = load_profiles()
        self.signals = GenerationSignals()
        self.manager: GenerationManager | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Generate Audiobook</h2>"))

        form = QFormLayout()
        self.title = QLineEdit("Audiobook")
        self.author = QLineEdit()
        form.addRow("Title:", self.title)
        form.addRow("Author:", self.author)
        layout.addLayout(form)

        self.voice_profile = QComboBox()
        self._load_profiles()
        form.addRow("Voice Profile:", self.voice_profile)

        self.backend = QComboBox()
        self.backend.addItem("Automatic", "automatic")
        self.backend.addItem("CPU Only", "cpu")
        self.backend.addItem("NVIDIA CUDA", "cuda")
        self.backend.addItem("DirectML", "directml")
        form.addRow("Backend Override:", self.backend)

        self.preview_button = QPushButton("Generate Voice Preview")
        self.preview_button.clicked.connect(self.preview)
        layout.addWidget(self.preview_button)

        self.output = QLineEdit()
        output_button = QPushButton("Choose M4B Output")
        output_button.clicked.connect(self.choose_output)
        layout.addWidget(output_button)
        layout.addWidget(self.output)

        self.cover: Path | None = None
        cover_button = QPushButton("Choose Cover")
        cover_button.clicked.connect(self.choose_cover)
        layout.addWidget(cover_button)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        self.start_button = QPushButton("Generate Audiobook")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.start_button)
        layout.addWidget(self.cancel_button)

        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.finished)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)

        self._restore_state()

    def _load_profiles(self):
        self.voice_profile.clear()
        for profile in self.profiles:
            self.voice_profile.addItem(profile.name, profile)
        if not self.profiles:
            self.voice_profile.addItem("No saved voice profiles", None)

    def _restore_state(self):
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        profile_name = state.get("voice_profile")
        if profile_name:
            index = self.voice_profile.findText(profile_name)
            if index >= 0:
                self.voice_profile.setCurrentIndex(index)
        output = state.get("output_path")
        if output:
            self.output.setText(str(output))
        cover = state.get("cover_path")
        if cover:
            self.cover = Path(cover)

    def _selected_profile(self) -> VoiceProfile | None:
        value = self.voice_profile.currentData()
        return value if isinstance(value, VoiceProfile) else None

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save M4B", "", "M4B Audiobook (*.m4b)")
        if path:
            self.output.setText(path)

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Cover", "", "Images (*.jpg *.jpeg *.png)")
        if path:
            self.cover = Path(path)
            self.status.setText(f"Cover: {self.cover.name}")

    def _provider(self):
        profile = self._selected_profile()
        if not profile:
            return None, None
        backend = self.backend.currentData() or profile.backend
        if backend == "automatic":
            backend = profile.backend
        if profile.provider == "piper":
            return PiperProvider(backend="cuda" if backend == "cuda" else "cpu"), profile.voice_id
        if profile.provider == "windows-sapi":
            return SystemSAPIProvider(), profile.voice_id
        provider, voice = provider_from_profile(profile)
        if hasattr(provider, "backend"):
            provider.backend = backend
        return provider, voice

    def preview(self):
        provider, voice = self._provider()
        if not provider:
            self.status.setText("Create or select a Voice Profile first.")
            return
        text = (
            "Welcome to Ryu's Audiobook. This is a voice preview. "
            "The selected voice profile will be used for audiobook generation."
        )
        try:
            import tempfile
            output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"
            provider.synthesize(text, output, voice)
            result = benchmark_provider(provider, voice, self.backend.currentData() or "automatic")
            self.status.setText(
                f"Preview ready: {output.name} • {result.seconds:.2f}s generation "
                f"for {result.audio_seconds:.2f}s audio"
                if result.success else f"Preview ready: {output.name}"
            )
        except Exception as exc:
            self.status.setText(f"Preview failed: {exc}")

    def start(self):
        if not self.chapters:
            self.status.setText("No chapters available.")
            return
        output = Path(self.output.text().strip()) if self.output.text().strip() else None
        if output is None:
            self.status.setText("Choose an M4B output file.")
            return
        provider, voice = self._provider()
        if not provider:
            self.status.setText("Select a Voice Profile.")
            return

        if self.project_folder:
            state = load_state(self.project_folder)
            profile = self._selected_profile()
            state.update({
                "voice_profile": profile.name if profile else None,
                "output_path": str(output),
                "cover_path": str(self.cover) if self.cover else None,
                "status": "generating",
            })
            save_state(self.project_folder, state)

        self.progress.setRange(0, len(self.chapters))
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Generating...")

        self.manager = GenerationManager(
            provider, voice, self.chapters, self.audio_root,
            on_progress=lambda *args: self.signals.progress.emit(*args),
            on_finished=lambda summary: self.signals.finished.emit(summary),
        )
        self.manager.start(output, self.title.text().strip(), self.author.text().strip(), self.cover)

    def cancel(self):
        if self.manager:
            self.manager.cancel()
            self.status.setText("Cancelling after the current chunk...")

    def update_progress(self, chapter, total, done, message):
        self.progress.setValue(chapter if message == "chapter-complete" else max(0, chapter - 1))
        self.status.setText(f"Chapter {chapter}/{total} — {message}")

    def finished(self, summary: GenerationSummary):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.project_folder:
            state = load_state(self.project_folder)
            state["status"] = "completed" if summary.output_path else ("failed" if summary.chapters_failed else "cancelled")
            state["completed_chapters"] = list(range(1, summary.chapters_completed + 1))
            state["failed_chapters"] = summary.chapters_failed
            save_state(self.project_folder, state)
        if summary.output_path:
            self.status.setText(f"Finished: {summary.output_path}")
        elif summary.chapters_failed:
            self.status.setText(f"Finished with failures: {summary.chapters_failed}")
        else:
            self.status.setText(f"Stopped: {summary.chapters_completed}/{summary.chapters_total} chapters")
