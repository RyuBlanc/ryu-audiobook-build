from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.system_sapi import SystemSAPIProvider

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

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Generate Audiobook"))

        form = QFormLayout()
        self.title = QLineEdit("Audiobook")
        self.author = QLineEdit()
        form.addRow("Title:", self.title)
        form.addRow("Author:", self.author)
        layout.addLayout(form)

        self.voice = QLineEdit()
        self.voice.setPlaceholderText("Windows SAPI voice ID")
        layout.addWidget(QLabel("Voice ID"))
        layout.addWidget(self.voice)

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

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save M4B", "", "M4B Audiobook (*.m4b)")
        if path:
            self.output.setText(path)

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Cover", "", "Images (*.jpg *.jpeg *.png)")
        if path:
            self.cover = Path(path)
            self.status.setText(f"Cover: {self.cover.name}")

    def start(self) -> None:
        if not self.chapters:
            self.status.setText("No chapters available.")
            return
        output = Path(self.output.text().strip()) if self.output.text().strip() else None
        if output is None:
            self.status.setText("Choose an M4B output file.")
            return
        voice = self.voice.text().strip()
        if not voice:
            self.status.setText("Enter a Windows SAPI voice ID.")
            return

        self.progress.setRange(0, len(self.chapters))
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Generating...")

        self.manager = GenerationManager(
            SystemSAPIProvider(),
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
        self.progress.setValue(chapter - 1 if message != "chapter-complete" else chapter)
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
