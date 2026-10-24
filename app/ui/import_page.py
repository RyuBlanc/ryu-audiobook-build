from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.chapters.detector import detect_chapters
from app.documents.parser import extract_text, validate_chapter_text_coverage


class ImportPreviewWorker(QThread):
    """Extract and validate a source file off the UI thread before project creation."""

    ready = Signal(object, object)
    failed = Signal(str)
    status = Signal(str)
    progress = Signal(int)

    def __init__(self, source_path: Path) -> None:
        super().__init__()
        self.source_path = Path(source_path)

    def run(self) -> None:
        try:
            # Extraction and chapter detection do not expose a reliable byte/page
            # fraction. Show a true indeterminate animation and actual worker phases.
            self.progress.emit(-1)
            self.status.emit(f"Reading {self.source_path.name}…")
            book = extract_text(self.source_path)
            if not str(book.text or "").strip():
                raise RuntimeError("No readable text was extracted from this file.")
            self.status.emit(f"Detecting chapters in {self.source_path.name}…")
            chapters = detect_chapters(book.text)
            if not chapters:
                raise RuntimeError("No readable chapters were found in this file.")
            self.status.emit(f"Checking extracted text and chapter coverage for {self.source_path.name}…")
            try:
                validate_chapter_text_coverage(book.text, chapters, minimum=0.90)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            self.status.emit(f"Preparing the verified preview for {self.source_path.name}…")
            self.ready.emit(book, chapters)
        except Exception as exc:
            self.failed.emit(str(exc))


class BookDropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("importDropZone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event) -> None:
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        valid = [str(path) for path in paths if path.is_file()]
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if valid:
            self.files_dropped.emit(valid)
            event.acceptProposedAction()
        else:
            event.ignore()


class ImportPage(QWidget):
    def __init__(self, on_import=None) -> None:
        super().__init__()
        self.on_import = on_import
        self.source_path: Path | None = None
        self.book = None
        self.chapters = None
        self.worker: ImportPreviewWorker | None = None

        # Keep the complete import workflow reachable on shorter displays.
        # The scroll area contains the existing real controls; it does not replace
        # the import logic or alter the drop/browse/create-project callbacks.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setObjectName("importScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 6, 8, 14)
        root.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        title = QLabel("Import Studio")
        title.setObjectName("pageHeading")
        root.addWidget(title)
        subtitle = QLabel(
            "Bring a supported book into your local library. Review extraction before creating the project."
        )
        subtitle.setObjectName("pageSubheading")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.drop_zone = BookDropZone()
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(24, 24, 24, 24)
        drop_layout.setSpacing(10)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_mark = QLabel("↓")
        self.drop_mark.setObjectName("importDropIcon")
        self.drop_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.drop_mark)
        drop_title = QLabel("Drop your book here")
        drop_title.setObjectName("dropTitle")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_title)
        drop_hint = QLabel("Or browse your PC to select a supported file")
        drop_hint.setObjectName("muted")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_hint)
        self.button = QPushButton("Browse Files")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.choose_book)
        drop_layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        formats = QHBoxLayout()
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for fmt in ("EPUB", "PDF", "TXT", "DOCX"):
            tag = QLabel(fmt)
            tag.setObjectName("formatTag")
            formats.addWidget(tag)
        drop_layout.addLayout(formats)
        self.drop_zone.files_dropped.connect(self._drop_files)
        root.addWidget(self.drop_zone)

        self.info = QLabel("Your source file remains in your chosen location; project data is stored locally.")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        result_group = QGroupBox("Extraction Preview")
        result_layout = QVBoxLayout(result_group)
        self.summary = QLabel("Select a book to preview its extracted text and chapter boundaries.")
        self.summary.setWordWrap(True)
        result_layout.addWidget(self.summary)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Extracted text preview will appear here after analysis.")
        self.preview.setMinimumHeight(150)
        result_layout.addWidget(self.preview, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        result_layout.addWidget(self.progress)
        status_row = QHBoxLayout()
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        status_row.addWidget(self.status, 1)
        self.create_button = QPushButton("Create Local Project")
        self.create_button.setObjectName("primary")
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self.create_project)
        status_row.addWidget(self.create_button)
        result_layout.addLayout(status_row)
        root.addWidget(result_group, 1)

    def choose_book(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Book",
            "",
            "Books (*.pdf *.epub *.txt *.docx);;PDF (*.pdf);;EPUB (*.epub);;Text (*.txt);;Word (*.docx)",
        )
        if path:
            self._begin_analysis(Path(path))

    def _drop_files(self, paths: list[str]) -> None:
        if not paths:
            return
        if len(paths) != 1:
            self.status.setText("Drop one book at a time so each import can be checked before project creation.")
            return
        self._begin_analysis(Path(paths[0]))

    def _begin_analysis(self, path: Path) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status.setText("Another book is still being analysed. Wait for it to finish before selecting another.")
            return

        # Clear the previous preview before validating the new selection so a
        # failed/unsupported file cannot leave old book details on screen.
        self.source_path = None
        self.book = None
        self.chapters = None
        self.create_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        self.info.setText("Your source file remains in your chosen location; project data is stored locally.")
        self.summary.setText("Select a supported book to begin a fresh import.")
        self.preview.clear()

        if not path.is_file():
            self.status.setText("The selected file could not be found. Choose a file that still exists and try again.")
            self.button.setEnabled(True)
            return
        if path.suffix.lower() not in {".pdf", ".epub", ".txt", ".docx"}:
            self.status.setText("Unsupported file format. Choose a PDF, EPUB, TXT, or DOCX book.")
            self.button.setEnabled(True)
            return
        self.source_path = path
        self.create_button.setEnabled(False)
        self.button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat(f"Analyzing {path.name}…")
        self.info.setText(f"Latest import: {path.name}")
        self.summary.setText(f"Analyzing {path.name} in the background.")
        self.status.setText(f"Preparing to read {path.name}…")
        self.worker = ImportPreviewWorker(path)
        self.worker.status.connect(self.status.setText)
        self.worker.progress.connect(self._worker_progress_changed)
        self.worker.ready.connect(self._analysis_ready)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _analysis_ready(self, book, chapters) -> None:
        self.book = book
        self.chapters = list(chapters)
        word_count = len(str(book.text or "").split())
        total_characters = len(str(book.text or ""))
        self.summary.setText(
            f"<b>{book.title}</b> · {len(chapters)} chapters · {word_count:,} words "
            f"· {total_characters:,} characters"
        )
        preview_parts = []
        for chapter in self.chapters[:8]:
            text = str(chapter.text or "").strip()
            preview_parts.append(f"## {chapter.title}\n{text[:950]}")
        self.preview.setPlainText("\n\n".join(preview_parts))
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Analysis complete")
        self.progress.setVisible(True)
        self.status.setText(f"Extraction verified for {self.source_path.name} • preview the text, then create the local project.")
        self.create_button.setEnabled(True)
        self.button.setEnabled(True)

    def _analysis_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        self.source_path = None
        self.book = None
        self.chapters = None
        self.info.setText("Your source file remains in your chosen location; project data is stored locally.")
        self.status.setText(f"Import analysis failed: {message}")
        self.summary.setText("The project has not been created. Correct the source issue and choose the source again.")
        self.create_button.setEnabled(False)
        self.button.setEnabled(True)

    def _worker_finished(self) -> None:
        self.worker = None

    def create_project(self) -> None:
        if not self.source_path or self.book is None or self.chapters is None:
            self.status.setText("Choose and analyse a supported book first.")
            return
        if not self.on_import:
            self.status.setText("Project creation is unavailable in this window.")
            return
        self.project_creation_started(self.source_path)
        self.create_button.setEnabled(False)
        self.button.setEnabled(False)
        self.on_import(self.source_path, self.book, self.chapters)

    def _worker_progress_changed(self, value: int) -> None:
        """Show animation for unknown-duration work; never imply fake percentages."""
        if int(value) < 0:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Working…")
            self.progress.setVisible(True)
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, int(value))))
        self.progress.setVisible(True)

    def project_creation_started(self, source_path: Path | str) -> None:
        path = Path(source_path)
        self.source_path = path
        self.progress.setRange(0, 0)
        self.progress.setFormat(f"Adding {path.name} to Library…")
        self.progress.setVisible(True)
        self.info.setText(f"Latest import: {path.name}")
        self.summary.setText(f"Creating the local project for {path.name}…")
        self.status.setText(f"Saving {path.name} and its verified chapter structure…")

    def project_created(self, project) -> None:
        project_source = getattr(project, "source_path", None)
        if self.source_path is not None and project_source is not None:
            if self._normal_path(self.source_path) != self._normal_path(project_source):
                return
        self.source_path = Path(project_source) if project_source else self.source_path
        title = str(getattr(project, "title", "") or (self.source_path.name if self.source_path else "Imported book"))
        source_name = self.source_path.name if self.source_path else title
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Import complete")
        self.progress.setVisible(True)
        self.info.setText(f"Latest import: {source_name}")
        self.summary.setText(f"{title} was saved to your local Library.")
        self.status.setText("Import complete • local project created successfully.")
        self.create_button.setEnabled(False)
        self.button.setEnabled(True)

    def project_creation_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        self.info.setText("Your source file remains in your chosen location; project data is stored locally.")
        self.status.setText(f"Project creation failed: {message}")
        self.summary.setText("The verified preview is still available. Resolve the issue and try creating the project again.")
        self.create_button.setEnabled(bool(self.source_path and self.book is not None and self.chapters is not None))
        self.button.setEnabled(True)

    @staticmethod
    def _normal_path(path: Path | str) -> str:
        try:
            return str(Path(path).expanduser().resolve()).casefold()
        except OSError:
            return str(path).casefold()

    def clear_if_source_deleted(self, source_path: Path | str | None) -> None:
        """Hide latest-import data when its corresponding local project is deleted."""
        if source_path is None or self.source_path is None:
            return
        if self._normal_path(source_path) != self._normal_path(self.source_path):
            return
        self.source_path = None
        self.book = None
        self.chapters = None
        self.preview.clear()
        self.info.setText("Your source file remains in your chosen location; project data is stored locally.")
        self.summary.setText("Select a book to preview its extracted text and chapter boundaries.")
        self.status.setText("Ready")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setVisible(False)
        self.create_button.setEnabled(False)
        self.button.setEnabled(True)
