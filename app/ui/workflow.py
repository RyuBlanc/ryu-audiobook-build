from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QEasingCurve, QPropertyAnimation, QTimer, QSize
from PySide6.QtGui import QFontMetrics, QIcon, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QGraphicsOpacityEffect,
)

from app.chapters.detector import Chapter, detect_chapters
from app.version import full_version
from app.core.project import Project, create_project
from app.core.state import load_state, save_state
from app.documents.parser import extract_text, reflow_source_text
from app.ui.chapter_editor import ChapterEditorPage
from app.ui.generation_page import GenerationPage
from app.ui.import_page import ImportPage
from app.ui.library import LibraryPage
from app.ui.voice_page import VoicePage
from app.ui.hardware_page import HardwarePage
from app.ui.models_page import ModelsPage
from app.ui.voice_cast_page import VoiceCastPage
from app.ui.loading_overlay import FrostedLoadingOverlay
from app.ui.motion import reduced_motion_enabled


def _import_book_icon() -> QIcon:
    """Use the Ryu audiobook brand mark instead of a generic plus symbol."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for filename in ("ryu_audiobook_logo.svg", "ryu_audiobook_logo.png", "ryu_audiobook_logo.jpg"):
        path = base / "assets" / filename
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return QIcon()


class ImportBookWorker(QThread):
    """Extract and detect chapters away from the UI thread."""

    completed = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, source_path: Path) -> None:
        super().__init__()
        self.source_path = Path(source_path)

    def run(self) -> None:
        try:
            self.status.emit("Extracting text from the source book…")
            book = extract_text(self.source_path)
            self.status.emit("Finding chapter and section boundaries…")
            chapters = detect_chapters(book.text)
            if not chapters:
                raise RuntimeError("No readable chapters were found in this file.")
            source_words = len(book.text.split())
            chapter_words = sum(len(chapter.text.split()) for chapter in chapters)
            if source_words >= 1000 and chapter_words < int(source_words * 0.90):
                raise RuntimeError(
                    "Chapter detection retained only "
                    f"{chapter_words:,} of {source_words:,} extracted words. "
                    "Import was stopped to protect the book from losing content. "
                    "Review the source text and chapter boundaries, then retry."
                )
            self.status.emit("Saving the local audiobook project…")
            project = create_project(book.title, self.source_path, chapters)
            self.completed.emit(project)
        except Exception as exc:
            self.failed.emit(str(exc))


class RedetectChaptersWorker(QThread):
    """Re-read a project's original source and detect chapters off the UI thread."""

    completed = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, source_path: Path) -> None:
        super().__init__()
        self.source_path = Path(source_path)

    def run(self) -> None:
        try:
            self.status.emit("Re-reading the original source file…")
            book = extract_text(self.source_path)
            self.status.emit("Re-detecting chapter and section boundaries…")
            chapters = detect_chapters(book.text)
            if not chapters:
                raise RuntimeError("No readable chapters were detected.")
            self.completed.emit(chapters)
        except Exception as exc:
            self.failed.emit(str(exc))


class ProjectWorkflow(QMainWindow):
    """Main studio shell inspired by modern audiobook creation workflows."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ryu's Audiobook")
        self.resize(1440, 900)
        self.project: Project | None = None
        self._import_worker: ImportBookWorker | None = None
        self._redetect_worker: RedetectChaptersWorker | None = None
        self._page_animation: QPropertyAnimation | None = None
        self._page_animation_widget: QWidget | None = None

        # Persistent Dragon Studio shell: grouped navigation on the left,
        # a compact project-aware top bar, and the existing functional pages.
        # Visible labels may evolve without changing the internal routing keys.
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.import_book_icon = _import_book_icon()
        sidebar_panel = QWidget()
        sidebar_panel.setObjectName("studioSidebar")
        sidebar_panel.setFixedWidth(252)
        side_layout = QVBoxLayout(sidebar_panel)
        side_layout.setContentsMargins(14, 18, 14, 16)
        side_layout.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_mark = QLabel()
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(QSize(54, 54))
        brand_mark.setPixmap(self.import_book_icon.pixmap(QSize(54, 54)))
        brand_row.addWidget(brand_mark)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(2)
        brand = QLabel("RYU'S AUDIOBOOK")
        brand.setObjectName("brand")
        brand_col.addWidget(brand)
        edition = QLabel("DRAGON STUDIO")
        edition.setObjectName("brandEdition")
        brand_col.addWidget(edition)
        brand_row.addLayout(brand_col, 1)
        side_layout.addLayout(brand_row)

        brand_divider = QWidget()
        brand_divider.setObjectName("sidebarDivider")
        brand_divider.setFixedHeight(1)
        side_layout.addWidget(brand_divider)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setSpacing(3)
        self.sidebar.setIconSize(QSize(20, 20))
        self.nav_titles = {
            "Library": "Audiobook Library",
            "Import": "Import Studio",
            "Chapters": "Chapter Studio",
            "Voice & Narration": "Voice Studio",
            "Voice Cast": "Character Studio",
            "Generate": "Production Studio",
            "Models": "Models Center",
            "Hardware": "Performance Center",
        }

        def add_nav_group(label: str, entries: list[tuple[str, str, str]]) -> None:
            group_item = QListWidgetItem(label.upper())
            group_item.setData(32, "")
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group_item.setForeground(QColor("#D6B06A"))
            group_font = group_item.font()
            group_font.setBold(True)
            group_font.setPointSize(8)
            group_item.setFont(group_font)
            self.sidebar.addItem(group_item)
            for key, title, icon_text in entries:
                if key == "Import":
                    item = QListWidgetItem(f"  {title}")
                    item.setIcon(self.import_book_icon)
                else:
                    item = QListWidgetItem(f"  {icon_text}   {title}")
                item.setData(32, key)
                item.setToolTip(title)
                self.sidebar.addItem(item)

        add_nav_group("Home", [("Library", "Audiobook Library", "⌂")])
        add_nav_group("Project", [
            ("Import", "Import Studio", ""),
            ("Chapters", "Chapter Studio", "☷"),
            ("Voice & Narration", "Voice Studio", "◉"),
            ("Voice Cast", "Character Studio", "♙"),
        ])
        add_nav_group("Production", [("Generate", "Production Studio", "▶")])
        add_nav_group("System", [
            ("Models", "Models Center", "◆"),
            ("Hardware", "Performance Center", "⚙"),
        ])

        self.sidebar.currentRowChanged.connect(self._sidebar_changed)
        self.sidebar.itemClicked.connect(self._sidebar_item_clicked)
        side_layout.addWidget(self.sidebar, 1)

        self.current_project_card = QWidget()
        self.current_project_card.setObjectName("currentProjectCard")
        current_project_layout = QVBoxLayout(self.current_project_card)
        current_project_layout.setContentsMargins(12, 10, 12, 10)
        current_project_layout.setSpacing(4)
        current_project_eyebrow = QLabel("CURRENT PROJECT")
        current_project_eyebrow.setObjectName("muted")
        current_project_layout.addWidget(current_project_eyebrow)
        self.project_mini_title = QLabel("No book open")
        self.project_mini_title.setObjectName("projectMiniTitle")
        self.project_mini_title.setWordWrap(True)
        self.project_mini_title.setToolTip("No book open")
        current_project_layout.addWidget(self.project_mini_title)
        self.project_mini_status = QLabel("Local-first workspace")
        self.project_mini_status.setObjectName("muted")
        current_project_layout.addWidget(self.project_mini_status)
        side_layout.addWidget(self.current_project_card)

        main_panel = QWidget()
        main_panel.setObjectName("studioMainPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 24, 14)
        header.setSpacing(14)
        page_col = QVBoxLayout()
        page_col.setSpacing(1)
        self.page_heading = QLabel("Audiobook Library")
        self.page_heading.setObjectName("pageHeading")
        page_col.addWidget(self.page_heading)
        self.page_subheading = QLabel("Your local audiobook projects and ongoing work.")
        self.page_subheading.setObjectName("pageSubheading")
        page_col.addWidget(self.page_subheading)
        header.addLayout(page_col, 1)

        self.project_label = QLabel("No book open")
        self.project_label.setObjectName("projectPill")
        self.project_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.project_label.setMinimumWidth(110)
        self.project_label.setMaximumWidth(260)
        self.project_label.setToolTip("No book open")
        header.addWidget(self.project_label)

        self.global_search = QLineEdit()
        self.global_search.setObjectName("globalSearch")
        self.global_search.setPlaceholderText("Search your local library…")
        self.global_search.setClearButtonEnabled(True)
        self.global_search.setMaximumWidth(250)
        self.global_search.returnPressed.connect(self._search_library)
        header.addWidget(self.global_search)

        self.new_book_button = QPushButton("Import Book")
        self.new_book_button.setObjectName("primary")
        self.new_book_button.setIcon(self.import_book_icon)
        self.new_book_button.setIconSize(QSize(20, 20))
        self.new_book_button.clicked.connect(lambda: self.select_section("Import"))
        header.addWidget(self.new_book_button)
        main_layout.addLayout(header)

        body = QHBoxLayout()
        body.setContentsMargins(22, 6, 22, 16)
        body.setSpacing(10)
        self.stack = QStackedWidget()
        self.stack.setObjectName("studioStack")
        body.addWidget(self.stack, 1)
        main_layout.addLayout(body, 1)

        shell_layout.addWidget(sidebar_panel)
        shell_layout.addWidget(main_panel, 1)

        self.setCentralWidget(shell)
        self.loading_overlay = FrostedLoadingOverlay(shell)
        self.loading_overlay.setGeometry(shell.rect())

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

        # Row 0 is the non-selectable HOME heading; Library is the first destination.
        self.sidebar.setCurrentRow(1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_project_label()
        if hasattr(self, "loading_overlay") and self.centralWidget():
            self.loading_overlay.setGeometry(self.centralWidget().rect())

    def _log_ui_failure(self, context: str, exc: BaseException) -> None:
        """Persist UI exceptions so frozen Windows builds are diagnosable."""
        try:
            from app.core.paths import app_root

            log_dir = app_root() / "Logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "application.log"
            trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"\n[{datetime.now().astimezone().isoformat()}] "
                    f"{context}: {type(exc).__name__}: {exc}\n{trace}\n"
                )
        except Exception:
            # Diagnostics must never crash or block a navigation action.
            pass

    def _set_project_title(self, title: str) -> None:
        self._project_title_full = title or "No book open"
        self._refresh_project_label()

    def _refresh_project_label(self) -> None:
        title = getattr(self, "_project_title_full", self.project_label.text() or "No book open")
        width = max(120, self.project_label.width() - 8)
        text = QFontMetrics(self.project_label.font()).elidedText(
            title, Qt.TextElideMode.ElideMiddle, width
        )
        self.project_label.setText(text)
        self.project_label.setToolTip(title)
        if hasattr(self, "project_mini_title"):
            self.project_mini_title.setText(title)
            self.project_mini_title.setToolTip(title)
            is_open = self.project is not None
            self.project_mini_status.setText(
                "Project open • saved locally" if is_open else "Local-first workspace"
            )

    def _search_library(self) -> None:
        """Route top-bar search to the real local library filter."""
        query = self.global_search.text().strip()
        if not query:
            return
        self.select_section("Library")
        self._show_page(self.library)
        self.library.search.setText(query)

    def _update_page_chrome(self, widget: QWidget) -> None:
        pages = [
            (self.library, "Library", "Your local audiobook projects and ongoing work."),
            (self.import_page, "Import", "Bring a source book into your local workflow."),
            (self.voice, "Voice & Narration", "Choose, configure, and preview the narrator."),
            (self.voice_cast, "Voice Cast", "Review dialogue and assign character voices."),
        ]
        if self.editor is not None:
            pages.append((self.editor, "Chapters", "Review and edit your book chapter by chapter."))
        if self.generation is not None:
            pages.append((self.generation, "Generate", "Preview, generate, recover, and assemble your audiobook."))
        if self.stack.count() > 4:
            pages.append((self.stack.widget(4), "Models", "Manage local speech and analysis components."))
        if self.stack.count() > 5:
            pages.append((self.stack.widget(5), "Hardware", "Verify local backends and review hardware performance."))
        for page, key, subtitle in pages:
            if page is widget:
                self.page_heading.setText(self.nav_titles.get(key, key))
                self.page_subheading.setText(subtitle)
                return

    def _show_page(self, widget: QWidget) -> None:
        """Switch pages first; animation is optional and must never block navigation."""
        if widget is None:
            return

        # A page can be re-created when a book is saved or renamed. Never try to
        # show a widget that is no longer registered with the stacked widget.
        if self.stack.indexOf(widget) < 0:
            raise RuntimeError(
                f"Cannot navigate to {type(widget).__name__}: page is not in the workflow stack."
            )

        if self._page_animation is not None:
            try:
                self._page_animation.stop()
            except RuntimeError:
                # The previous page may already have been deleted by Qt.
                pass
            if self._page_animation_widget is not None:
                try:
                    self._page_animation_widget.setGraphicsEffect(None)
                except RuntimeError:
                    pass
            self._page_animation = None
            self._page_animation_widget = None

        self.stack.setCurrentWidget(widget)
        if self.stack.currentWidget() is not widget:
            raise RuntimeError(
                f"Navigation did not activate {type(widget).__name__}."
            )
        self._update_page_chrome(widget)

        # A graphics effect is decorative. If a platform-specific Qt animation
        # fails, keep the newly selected page visible and log the issue instead
        # of falling back to Import and making Generate appear broken.
        try:
            if reduced_motion_enabled() or not widget.isVisible():
                return

            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(135)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            self._page_animation = animation
            self._page_animation_widget = widget

            def finish() -> None:
                if self._page_animation is animation:
                    widget.setGraphicsEffect(None)
                    self._page_animation = None
                    self._page_animation_widget = None

            animation.finished.connect(finish)
            animation.start()
        except Exception as exc:
            self._log_ui_failure("Page transition animation", exc)
            try:
                widget.setGraphicsEffect(None)
            except RuntimeError:
                pass
            self._page_animation = None
            self._page_animation_widget = None

    def _sidebar_item_clicked(self, item: QListWidgetItem) -> None:
        """Recover navigation when the clicked row is already selected."""
        row = self.sidebar.row(item)
        if row < 0:
            return
        name = str(item.data(32) or "")
        if name == "Generate":
            expected = self.generation if self.project else self.import_page
        elif name == "Library":
            expected = self.library
        elif name == "Import":
            expected = self.import_page
        elif name == "Chapters":
            expected = self.editor or self.import_page
        elif name == "Voice & Narration":
            expected = self.voice
        elif name == "Voice Cast":
            expected = self.voice_cast
        elif name == "Models":
            expected = self.stack.widget(4)
        elif name == "Hardware":
            expected = self.stack.widget(5)
        else:
            return
        # If currentRowChanged already navigated, do not repeat or refresh twice.
        if expected is None or self.stack.currentWidget() is not expected:
            self._sidebar_changed(row)

    def _refresh_generation_context(self) -> None:
        """Refresh book-dependent fields after the Generate page is already visible."""
        if not self.project or not self.generation:
            return
        page = self.generation
        page.chapters = self.project.chapters
        problems: list[str] = []
        for label, callback in (
            ("voice profiles", page._refresh_voice_profiles),
            ("voice cast", page._load_voice_cast_summary),
            ("chapter sources", page.refresh_chapter_sources),
        ):
            try:
                callback()
            except Exception as exc:
                # A stale optional widget/profile must not block navigation,
                # but retain the complete traceback for the support log.
                self._log_ui_failure(f"Generate context refresh ({label})", exc)
                problems.append(f"{label}: {type(exc).__name__}: {exc}")
        if problems and hasattr(page, "status"):
            page.status.setText(
                "Generate opened, but some details could not be refreshed. "
                + " | ".join(problems)
            )

    def _sidebar_changed(self, row: int) -> None:
        if row < 0 or row >= self.sidebar.count():
            return
        item = self.sidebar.item(row)
        if item is None:
            return
        name = item.data(32)

        if name == "Library":
            self._show_page(self.library)
        elif name == "Import":
            self._show_page(self.import_page)
        elif name == "Chapters":
            if self.editor:
                self._show_page(self.editor)
            else:
                self._show_page(self.import_page)
        elif name == "Voice & Narration":
            self._show_page(self.voice)
        elif name == "Voice Cast":
            try:
                self.voice_cast.refresh_profiles()
            except Exception:
                pass
            self._show_page(self.voice_cast)
        elif name == "Generate":
            try:
                if not self.project:
                    # The Library can show a selected book without making it the
                    # active project. Generate should promote that selected project
                    # automatically instead of bouncing back to the Library.
                    selected_projects = self.library._selected_projects()
                    if selected_projects:
                        self.open_project(selected_projects[0])
                        # open_project selects Chapters for editing. Restore the
                        # Generate row without emitting a nested navigation event;
                        # this handler will show the generation page below.
                        generate_row = next(
                            (
                                index for index in range(self.sidebar.count())
                                if self.sidebar.item(index).data(32) == "Generate"
                            ),
                            -1,
                        )
                        if generate_row >= 0:
                            self.sidebar.blockSignals(True)
                            try:
                                self.sidebar.setCurrentRow(generate_row)
                            finally:
                                self.sidebar.blockSignals(False)
                    if not self.project:
                        self._show_page(self.library)
                        QMessageBox.information(
                            self,
                            "Open a book first",
                            "Generate needs an audiobook project. Select a book in Library "
                            "or import a new book, then select Generate again.",
                        )
                        return
                if self.generation is None:
                    self.ensure_generation_page()
                if self.generation is None:
                    raise RuntimeError("The Generate page could not be initialized.")
                self._show_page(self.generation)
                # Do not run disk/profile/readiness refreshes before showing the page;
                # this was able to leave the previous page visible if a refresh failed.
                QTimer.singleShot(75, self._refresh_generation_context)
            except Exception as exc:
                self._log_ui_failure("Generate page navigation", exc)
                # Keep the Generate page selected when construction succeeded;
                # only use Import as a fallback if the page itself is unavailable.
                if (
                    self.generation is None
                    or self.stack.indexOf(self.generation) < 0
                    or (
                        self.project is not None
                        and self.generation.project_folder != self.project.folder
                    )
                ):
                    self._show_page(self.import_page)
                QMessageBox.critical(
                    self,
                    "Generate page could not be opened",
                    "Ryu's Audiobook could not open the Generate page.\n\n"
                    f"Details: {type(exc).__name__}: {exc}\n\n"
                    "Your imported book and saved chapter text have not been deleted.",
                )
        elif name == "Models":
            self._show_page(self.stack.widget(4))
        elif name == "Hardware":
            self._show_page(self.stack.widget(5))

    def select_section(self, name: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(32) == name:
                self.sidebar.setCurrentRow(i)
                return

    def handle_import(self, path: Path) -> None:
        if self._import_worker is not None and self._import_worker.isRunning():
            return
        self.loading_overlay.show_loading(
            "Importing your book",
            "Reading the source file, finding chapters and preparing your local project…",
        )
        worker = ImportBookWorker(path)
        self._import_worker = worker
        worker.status.connect(self.loading_overlay.set_detail)
        worker.completed.connect(self._import_completed)
        worker.failed.connect(self._import_failed)
        worker.finished.connect(self._import_worker_finished)
        worker.start()

    def _import_completed(self, project: Project) -> None:
        self.loading_overlay.dismiss()
        self.project = project
        self._set_project_title(project.title)
        self.open_editor()

    def _import_failed(self, message: str) -> None:
        self.loading_overlay.dismiss()
        QMessageBox.critical(self, "Import Failed", message)

    def _import_worker_finished(self) -> None:
        # Keep the QThread alive until Qt confirms its worker loop has ended.
        self._import_worker = None

    def open_editor(self) -> None:
        if not self.project:
            return
        if self.editor:
            self.stack.removeWidget(self.editor)
            self.editor.deleteLater()
        self.editor = ChapterEditorPage(
            self.project.chapters,
            self.save_project,
            self.rename_project,
            self.redetect_chapters,
            self.project.folder,
            self.project.title,
            self.autosave_project,
        )
        self.stack.addWidget(self.editor)
        self._editor_index = self.stack.indexOf(self.editor)
        self.select_section("Chapters")

    def redetect_chapters(self) -> None:
        if not self.project or not self.project.source_path or not self.project.source_path.exists():
            QMessageBox.warning(self, "Re-detect Chapters", "The original source file is not available.")
            return
        if self._redetect_worker is not None and self._redetect_worker.isRunning():
            return

        self.loading_overlay.show_loading(
            "Rebuilding chapter map",
            "Re-reading the original book and identifying chapter boundaries…",
        )
        worker = RedetectChaptersWorker(self.project.source_path)
        self._redetect_worker = worker
        worker.status.connect(self.loading_overlay.set_detail)
        worker.completed.connect(self._redetect_completed)
        worker.failed.connect(self._redetect_failed)
        worker.finished.connect(self._redetect_worker_finished)
        worker.start()

    def _redetect_completed(self, chapters: list[Chapter]) -> None:
        self.loading_overlay.dismiss()
        if not self.project:
            return
        try:
            self.project.chapters = chapters
            self.project.save()
            self.library.refresh()
            self.open_editor()
            self.ensure_generation_page()
        except Exception as exc:
            QMessageBox.critical(self, "Re-detect Chapters Failed", str(exc))

    def _redetect_failed(self, message: str) -> None:
        self.loading_overlay.dismiss()
        QMessageBox.critical(self, "Re-detect Chapters Failed", message)

    def _redetect_worker_finished(self) -> None:
        # Hold the worker until Qt confirms it has stopped.
        self._redetect_worker = None

    def rename_project(self, title: str) -> None:
        if not self.project or not title.strip():
            return
        self.project.title = title.strip()
        self.project.save()
        self._set_project_title(self.project.title)
        self.library.refresh()
        if self.editor:
            self.editor.project_title = self.project.title
        if self.generation:
            self.generation.project_title = self.project.title
            self.generation.title.setText(self.project.title)
            self.generation._set_default_output()
        self.ensure_generation_page()

    def autosave_project(self, chapters: list[Chapter]) -> bool:
        """Persist editor text without rebuilding heavyweight UI pages."""
        if not self.project:
            return False
        try:
            self.project.chapters = list(chapters)
            self.project.save()
            return True
        except Exception as exc:
            return False

    def save_project(self, chapters: list[Chapter]) -> bool:
        if not self.project:
            return False
        try:
            # Save the exact manual editor state first. Do not re-run chapter
            # detection or repair during a normal Save operation.
            self.project.chapters = list(chapters)
            self.project.save()
            persisted = Project.load(self.project.folder)
            self.project.chapters = persisted.chapters

            state = load_state(self.project.folder)
            state["status"] = "ready"
            state["failed_chapters"] = []
            save_state(self.project.folder, state)

            self.library.refresh()
            self.ensure_generation_page()
            return True
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Chapter edits could not be saved.\n\n{exc}",
            )
            return False

    def _repair_text_layout(self) -> bool:
        if not self.project:
            return False
        changed = False
        for chapter in self.project.chapters:
            normalized = reflow_source_text(chapter.text or "")
            if normalized != chapter.text:
                chapter.text = normalized
                changed = True
        if changed:
            try:
                self.project.save()
            except Exception:
                return False
        return changed

    def _repair_empty_chapters(self) -> None:
        """Repair projects created by older chapter-detector versions."""
        if not self.project or not self.project.source_path:
            return
        if not any(not c.text or not c.text.strip() for c in self.project.chapters):
            return
        try:
            source = Path(self.project.source_path)
            if not source.exists():
                return
            detected = detect_chapters(extract_text(source).text)
            if detected and all(c.text.strip() for c in detected):
                self.project.chapters = detected
                self.project.save()
                self.library.refresh()
        except Exception:
            # Keep the existing project intact if automatic repair cannot run.
            return

    def ensure_generation_page(self) -> None:
        if not self.project:
            return

        # Build the replacement before touching the current widget. Previously,
        # the old page was removed and scheduled for deletion first; if the new
        # constructor raised, self.generation could still point at a deleted Qt
        # object and every later click on Generate failed with a C++ object error.
        old_generation = self.generation
        old_was_current = (
            old_generation is not None
            and self.stack.indexOf(old_generation) >= 0
            and self.stack.currentWidget() is old_generation
        )
        try:
            new_generation = GenerationPage(
                self.project.chapters,
                self.project.folder / "working",
                self.project.folder,
                self.project.title,
            )
        except Exception as exc:
            self._log_ui_failure("Construct Generate page", exc)
            old_is_registered = (
                old_generation is not None
                and self.stack.indexOf(old_generation) >= 0
            )
            old_matches_project = (
                old_is_registered
                and old_generation.project_folder == self.project.folder
            )
            if old_matches_project:
                # Preserve the working page only when it belongs to the same
                # project. Never show a previous book's Generate settings as
                # though they belonged to the newly selected project.
                if hasattr(old_generation, "status"):
                    old_generation.status.setText(
                        f"Generate refresh failed ({type(exc).__name__}: {exc}). "
                        "The previous page is still available; see Logs/application.log."
                    )
                self.generation = old_generation
                return
            if old_is_registered:
                self.stack.removeWidget(old_generation)
                old_generation.hide()
                old_generation.deleteLater()
            self.generation = None
            self._generation_index = -1
            raise

        self.stack.addWidget(new_generation)
        self.generation = new_generation
        self._generation_index = self.stack.indexOf(new_generation)
        if old_was_current:
            self.stack.setCurrentWidget(new_generation)
        if old_generation is not None and old_generation is not new_generation:
            if self.stack.indexOf(old_generation) >= 0:
                self.stack.removeWidget(old_generation)
            old_generation.hide()
            old_generation.deleteLater()

    def open_project(self, project: Project) -> None:
        self.project = project
        self._set_project_title(project.title)
        # Repair legacy empty chapter records before creating either editor or
        # generation UI so both views show the same corrected chapter list.
        self._repair_empty_chapters()
        self._repair_text_layout()
        if self.project.chapters:
            first = self.project.chapters[0]
            self.voice.set_preview_source(first.text, first.title)
        self.open_editor()
        self.ensure_generation_page()
        self.select_section("Chapters")


def build_workflow() -> ProjectWorkflow:
    return ProjectWorkflow()
