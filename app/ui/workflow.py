from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
)

from app.chapters.detector import Chapter, detect_chapters
from app.core.project import Project, create_project
from app.core.state import load_state, save_state
from app.documents.parser import extract_text
from app.ui.chapter_editor import ChapterEditorPage
from app.ui.generation_page import GenerationPage
from app.ui.import_page import ImportPage
from app.ui.library import LibraryPage
from app.ui.voice_page import VoicePage
from app.ui.hardware_page import HardwarePage
from app.ui.models_page import ModelsPage
from app.ui.voice_cast_page import VoiceCastPage


class ProjectWorkflow(QMainWindow):
    """Main studio shell inspired by modern audiobook creation workflows."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ryu's Audiobook")
        self.resize(1440, 900)
        self.project: Project | None = None

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(26, 18, 26, 16)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)
        brand = QLabel("RYU'S AUDIOBOOK")
        brand.setObjectName("brand")
        brand_col.addWidget(brand)
        subtitle = QLabel("Local audiobook studio")
        subtitle.setObjectName("muted")
        brand_col.addWidget(subtitle)
        header.addLayout(brand_col)
        header.addSpacing(28)

        self.project_label = QLabel("No book open")
        self.project_label.setObjectName("projectTitle")
        header.addWidget(self.project_label, 1)

        self.new_book_button = QPushButton("+  Import Book")
        self.new_book_button.setObjectName("primary")
        self.new_book_button.clicked.connect(lambda: self.select_section("Import"))
        header.addWidget(self.new_book_button)
        shell_layout.addLayout(header)

        body = QHBoxLayout()
        body.setContentsMargins(12, 0, 12, 12)
        body.setSpacing(10)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        self.sidebar.setSpacing(4)

        sections = [
            ("Library", "⌂"),
            ("Import", "+"),
            ("Chapters", "☷"),
            ("Voice & Narration", "◉"),
            ("Voice Cast", "♙"),
            ("Generate", "▶"),
            ("Models", "◆"),
            ("Hardware", "⚙"),
        ]
        for name, icon in sections:
            item = QListWidgetItem(f"  {icon}   {name}")
            item.setData(32, name)
            self.sidebar.addItem(item)

        self.sidebar.currentRowChanged.connect(self._sidebar_changed)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("studioStack")
        body.addWidget(self.stack, 1)
        shell_layout.addLayout(body, 1)

        self.setCentralWidget(shell)

        self.library = LibraryPage(self.open_project)
        self.import_page = ImportPage(self.handle_import)
        self.voice = VoicePage()

        self.stack.addWidget(self.library)
        self.stack.addWidget(self.import_page)
        self.stack.addWidget(self.voice)
        self.voice_cast = VoiceCastPage(
            lambda: self.project.chapters if self.project else [],
            lambda: self.project.source_path if self.project else None,
        )
        self.stack.addWidget(self.voice_cast)
        self.stack.addWidget(ModelsPage())
        self.stack.addWidget(HardwarePage())

        self.editor: ChapterEditorPage | None = None
        self.generation: GenerationPage | None = None
        self._generation_index = -1
        self._editor_index = -1

        self.sidebar.setCurrentRow(0)

    def _sidebar_changed(self, row: int) -> None:
        if row < 0:
            return
        name = self.sidebar.item(row).data(32)

        if name == "Library":
            self.stack.setCurrentWidget(self.library)
        elif name == "Import":
            self.stack.setCurrentWidget(self.import_page)
        elif name == "Chapters":
            if self.editor:
                self.stack.setCurrentWidget(self.editor)
            else:
                self.stack.setCurrentWidget(self.import_page)
        elif name == "Voice & Narration":
            self.stack.setCurrentWidget(self.voice)
        elif name == "Voice Cast":
            self.voice_cast.refresh_profiles()
            self.stack.setCurrentWidget(self.voice_cast)
        elif name == "Generate":
            if self.generation:
                self.stack.setCurrentWidget(self.generation)
            else:
                self.stack.setCurrentWidget(self.import_page)
        elif name == "Models":
            self.stack.setCurrentIndex(5)
        elif name == "Hardware":
            self.stack.setCurrentIndex(6)

    def select_section(self, name: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(32) == name:
                self.sidebar.setCurrentRow(i)
                return

    def handle_import(self, path: Path) -> None:
        try:
            book = extract_text(path)
            chapters = detect_chapters(book.text)
            self.project = create_project(book.title, path, chapters)
            self.project_label.setText(book.title)
            self.open_editor()
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))

    def open_editor(self) -> None:
        if not self.project:
            return
        if self.editor:
            self.stack.removeWidget(self.editor)
            self.editor.deleteLater()
        self.editor = ChapterEditorPage(self.project.chapters, self.save_project, self.rename_project, self.redetect_chapters)
        self.stack.addWidget(self.editor)
        self._editor_index = self.stack.indexOf(self.editor)
        self.select_section("Chapters")

    def redetect_chapters(self) -> None:
        if not self.project or not self.project.source_path or not self.project.source_path.exists():
            QMessageBox.warning(self, "Re-detect Chapters", "The original source file is not available.")
            return
        try:
            book = extract_text(self.project.source_path)
            chapters = detect_chapters(book.text)
            if not chapters:
                raise RuntimeError("No readable chapters were detected.")
            self.project.chapters = chapters
            self.project.save()
            self.library.refresh()
            self.open_editor()
            self.ensure_generation_page()
        except Exception as exc:
            QMessageBox.critical(self, "Re-detect Chapters Failed", str(exc))

    def rename_project(self, title: str) -> None:
        if not self.project or not title.strip():
            return
        self.project.title = title.strip()
        self.project.save()
        self.project_label.setText(self.project.title)
        self.library.refresh()
        self.ensure_generation_page()

    def save_project(self, chapters: list[Chapter]) -> None:
        if not self.project:
            return
        self.project.chapters = chapters
        self.project.save()
        state = load_state(self.project.folder)
        state["status"] = "ready"
        save_state(self.project.folder, state)
        self.library.refresh()
        self.ensure_generation_page()

    def ensure_generation_page(self) -> None:
        if not self.project:
            return
        if self.generation:
            self.stack.removeWidget(self.generation)
            self.generation.deleteLater()
        self.generation = GenerationPage(
            self.project.chapters,
            self.project.folder / "working",
            self.project.folder,
        )
        self.stack.addWidget(self.generation)
        self._generation_index = self.stack.indexOf(self.generation)

    def open_project(self, project: Project) -> None:
        self.project = project
        self.project_label.setText(project.title)
        self.open_editor()
        self.ensure_generation_page()
        self.select_section("Chapters")


def build_workflow() -> ProjectWorkflow:
    return ProjectWorkflow()
