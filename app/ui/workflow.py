from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QTabWidget, QMessageBox

from app.chapters.detector import detect_chapters, Chapter
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


class ProjectWorkflow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ryu's Audiobook")
        self.resize(1200, 800)
        self.project: Project | None = None
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.library = LibraryPage(self.open_project)
        self.import_page = ImportPage(self.handle_import)
        self.tabs.addTab(self.library, "Library")
        self.tabs.addTab(self.import_page, "Import")

        self.voice = VoicePage()
        self.tabs.addTab(self.voice, "Voice")
        self.tabs.addTab(ModelsPage(), "Models")
        self.tabs.addTab(HardwarePage(), "Hardware")

        self.editor: ChapterEditorPage | None = None
        self.generation: GenerationPage | None = None

    def handle_import(self, path: Path) -> None:
        try:
            book = extract_text(path)
            chapters = detect_chapters(book.text)
            self.project = create_project(book.title, path, chapters)
            self.open_editor()
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))

    def open_editor(self) -> None:
        if not self.project:
            return
        if self.editor:
            index = self.tabs.indexOf(self.editor)
            if index >= 0:
                self.tabs.removeTab(index)
        self.editor = ChapterEditorPage(self.project.chapters, self.save_project)
        self.tabs.addTab(self.editor, "Chapters")
        self.tabs.setCurrentWidget(self.editor)

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
            index = self.tabs.indexOf(self.generation)
            if index >= 0:
                self.tabs.removeTab(index)
        self.generation = GenerationPage(
            self.project.chapters,
            self.project.folder / "audio",
            self.project.folder,
        )
        self.tabs.addTab(self.generation, "Generate")

    def open_project(self, project: Project) -> None:
        self.project = project
        self.open_editor()
        self.ensure_generation_page()
        self.tabs.setCurrentWidget(self.editor)


def build_workflow() -> ProjectWorkflow:
    return ProjectWorkflow()
