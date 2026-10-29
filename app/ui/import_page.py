from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.import_status import load_latest_import, record_latest_import

SUPPORTED_EXTENSIONS = {".epub", ".pdf", ".txt", ".docx"}


class ImportPage(QWidget):
    """Import screen with worker-driven status and no synchronous novel parsing."""

    def __init__(self, on_import=None) -> None:
        super().__init__()
        self.on_import = on_import
        self._active = False
        self._active_path: Path | None = None
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        root.addWidget(QLabel("<h1>Import Studio</h1>"))
        description = QLabel("Bring a novel into Dragon Studio and create a local project.")
        description.setObjectName("muted")
        root.addWidget(description)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("importDropZone")
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(24, 24, 24, 24)
        drop_layout.setSpacing(12)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drop_title = QLabel("Drop a book here")
        self.drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        drop_layout.addWidget(self.drop_title)

        self.drop_hint = QLabel("Source files stay on this device.")
        self.drop_hint.setObjectName("muted")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.drop_hint)

        formats = QLabel("EPUB   ·   PDF   ·   TXT   ·   DOCX")
        formats.setObjectName("muted")
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(formats)

        self.browse_button = QPushButton("Browse files")
        self.browse_button.setObjectName("primary")
        self.browse_button.clicked.connect(self.choose_book)
        drop_layout.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.drop_zone, 3)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        self.progress_card = QGroupBox("Import progress")
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(16, 14, 16, 14)
        progress_layout.setSpacing(8)
        self.progress_title = QLabel("")
        self.progress_title.setWordWrap(True)
        self.progress_detail = QLabel("")
        self.progress_detail.setObjectName("muted")
        self.progress_detail.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        progress_layout.addWidget(self.progress_title)
        progress_layout.addWidget(self.progress_detail)
        progress_layout.addWidget(self.progress_bar)
        lower.addWidget(self.progress_card, 2)

        next_card = QGroupBox("What happens next")
        next_layout = QVBoxLayout(next_card)
        next_layout.setContentsMargins(16, 14, 16, 14)
        next_text = QLabel("Text extraction → metadata detection → chapter detection → project creation.")
        next_text.setObjectName("muted")
        next_text.setWordWrap(True)
        next_layout.addWidget(next_text)
        next_layout.addStretch(1)
        lower.addWidget(next_card, 1)
        root.addLayout(lower, 1)

        self.preview_card = QGroupBox("Imported chapter preview")
        preview_layout = QVBoxLayout(self.preview_card)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(170)
        preview_layout.addWidget(self.preview)
        root.addWidget(self.preview_card)
        self.preview_card.hide()

        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        self.refresh_latest_import()

    @property
    def import_active(self) -> bool:
        return self._active

    def choose_book(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Book",
            "",
            "Books (*.pdf *.epub *.txt *.docx);;PDF (*.pdf);;EPUB (*.epub);;Text (*.txt);;Word (*.docx)",
        )
        if path:
            self._request_import(Path(path))

    def _request_import(self, path: Path) -> None:
        path = path.expanduser()
        if not path.is_file():
            self.show_import_failed(path, "The selected file cannot be accessed.")
            return
        if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            self.show_import_failed(path, "Unsupported file type. Choose EPUB, PDF, TXT or DOCX.")
            return
        if self._active:
            name = self._active_path.name if self._active_path else "the current book"
            self.info.setText(f"Please let {name} finish importing before starting another book.")
            return
        if not self.on_import:
            self.show_import_failed(path, "The import worker is not connected to the application.")
            return
        # Start the worker immediately; extraction/chapter detection must never
        # execute synchronously on the UI thread here.
        self.on_import(path)

    def begin_import(self, path: str | Path) -> None:
        self._active = True
        self._active_path = Path(path)
        self.info.clear()
        self.preview.clear()
        self.preview_card.hide()
        self.progress_title.setText(f"Importing {self._active_path.name}")
        self.progress_detail.setText("Preparing the source file…")
        # Worker signals report real phases, not numerical percentage. An
        # indeterminate bar animates without fabricating precise progress.
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.progress_card.show()
        self.browse_button.setEnabled(False)
        self.drop_title.setText("Import in progress")
        self.drop_hint.setText("The import status below updates from the real worker.")

    def show_import_status(self, message: str) -> None:
        if self._active:
            self.progress_detail.setText(message or "Importing…")

    def show_import_completed(self, project) -> None:
        self._active = False
        self._active_path = None
        self.browse_button.setEnabled(True)
        try:
            record = record_latest_import(project)
        except Exception as exc:
            self.show_import_failed(getattr(project, "source_path", None),
                                    f"Project imported, but recent-import status could not be saved: {exc}")
            return
        filename = record.get("source_name") or project.title
        self.progress_title.setText(f"Imported successfully: {project.title}")
        self.progress_detail.setText(
            f"{filename} · {record.get('chapter_count', 0)} chapter(s) · Ready for Chapter Studio."
        )
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(True)
        self.progress_card.show()
        self.drop_title.setText("Drop another book here")
        self.drop_hint.setText("Latest successful import stays visible for up to 7 days, unless deleted.")
        self.info.clear()
        chapters = getattr(project, "chapters", []) or []
        if chapters:
            self.preview.setPlainText(
                "\n\n".join(f"## {chapter.title}\n{chapter.text[:900]}" for chapter in chapters[:8])
            )
            self.preview_card.show()

    def show_import_failed(self, path: str | Path | None, message: str) -> None:
        self._active = False
        self._active_path = None
        self.browse_button.setEnabled(True)
        filename = Path(path).name if path else "Selected book"
        self.progress_title.setText(f"Import failed: {filename}")
        self.progress_detail.setText(message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_card.show()
        self.drop_title.setText("Drop a book here")
        self.drop_hint.setText("Choose another file to retry.")
        self.info.setText("Import failed. Existing projects were not changed.")

    def refresh_latest_import(self) -> None:
        if self._active:
            return
        latest = load_latest_import()
        if not latest:
            self.progress_card.hide()
            self.progress_title.clear()
            self.progress_detail.clear()
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.info.clear()
            self.drop_title.setText("Drop a book here")
            self.drop_hint.setText("Source files stay on this device.")
            self.preview.clear()
            self.preview_card.hide()
            return
        self.progress_title.setText(f"Latest import: {latest.get('title') or 'Untitled book'}")
        self.progress_detail.setText(
            f"{latest.get('source_name') or 'Local source'} · "
            f"{latest.get('chapter_count', 0)} chapter(s) · Saved locally."
        )
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(True)
        self.progress_card.show()
        self.drop_title.setText("Drop another book here")
        self.drop_hint.setText("Source files stay on this device.")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for url in urls:
            if url.isLocalFile():
                self._request_import(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return
        event.ignore()
