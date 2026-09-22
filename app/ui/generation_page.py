from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget, QComboBox
)

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.providers.piper import PiperProvider
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.benchmark import benchmark_provider
from app.hardware.backend import detect_hardware


class GenerationSignals(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)


class GenerationPage(QWidget):
    def __init__(self, chapters: list[Chapter], audio_root: Path) -> None:
        super().__init__()
        self.chapters = chapters
        self.audio_root = audio_root
        self.signals = GenerationSignals()
        self.manager: GenerationManager | None = None
        self.hardware = detect_hardware()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Generate Audiobook</h2>"))

        form = QFormLayout()
        self.title = QLineEdit("Audiobook")
        self.author = QLineEdit()
        form.addRow("Title:", self.title)
        form.addRow("Author:", self.author)
        layout.addLayout(form)

        self.model = QComboBox()
        self.model.addItem("Windows SAPI (offline fallback)", "sapi")
        if PiperProvider.model_paths():
            self.model.addItem("Piper", "piper")
        form.addRow("TTS Model:", self.model)

        self.voice = QComboBox()
        self.voice.setEditable(True)
        self.voice.addItem("Default")
        self._refresh_voices()
        form.addRow("Voice:", self.voice)

        self.backend = QComboBox()
        self.backend.addItem("Automatic", "automatic")
        for info in self.hardware.backends:
            if info.available:
                self.backend.addItem(info.name, info.name)
        form.addRow("Backend:", self.backend)

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
        self.model.currentIndexChanged.connect(self._refresh_voices)

    def _refresh_voices(self):
        current = self.voice.currentText() if self.voice.count() else ""
        self.voice.clear()
        model = self.model.currentData()
        if model == "piper":
            names = PiperProvider().voices()
            self.voice.addItems(names)
        else:
            self.voice.addItem("Default")
        if current:
            index = self.voice.findText(current)
            if index >= 0:
                self.voice.setCurrentIndex(index)

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
        model = self.model.currentData()
        if model == "piper":
            backend = self.backend.currentData()
            use_backend = "cuda" if backend == "NVIDIA CUDA" else "cpu"
            return PiperProvider(backend=use_backend), self.voice.currentText().strip() or None
        return SystemSAPIProvider(), self.voice.currentText().strip() or None

    def preview(self):
        provider, voice = self._provider()
        text = (
            "Welcome to Ryu's Audiobook. This is a local voice preview. "
            "The selected engine will be used for audiobook generation."
        )
        try:
            import tempfile
            output = Path(tempfile.gettempdir()) / "ryu_audiobook_tts_preview.wav"
            provider.synthesize(text, output, voice)
            result = benchmark_provider(provider, voice, self.backend.currentData() or "automatic")
            if result.success:
                self.status.setText(
                    f"Preview ready: {output.name} • {result.seconds:.2f}s generation for "
                    f"{result.audio_seconds:.2f}s audio"
                )
            else:
                self.status.setText(f"Preview ready: {output.name}")
        except Exception as exc:
            self.status.setText(f"Preview failed: {exc}")

    def start(self) -> None:
        if not self.chapters:
            self.status.setText("No chapters available.")
            return
        output = Path(self.output.text().strip()) if self.output.text().strip() else None
        if output is None:
            self.status.setText("Choose an M4B output file.")
            return

        provider, voice = self._provider()
        if self.model.currentData() == "sapi" and not voice:
            self.status.setText("Select a Windows SAPI voice.")
            return

        self.progress.setRange(0, len(self.chapters))
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Generating...")

        self.manager = GenerationManager(
            provider,
            voice,
            self.chapters,
            self.audio_root,
            on_progress=lambda *args: self.signals.progress.emit(*args),
            on_finished=lambda summary: self.signals.finished.emit(summary),
        )
        self.manager.start(output, self.title.text().strip(), self.author.text().strip(), self.cover)

    def cancel(self) -> None:
        if self.manager:
            self.manager.cancel()
            self.status.setText("Cancelling after the current chunk...")

    def update_progress(self, chapter: int, total: int, done: int, message: str) -> None:
        self.progress.setValue(chapter if message == "chapter-complete" else max(0, chapter - 1))
        self.status.setText(f"Chapter {chapter}/{total} — {message}")

    def finished(self, summary: GenerationSummary) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if summary.output_path:
            self.status.setText(f"Finished: {summary.output_path}")
        elif summary.chapters_failed:
            self.status.setText(f"Finished with failures: {summary.chapters_failed}")
        else:
            self.status.setText(f"Stopped: {summary.chapters_completed}/{summary.chapters_total} chapters")
