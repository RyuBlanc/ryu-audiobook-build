from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QLineEdit, QProgressBar

from app.audio.assembler import assemble_m4b

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

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        layout.addWidget(self.progress)

        self.build_button = QPushButton("Build M4B Audiobook")
        self.build_button.clicked.connect(self.build)
        layout.addWidget(self.build_button)
        self.status = QLabel("")
        layout.addWidget(self.status)

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
        self.status.setText("Assembling audiobook...")
        try:
            assemble_m4b(self.chapter_dirs, self.output_path, self.title.text().strip() or "Audiobook", self.author.text().strip(), self.cover_path)
            self.progress.setValue(1)
            self.status.setText(f"Created: {self.output_path}")
        except Exception as exc:
            self.status.setText(f"Assembly failed: {exc}")
