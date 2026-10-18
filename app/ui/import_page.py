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
from app.documents.parser import extract_text


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
            self.status.emit("Reading the source book…")
            self.progress.emit(10)
            book = extract_text(self.source_path)
            if not str(book.text or "").strip():
                raise RuntimeError("No readable text was extracted from this file.")
            self.status.emit("Detecting chapter and section boundaries…")
            self.progress.emit(55)
            chapters = detect_chapters(book.text)
            if not chapters:
                raise RuntimeError("No readable chapters were found in this file.")
            source_words = len(book.text.split())
            chapter_words = sum(len(chapter.text.split()) for chapter in chapters)
            if source_words >= 1000 and chapter_words < int(source_words * 0.90):
                raise RuntimeError(
                    f"Chapter detection retained only {chapter_words:,} of {source_words:,} "
                    "extracted words. Import was stopped to protect your book from losing content."
                )
            self.status.emit("Preparing a text preview…")
            self.progress.emit(90)
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
        if paths:
            self._begin_analysis(Path(paths[0]))

    def _begin_analysis(self, path: Path) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status.setText("Another book is still being analysed.")
            return
        self.source_path = path
        self.book = None
        self.chapters = None
        self.create_button.setEnabled(False)
        self.button.setEnabled(False)
        self.progress.setValue(0)
        self.info.setText(f"Selected: {path.name}")
        self.summary.setText("The source is being analysed in the background.")
        self.preview.clear()
        self.status.setText("Preparing import…")
        self.worker = ImportPreviewWorker(path)
        self.worker.status.connect(self.status.setText)
        self.worker.progress.connect(self.progress.setValue)
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
        self.progress.setValue(100)
        self.status.setText("Extraction verified • preview the text, then create the local project.")
        self.create_button.setEnabled(True)
        self.button.setEnabled(True)

    def _analysis_failed(self, message: str) -> None:
        self.progress.setValue(0)
        self.status.setText(f"Import analysis failed: {message}")
        self.summary.setText("The project has not been created. Correct the source issue and try again.")
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
        self.create_button.setEnabled(False)
        self.button.setEnabled(False)
        self.status.setText("Saving the verified text and chapters into the local project…")
        self.on_import(self.source_path, self.book, self.chapters)
