from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QFileDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QLineEdit

from app.audio.assembler import assemble_m4b
from app.ui.motion import SmoothProgressBar


class AssemblyWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, chapter_dirs, output_path, title, author, cover_path):
        super().__init__()
        self.chapter_dirs = chapter_dirs
        self.output_path = output_path
        self.title = title
        self.author = author
        self.cover_path = cover_path

    def run(self):
        try:
            assemble_m4b(
                self.chapter_dirs,
                self.output_path,
                self.title,
                self.author,
                self.cover_path,
            )
            self.finished_ok.emit(str(self.output_path))
        except Exception as exc:
            self.failed.emit(str(exc))

class AssemblyPage(QWidget):
    def __init__(self, chapter_dirs: list[Path] | None = None) -> None:
        super().__init__()
        self.chapter_dirs = chapter_dirs or []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Audiobook Assembly"))

        form = QFormLayout()
        self.title = QLineEdit()
        self.author = QLineEdit()
        form.addRow("Book title:", self.title)
        form.addRow("Author:", self.author)
        layout.addLayout(form)

        self.cover = QLabel("No cover selected")
        self.cover_path: Path | None = None
        cover_button = QPushButton("Select Cover")
        cover_button.clicked.connect(self.select_cover)
        layout.addWidget(cover_button)
        layout.addWidget(self.cover)

        self.output = QLabel("No output selected")
        self.output_path: Path | None = None
        output_button = QPushButton("Choose M4B Output")
        output_button.clicked.connect(self.select_output)
        layout.addWidget(output_button)
        layout.addWidget(self.output)

        self.progress = SmoothProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.activity = SmoothProgressBar()
        self.activity.setRange(0, 0)
        self.activity.setTextVisible(False)
        self.activity.setFixedHeight(4)
        self.activity.setVisible(False)
        layout.addWidget(self.activity)
        self.stats = QLabel("Ready • Elapsed 0:00")
        layout.addWidget(self.stats)

        self.build_button = QPushButton("Build M4B Audiobook")
        self.build_button.clicked.connect(self.build)
        layout.addWidget(self.build_button)
        self.status = QLabel("")
        layout.addWidget(self.status)
        self.worker: AssemblyWorker | None = None
        self.started_at: float | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_stats)

    def select_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Cover", "", "Images (*.jpg *.jpeg *.png)")
        if path:
            self.cover_path = Path(path)
            self.cover.setText(self.cover_path.name)

    def select_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Audiobook", "", "M4B Audiobook (*.m4b)")
        if path:
            self.output_path = Path(path)
            self.output.setText(str(self.output_path))

    def build(self) -> None:
        if not self.chapter_dirs or not self.output_path:
            self.status.setText("Generate chapter audio and choose an output file first.")
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.build_button.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.activity.setVisible(True)
        self.started_at = time.monotonic()
        self.timer.start()
        self.stats.setText("Packaging M4B • Elapsed 0:00 • ETA unavailable")
        self.status.setText("Packaging audiobook in the background…")
        self.worker = AssemblyWorker(
            self.chapter_dirs,
            self.output_path,
            self.title.text().strip() or "Audiobook",
            self.author.text().strip(),
            self.cover_path,
        )
        self.worker.finished_ok.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _update_stats(self) -> None:
        if self.started_at is None:
            return
        elapsed = max(0, int(time.monotonic() - self.started_at))
        self.stats.setText(
            f"Packaging M4B • Elapsed {elapsed // 60}:{elapsed % 60:02d} • ETA unavailable"
        )

    def _finished(self, output_path: str) -> None:
        self.timer.stop()
        self.activity.setVisible(False)
        self.progress.setValue(1)
        self.stats.setText("Packaging complete")
        self.status.setText(f"Created: {output_path}")
        self.build_button.setEnabled(True)

    def _failed(self, message: str) -> None:
        self.timer.stop()
        self.activity.setVisible(False)
        self.progress.setValue(0)
        self.stats.setText("Packaging failed")
        self.status.setText(f"Assembly failed: {message}")
        self.build_button.setEnabled(True)

    def _worker_finished(self) -> None:
        self.worker = None
