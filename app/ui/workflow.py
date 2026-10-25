from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import sys
import traceback
import time

from PySide6.QtCore import Qt, QThread, Signal, QEasingCurve, QPropertyAnimation, QTimer, QSize, QSettings
from PySide6.QtGui import QFontMetrics, QIcon, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QLabel,
    QLineEdit,
    QComboBox,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QScrollArea,
    QGraphicsOpacityEffect,
    QApplication,
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
from app.ui.dashboard_page import DashboardPage
from app.ui.voice_page import VoicePage
from app.ui.hardware_page import HardwarePage
from app.ui.models_page import ModelsPage
from app.ui.voice_cast_page import VoiceCastPage
from app.ui.character_library import CharacterLibraryPage
from app.ui.audiobooks_page import AudiobooksPage
from app.ui.history_page import HistoryPage
from app.ui.settings_page import SettingsPage
from app.ui.loading_overlay import FrostedLoadingOverlay
from app.ui.motion import reduced_motion_enabled


def _import_book_icon() -> QIcon:
    """Use the Ryu audiobook brand mark instead of a generic plus symbol."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for filename in ("ryu_audiobook_logo.png", "ryu_audiobook_logo.svg", "ryu_audiobook_logo.jpg"):
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

    def __init__(self, source_path: Path, book=None, chapters=None) -> None:
        super().__init__()
        self.source_path = Path(source_path)
        self.book = book
        self.chapters = list(chapters) if chapters is not None else None

    def run(self) -> None:
        try:
            if self.book is None or self.chapters is None:
                self.status.emit(f"Extracting text from {self.source_path.name}…")
                book = extract_text(self.source_path)
                self.status.emit(f"Finding chapter and section boundaries in {self.source_path.name}…")
                chapters = detect_chapters(book.text)
            else:
                # Import Studio already parsed this book in the background.
                # Reuse that exact extraction rather than blocking the app by
                # parsing large EPUB/PDF files a second time.
                book = self.book
                chapters = self.chapters
                self.status.emit(f"Verifying extracted text and chapter map for {self.source_path.name}…")
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
            self.status.emit(f"Saving {self.source_path.name} as a local audiobook project…")
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


class StudioToast(QWidget):
    """Compact, non-blocking toast matching the approved HTML notification style."""

    def __init__(self, parent: QWidget, title: str, message: str, kind: str = "info") -> None:
        super().__init__(parent, Qt.WindowType.Widget)
        self.setObjectName("studioToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        accent = {"success": "#36C879", "warning": "#F5B942", "error": "#EB5757", "info": "#4E9CFF"}.get(kind, "#4E9CFF")
        symbol = {"success": "✓", "warning": "!", "error": "×", "info": "i"}.get(kind, "i")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 10, 12, 10)
        layout.setSpacing(10)
        mark = QLabel(symbol)
        mark.setFixedSize(25, 25)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"color:{accent};font-size:16px;font-weight:800;border:1px solid {accent};border-radius:12px;")
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        heading = QLabel(title)
        heading.setStyleSheet("color:#F5F5F6;font-size:13px;font-weight:700;background:transparent;")
        detail = QLabel(message)
        detail.setWordWrap(True)
        detail.setMaximumWidth(330)
        detail.setStyleSheet("color:#A6AFBD;font-size:12px;background:transparent;")
        column.addWidget(heading)
        column.addWidget(detail)
        layout.addLayout(column, 1)
        close = QPushButton("×")
        close.setFixedSize(22, 22)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet("QPushButton{color:#A6AFBD;background:transparent;border:0;font-size:17px;} QPushButton:hover{color:#FFFFFF;}")
        close.clicked.connect(self.dismiss)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet(f"#studioToast{{background:#191F2B;border:1px solid #2B3240;border-left:4px solid {accent};border-radius:10px;}}")
        self.setMinimumWidth(300)
        self.setMaximumWidth(410)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

    def show_toast(self, duration_ms: int = 4200) -> None:
        host = self.parentWidget()
        if host is not None:
            self.adjustSize()
            self.move(max(12, host.width() - self.width() - 20), max(12, host.height() - self.height() - 20))
        self.show()
        self.raise_()
        if reduced_motion_enabled():
            self._opacity.setOpacity(1.0)
        else:
            self._fade.setDuration(170)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self._timer.start(max(1200, int(duration_ms)))

    def dismiss(self) -> None:
        self._timer.stop()
        if reduced_motion_enabled():
            self.hide()
            self.deleteLater()
            return
        self._fade.stop()
        self._fade.setDuration(130)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        try:
            self._fade.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._fade.finished.connect(self._finish_dismiss)
        self._fade.start()

    def _finish_dismiss(self) -> None:
        self.hide()
        self.deleteLater()


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
        self._mini_player_dismissed = False
        self._active_toasts: list[StudioToast] = []

        # Persistent Dragon Studio shell: grouped navigation on the left,
        # a compact project-aware top bar, and the existing functional pages.
        # Visible labels may evolve without changing the internal routing keys.
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.import_book_icon = _import_book_icon()
        sidebar_panel = QWidget()
        self.sidebar_panel = sidebar_panel
        sidebar_panel.setObjectName("studioSidebar")
        sidebar_panel.setFixedWidth(276)
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
        self.brand_col = brand_col
        brand_col.setSpacing(2)
        brand = QLabel("RYU'S AUDIOBOOK")
        self.brand_label = brand
        brand.setObjectName("brand")
        brand_col.addWidget(brand)
        edition = QLabel("DRAGON STUDIO")
        self.edition_label = edition
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
        self._nav_item_full_text: dict[int, str] = {}
        self._nav_item_icon_text: dict[int, str] = {}
        self._sidebar_collapsed = False
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setSpacing(3)
        self.sidebar.setIconSize(QSize(20, 20))
        self.nav_titles = {
            "Dashboard": "Dashboard",
            "Library": "Audiobook Library",
            "Import": "Import Studio",
            "Chapters": "Chapter Studio",
            "Voice & Narration": "Voice Studio",
            "Voice Cast": "Character Studio",
            "Character Library": "Character Library",
            "Pronunciation": "Pronunciation Studio",
            "Sound Design": "Sound Design Studio",
            "Generate": "Production Studio",
            "Audiobooks": "Audiobooks",
            "History": "Generation History",
            "Models": "Models Center",
            "Hardware": "Performance Center",
            "Settings": "Settings",
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
                self._nav_item_full_text[id(item)] = item.text()
                self._nav_item_icon_text[id(item)] = ("＋" if key == "Import" else icon_text.strip() or "•")

        add_nav_group("Home", [
            ("Dashboard", "Dashboard", "⌂"),
            ("Library", "Audiobook Library", "▤"),
        ])
        add_nav_group("Project", [
            ("Import", "Import Studio", ""),
            ("Chapters", "Chapter Studio", "☷"),
            ("Voice & Narration", "Voice Studio", "◉"),
            ("Voice Cast", "Character Studio", "♙"),
            ("Character Library", "Character Library", "♙"),
            ("Pronunciation", "Pronunciation Studio", "Aa"),
        ])
        add_nav_group("Production", [
            ("Sound Design", "Sound Design Studio", "♫"),
            ("Generate", "Production Studio", "▶"),
            ("Audiobooks", "Audiobooks", "▷"),
            ("History", "Generation History", "↻"),
        ])
        add_nav_group("System", [
            ("Models", "Models Center", "◆"),
            ("Hardware", "Performance Center", "⚙"),
            ("Settings", "Settings", "⚙"),
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
        self.project_mini_title.setWordWrap(False)
        self.project_mini_title.setToolTip("No book open")
        current_project_layout.addWidget(self.project_mini_title)
        self.project_mini_status = QLabel("No project selected")
        self.project_mini_status.setObjectName("muted")
        self._project_mini_status_text = "No project selected"
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

        self.menu_toggle = QPushButton("☰")
        self.menu_toggle.setObjectName("shellIconButton")
        self.menu_toggle.setToolTip("Collapse or expand navigation")
        self.menu_toggle.setFixedWidth(40)
        self.menu_toggle.clicked.connect(self.toggle_sidebar)
        header.insertWidget(0, self.menu_toggle)

        self.project_label = QLabel("No book open")
        self.project_label.setObjectName("projectPill")
        self.project_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.project_label.setMinimumWidth(110)
        self.project_label.setMaximumWidth(260)
        self.project_label.setToolTip("No book open")
        self.project_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.project_label)

        self.global_search = QLineEdit()
        self.global_search.setObjectName("globalSearch")
        self.global_search.setPlaceholderText("Search your local library…")
        self.global_search.setClearButtonEnabled(True)
        self.global_search.setMinimumWidth(130)
        self.global_search.setMaximumWidth(250)
        self.global_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.global_search.returnPressed.connect(self._search_library)
        header.addWidget(self.global_search)

        self.theme_toggle = QPushButton("◐")
        self.theme_toggle.setObjectName("shellIconButton")
        self.theme_toggle.setToolTip("Toggle dark and cream themes")
        self.theme_toggle.setFixedWidth(40)
        self.theme_toggle.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_toggle)

        self.notifications_button = QPushButton("♧ 0")
        self.notifications_button.setObjectName("shellIconButton")
        self.notifications_button.setToolTip("View local project warnings and generation status")
        self.notifications_button.clicked.connect(self.show_notifications)
        header.addWidget(self.notifications_button)
        self._refresh_notification_count()

        self.new_book_button = QPushButton("Import Book")
        self.new_book_button.setObjectName("primary")
        self.new_book_button.setIcon(self.import_book_icon)
        self.new_book_button.setIconSize(QSize(20, 20))
        self.new_book_button.clicked.connect(lambda: self.select_section("Import"))
        header.addWidget(self.new_book_button)
        main_layout.addLayout(header)

        # Persistent workflow rail mirrors the approved Dragon Studio prototype.
        # These buttons route into the existing pages; they are not demo-only tabs.
        self.workflow_step_buttons: dict[str, QPushButton] = {}
        workflow_rail = QWidget()
        workflow_rail.setObjectName("workflowRail")
        workflow_rail_layout = QHBoxLayout(workflow_rail)
        workflow_rail_layout.setContentsMargins(22, 9, 22, 10)
        workflow_rail_layout.setSpacing(8)
        for number, key, label in (
            ("01", "Import", "Import"),
            ("02", "Chapters", "Chapters"),
            ("03", "Voice & Narration", "Narrator"),
            ("04", "Voice Cast", "Characters"),
            ("05", "Pronunciation", "Pronunciation"),
            ("06", "Sound Design", "Sound Design"),
            ("07", "Generate", "Generate"),
            ("08", "Audiobooks", "Listen & Export"),
        ):
            button = QPushButton(f"{number}  ·  {label}")
            button.setObjectName("workflowStep")
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button.setToolTip(f"Open {label}")
            button.clicked.connect(lambda _checked=False, target=key: self._navigate_workflow_step(target))
            self.workflow_step_buttons[key] = button
            workflow_rail_layout.addWidget(button, 1)
        # Keep all eight workflow actions readable on compact windows.
        # The rail scrolls horizontally rather than squeezing labels or hiding steps.
        workflow_rail.setMinimumWidth(1080)
        workflow_scroll = QScrollArea()
        workflow_scroll.setObjectName("workflowRailScroll")
        workflow_scroll.setWidgetResizable(False)
        workflow_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        workflow_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        workflow_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        workflow_scroll.setFixedHeight(62)
        workflow_scroll.setWidget(workflow_rail)
        main_layout.addWidget(workflow_scroll)

        body = QHBoxLayout()
        body.setContentsMargins(22, 6, 22, 16)
        body.setSpacing(10)
        self.stack = QStackedWidget()
        self.stack.setObjectName("studioStack")
        body.addWidget(self.stack, 1)
        main_layout.addLayout(body, 1)

        # Persistent mini-player from the HTML prototype, backed by the same
        # QMediaPlayer used by the real local Audiobooks screen.
        self.mini_player_bar = QWidget()
        self.mini_player_bar.setObjectName("miniPlayerBar")
        mini_layout = QHBoxLayout(self.mini_player_bar)
        mini_layout.setContentsMargins(22, 8, 22, 8)
        mini_layout.setSpacing(12)
        self.mini_play_button = QPushButton("▶")
        self.mini_play_button.setObjectName("primary")
        self.mini_play_button.setFixedSize(40, 36)
        self.mini_play_button.setToolTip("Play or pause current audiobook")
        self.mini_play_button.clicked.connect(self._toggle_mini_playback)
        mini_layout.addWidget(self.mini_play_button)
        self.mini_title = QLabel("No audiobook playing")
        self.mini_title.setObjectName("sectionTitle")
        self.mini_title.setMinimumWidth(120)
        self.mini_title.setMaximumWidth(260)
        self.mini_title.setWordWrap(False)
        mini_layout.addWidget(self.mini_title)
        self.mini_position = QLabel("0:00")
        self.mini_position.setObjectName("muted")
        mini_layout.addWidget(self.mini_position)
        self.mini_timeline = QSlider(Qt.Orientation.Horizontal)
        self.mini_timeline.setRange(0, 0)
        self.mini_timeline.setToolTip("Seek through the current audiobook")
        self.mini_timeline.sliderMoved.connect(self._seek_mini_player)
        mini_layout.addWidget(self.mini_timeline, 1)
        self.mini_duration = QLabel("0:00")
        self.mini_duration.setObjectName("muted")
        mini_layout.addWidget(self.mini_duration)
        self.mini_open_button = QPushButton("Open Player")
        self.mini_open_button.clicked.connect(lambda: self.select_section("Audiobooks"))
        mini_layout.addWidget(self.mini_open_button)
        self.mini_hide_button = QPushButton("×")
        self.mini_hide_button.setObjectName("shellIconButton")
        self.mini_hide_button.setFixedSize(32, 32)
        self.mini_hide_button.setToolTip("Hide mini-player")
        self.mini_hide_button.clicked.connect(self._hide_mini_player)
        mini_layout.addWidget(self.mini_hide_button)
        self.mini_player_bar.setVisible(False)
        main_layout.addWidget(self.mini_player_bar)

        shell_layout.addWidget(sidebar_panel)
        shell_layout.addWidget(main_panel, 1)

        self.setCentralWidget(shell)
        self.loading_overlay = FrostedLoadingOverlay(shell)
        self.loading_overlay.setGeometry(shell.rect())

        self.library = LibraryPage(
            self.open_project,
            on_before_delete=self._before_project_delete,
            on_deleted=self._on_project_deleted,
        )
        self.import_page = ImportPage(self.handle_import)
        self.voice = VoicePage()

        self.dashboard = DashboardPage(
            self.open_project,
            lambda: self.select_section("Import"),
            lambda: self.select_section("Library"),
        )
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.library)
        self.stack.addWidget(self.import_page)
        self.stack.addWidget(self.voice)
        self.voice_cast = VoiceCastPage(
            lambda: self.project.chapters if self.project else [],
            lambda: self.project.source_path if self.project else None,
        )
        self.stack.addWidget(self.voice_cast)
        self.character_library_page = CharacterLibraryPage(
            on_open_in_studio=self._open_character_in_studio,
        )
        self.stack.addWidget(self.character_library_page)
        self.models_page = ModelsPage()
        self.stack.addWidget(self.models_page)
        self.hardware_page = HardwarePage()
        self.stack.addWidget(self.hardware_page)
        self.audiobooks_page = AudiobooksPage(self.open_project)
        self.stack.addWidget(self.audiobooks_page)
        self.audiobooks_page.player.sourceChanged.connect(self._mini_source_changed)
        self.audiobooks_page.player.positionChanged.connect(self._mini_position_changed)
        self.audiobooks_page.player.durationChanged.connect(self._mini_duration_changed)
        self.audiobooks_page.player.playbackStateChanged.connect(self._mini_playback_state_changed)
        self.audiobooks_page.player.errorOccurred.connect(self._mini_playback_error)
        self.history_page = HistoryPage(
            on_open_project=self.open_project,
            on_open_generation=lambda: self.select_section("Generate"),
        )
        self.stack.addWidget(self.history_page)
        self.settings_page = SettingsPage(self._settings_saved)
        self.stack.addWidget(self.settings_page)

        self.editor: ChapterEditorPage | None = None
        self.generation: GenerationPage | None = None
        self._generation_index = -1
        self._editor_index = -1

        # Row 0 is the non-selectable HOME heading; Library is the first destination.
        self.sidebar.setCurrentRow(1)
        stored_theme = str(QSettings("RyuBlanc", "Ryu's Audiobook").value("ui/theme", "dark")).lower()
        self.theme_toggle.setText("☀" if stored_theme == "light" else "◐")


    @staticmethod
    def _mini_time_text(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds // 1000))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"

    def _set_mini_player_visible(self, visible: bool) -> None:
        """Change bottom-bar layout only when the target visibility actually changes."""
        currently_hidden = self.mini_player_bar.isHidden()
        if visible and currently_hidden:
            self.mini_player_bar.setVisible(True)
        elif not visible and not currently_hidden:
            self.mini_player_bar.setVisible(False)

    def _mini_source_changed(self, source) -> None:
        # A non-empty source means Qt accepted a URL, not that it can decode
        # or play it. Keep the shell layout stable until PlayingState confirms
        # actual playback; unsupported old M4B files no longer pop the mini-player.
        if source.isEmpty():
            self._set_mini_player_visible(False)
            self.mini_title.setText("No audiobook playing")
            self.mini_title.setToolTip("")
            self.mini_timeline.setRange(0, 0)
            self.mini_timeline.setValue(0)
            self.mini_position.setText("0:00")
            self.mini_duration.setText("0:00")
            return
        self._mini_player_dismissed = False
        self.mini_title.setText(self.audiobooks_page.now_playing.text())
        self.mini_title.setToolTip(source.toLocalFile())
        # Preserve the existing layout while switching tracks. If the bar was
        # hidden, a source change does not reveal it; only successful playback does.

    def _mini_playback_error(self, _error, _error_text: str) -> None:
        # Error details stay in the Audiobooks page. The shared shell only hides
        # its compact controls: it does not retry, change pages, or show a toast.
        self._set_mini_player_visible(False)
        self.mini_play_button.setText("▶")

    def _hide_mini_player(self) -> None:
        self._mini_player_dismissed = True
        self._set_mini_player_visible(False)

    def _mini_position_changed(self, position: int) -> None:
        self.mini_timeline.blockSignals(True)
        self.mini_timeline.setValue(position)
        self.mini_timeline.blockSignals(False)
        self.mini_position.setText(self._mini_time_text(position))

    def _mini_duration_changed(self, duration: int) -> None:
        self.mini_timeline.setRange(0, max(0, duration))
        self.mini_duration.setText(self._mini_time_text(duration))

    def _mini_playback_state_changed(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        paused = state == QMediaPlayer.PlaybackState.PausedState
        self.mini_play_button.setText("Ⅱ" if playing else "▶")
        if playing:
            self.mini_title.setText(self.audiobooks_page.now_playing.text())
            if not self._mini_player_dismissed:
                self._set_mini_player_visible(True)
        elif paused:
            # Preserve a visible bar when pausing a track that already started,
            # but never reveal it for a merely selected or failed source.
            if not self._mini_player_dismissed and not self.mini_player_bar.isHidden():
                self.mini_title.setText(self.audiobooks_page.now_playing.text())
        # StoppedState intentionally does not reveal the mini-player.

    def _toggle_mini_playback(self) -> None:
        player = self.audiobooks_page.player
        from PySide6.QtMultimedia import QMediaPlayer
        if player.source().isEmpty():
            self.select_section("Audiobooks")
            return
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    def _seek_mini_player(self, position: int) -> None:
        self.audiobooks_page.player.setPosition(position)

    def toggle_sidebar(self) -> None:
        """Collapse to an icon rail or restore the full grouped navigation."""
        self._sidebar_collapsed = not self._sidebar_collapsed
        if self._sidebar_collapsed:
            self.sidebar_panel.setFixedWidth(78)
            self.brand_label.setVisible(False)
            self.edition_label.setVisible(False)
            # Keep the logo visible while removing the wordmark from the narrow rail.
            for row in range(self.sidebar.count()):
                item = self.sidebar.item(row)
                key = str(item.data(32) or "")
                if not key:
                    item.setHidden(True)
                    continue
                full = self._nav_item_full_text.get(id(item), item.text())
                icon = self._nav_item_icon_text.get(id(item), "•")
                item.setText(icon)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(self.nav_titles.get(key, full.strip()))
        else:
            self.sidebar_panel.setFixedWidth(276)
            self.brand_label.setVisible(True)
            self.edition_label.setVisible(True)
            for row in range(self.sidebar.count()):
                item = self.sidebar.item(row)
                item.setHidden(False)
                item.setText(self._nav_item_full_text.get(id(item), item.text()))
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                key = str(item.data(32) or "")
                if key:
                    item.setToolTip(self.nav_titles.get(key, item.text().strip()))
        self.sidebar.setMinimumWidth(0)
        self.sidebar.updateGeometry()

    def toggle_theme(self) -> None:
        """Switch between saved dark and cream palettes using the Settings theme engine."""
        settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        current = str(settings.value("ui/theme", "dark")).lower()
        target = "light" if current != "light" else "dark"
        settings.setValue("ui/theme", target)
        settings.sync()
        from app.ui.settings_page import apply_application_theme
        app = QApplication.instance()
        if app is not None:
            apply_application_theme(app, target)
        self.theme_toggle.setText("☀" if target == "light" else "◐")
        self.theme_toggle.setToolTip("Switch to dark theme" if target == "light" else "Switch to cream light theme")

    def _refresh_notification_count(self, force: bool = False) -> None:
        """Refresh the header count with a short cache to avoid disk scans on every page click."""
        now = time.monotonic()
        last = float(getattr(self, "_notification_count_last_refresh", 0.0) or 0.0)
        cached = getattr(self, "_notification_count_cache", None)
        if (
            not force
            and cached is not None
            and now - last < 3.0
        ):
            count = int(cached)
        else:
            count = 0
            for project in self._safe_list_projects():
                state = load_state(project.folder)
                status = str(state.get("status") or "new").strip().lower()
                if status in {"generating", "running", "queued", "failed", "cancelled"} or state.get("failed_chapters"):
                    count += 1
            self._notification_count_cache = count
            self._notification_count_last_refresh = now
        self.notifications_button.setText(f"♧ {count}")
        self.notifications_button.setToolTip(
            f"{count} local project(s) active or needing attention"
            if count else "No active or failed jobs recorded locally"
        )

    def show_notifications(self) -> None:
        """Show actual local project attention states; never fabricate a running job."""
        issues: list[str] = []
        active = 0
        for project in self._safe_list_projects():
            state = load_state(project.folder)
            status = str(state.get("status") or "new").strip().lower()
            failed = state.get("failed_chapters") or []
            if status in {"generating", "running", "queued"}:
                active += 1
                issues.append(f"IN PROGRESS · {project.title}")
            if status in {"failed", "cancelled"} or failed:
                detail = f"{len(failed)} failed chapter(s)" if failed else status
                issues.append(f"NEEDS ATTENTION · {project.title} — {detail}")
        if not issues:
            issues.append("No active or failed generation jobs are recorded in local project state.")
        # The HTML reference uses compact toasts; avoid blocking navigation with a modal dialog.
        summary = f"Active projects: {active}. " + " • ".join(issues[:3])
        if len(issues) > 3:
            summary += f" • and {len(issues) - 3} more"
        kind = "error" if any("NEEDS ATTENTION" in item for item in issues) else ("success" if not active else "info")
        self.show_toast("Local notifications", summary, kind, duration_ms=6500)

    def show_toast(self, title: str, message: str, kind: str = "info", duration_ms: int = 4200) -> None:
        """Show a truthful, dismissible toast without blocking the UI thread."""
        host = self.centralWidget()
        if host is None:
            return
        toast = StudioToast(host, title, message, kind)
        self._active_toasts.append(toast)
        toast.destroyed.connect(lambda _obj=None, item=toast: self._discard_toast(item))
        toast.show_toast(duration_ms)

    def _discard_toast(self, toast: StudioToast) -> None:
        self._active_toasts = [item for item in self._active_toasts if item is not toast]

    @staticmethod
    def _safe_list_projects():
        from app.core.project import list_projects
        try:
            return list_projects()
        except Exception:
            return []

    def apply_window_size(self, choice: str) -> None:
        """Apply saved native geometry while respecting the active display work area."""
        choice = str(choice or "auto").strip().lower()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            min_width = max(480, min(960, int(available.width())))
            min_height = max(360, min(620, int(available.height())))
        else:
            min_width, min_height = 960, 620
        self.setMinimumSize(min_width, min_height)
        if choice == "maximized":
            self.showMaximized()
            return
        if self.isMaximized():
            self.showNormal()
        if choice == "auto":
            width = int(available.width() * 0.90) if available is not None else 1440
            height = int(available.height() * 0.90) if available is not None else 900
            width = min(1600, max(min_width, width))
            height = min(1000, max(min_height, height))
        else:
            try:
                width, height = (int(part) for part in choice.split("x", 1))
            except (TypeError, ValueError):
                width, height = 1440, 900
        if available is not None:
            width = min(width, int(available.width()))
            height = min(height, int(available.height()))
        self.resize(max(min_width, width), max(min_height, height))

    def _settings_saved(self, reduce_motion: bool) -> None:
        """Apply saved UI preferences to an already-open native generation page."""
        if self.generation is not None and self.stack.indexOf(self.generation) >= 0:
            setter = getattr(self.generation, "_set_reduce_motion", None)
            if callable(setter):
                setter(bool(reduce_motion))
        self.apply_window_size(str(QSettings("RyuBlanc", "Ryu's Audiobook").value("ui/window_size", "auto")))

    def resizeEvent(self, event) -> None:
        """Keep the header, mini-player, and loading overlay responsive on resize."""
        super().resizeEvent(event)
        width = event.size().width()
        # Keep the project title available in the sidebar card when the header
        # is compact, and reserve room for the search and primary action.
        compact_header = width < 1240
        self.project_label.setVisible(not compact_header)
        self.global_search.setMaximumWidth(180 if width < 1400 else 250)
        # Collapse secondary playback labels before the seek bar is squeezed.
        compact_player = width < 1080
        self.mini_title.setVisible(not compact_player)
        self.mini_position.setVisible(not compact_player)
        self.mini_duration.setVisible(not compact_player)
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

    def _set_project_mini_status(self, status: str) -> None:
        """Publish a real project save/open status to the persistent sidebar card."""
        self._project_mini_status_text = str(status or "No project selected")
        label = getattr(self, "project_mini_status", None)
        if label is not None:
            label.setText(self._project_mini_status_text)

    def _set_project_title(self, title: str) -> None:
        self._project_title_full = title or "No book open"
        if self.project is None:
            self._set_project_mini_status("No project selected")
        elif not getattr(self, "_project_mini_status_text", ""):
            self._set_project_mini_status("Saved locally")
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
            mini_width = max(80, self.project_mini_title.contentsRect().width() - 8)
            mini_text = QFontMetrics(self.project_mini_title.font()).elidedText(
                title, Qt.TextElideMode.ElideRight, mini_width
            )
            self.project_mini_title.setText(mini_text)
            self.project_mini_title.setToolTip(title)
            status = getattr(
                self, "_project_mini_status_text",
                "Saved locally" if self.project is not None else "No project selected",
            )
            self.project_mini_status.setText(status)

    def _search_library(self) -> None:
        """Route top-bar search to the real local library filter."""
        query = self.global_search.text().strip()
        if not query:
            return
        self.select_section("Library")
        self._show_page(self.library)
        self.library.search.setText(query)

    def _sync_workflow_steps(self) -> None:
        current_item = self.sidebar.currentItem() if hasattr(self, "sidebar") else None
        current_key = str(current_item.data(32) or "") if current_item is not None else ""
        stage_for_key = {
            "Import": "Import",
            "Chapters": "Chapters",
            "Voice & Narration": "Voice & Narration",
            "Voice Cast": "Voice Cast",
            "Pronunciation": "Pronunciation",
            "Sound Design": "Sound Design",
            "Generate": "Generate",
            "Audiobooks": "Audiobooks",
        }
        active = stage_for_key.get(current_key)
        for key, button in getattr(self, "workflow_step_buttons", {}).items():
            button.setChecked(key == active)

    def _update_page_chrome(self, widget: QWidget) -> None:
        self._sync_workflow_steps()
        # Pronunciation and Sound Design are focused views into the same real
        # per-book production workspace, not duplicate/mock implementations.
        selected = ""
        current_item = self.sidebar.currentItem() if hasattr(self, "sidebar") else None
        if current_item is not None:
            selected = str(current_item.data(32) or "")
        focused_chrome = {
            "Pronunciation": (
                "Pronunciation Studio",
                "Correct names and terms, audition changes, and save per-book overrides.",
            ),
            "Sound Design": (
                "Sound Design Studio",
                "Configure real local BGM, chapter cues, mixing levels, and transitions.",
            ),
            "Generate": (
                "Production Studio",
                "Preview, generate, recover, and assemble your audiobook.",
            ),
        }
        if widget is self.generation and selected in focused_chrome:
            heading, subtitle = focused_chrome[selected]
            self.page_heading.setText(heading)
            self.page_subheading.setText(subtitle)
            return

        pages = [
            (self.dashboard, "Dashboard", "A live summary of your local audiobook workspace."),
            (getattr(self, "pronunciation_page", None), "Pronunciation", "Correct names and terms, audition changes, and save per-book overrides."),
            (getattr(self, "sound_design_page", None), "Sound Design", "Configure contextual music, chapter transitions, and audio quality."),
            (self.library, "Library", "Your local audiobook projects and ongoing work."),
            (self.import_page, "Import", "Bring a source book into your local workflow."),
            (self.voice, "Voice & Narration", "Choose, configure, and preview the narrator."),
            (self.voice_cast, "Voice Cast", "Review dialogue and assign character voices."),
            (getattr(self, "character_library_page", None), "Character Library", "Browse reusable series-level character names, aliases, voice profiles, and dialogue samples."),
            (self.audiobooks_page, "Audiobooks", "Listen to finished local audiobook files in the app."),
            (self.history_page, "History", "Review real project and generation status from local files."),
            (self.settings_page, "Settings", "Manage appearance, local folders, and diagnostics."),
        ]
        if self.editor is not None:
            pages.append((self.editor, "Chapters", "Review and edit your book chapter by chapter."))
        if self.generation is not None:
            pages.append((self.generation, "Generate", "Preview, generate, recover, and assemble your audiobook."))
        pages.append((self.models_page, "Models", "Manage local speech and analysis components."))
        pages.append((self.hardware_page, "Hardware", "Verify local backends and review hardware performance."))
        for page, key, subtitle in pages:
            if page is not None and page is widget:
                self.page_heading.setText(self.nav_titles.get(key, key))
                self.page_subheading.setText(subtitle)
                return

    def _show_page(self, widget: QWidget) -> None:
        """Switch pages without opacity effects that can flash black on Windows."""
        self._refresh_notification_count()
        if widget is None:
            return
        if self.stack.indexOf(widget) < 0:
            raise RuntimeError(
                f"Cannot navigate to {type(widget).__name__}: page is not in the workflow stack."
            )

        # QWidget graphics effects are expensive for the stacked pages and can
        # briefly composite a black frame during rapid navigation on Windows.
        # Stop and detach any effect left by an earlier transition before
        # changing the visible page.
        if self._page_animation is not None:
            try:
                self._page_animation.stop()
            except RuntimeError:
                pass
        if self._page_animation_widget is not None:
            try:
                self._page_animation_widget.setGraphicsEffect(None)
            except RuntimeError:
                pass
        self._page_animation = None
        self._page_animation_widget = None

        self._sync_workflow_steps()
        self._update_page_chrome(widget)
        self.stack.setCurrentWidget(widget)

    def _sidebar_item_clicked(self, item: QListWidgetItem) -> None:
        """Recover navigation when the clicked row is already selected."""
        row = self.sidebar.row(item)
        if row < 0:
            return
        name = str(item.data(32) or "")
        if name == "Dashboard":
            expected = self.dashboard
        elif name == "Generate":
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
        elif name == "Character Library":
            expected = self.character_library_page
        elif name in {"Pronunciation", "Sound Design"}:
            expected = self.generation if self.project else self.import_page
        elif name == "Audiobooks":
            expected = self.audiobooks_page
        elif name == "History":
            expected = self.history_page
        elif name == "Settings":
            expected = self.settings_page
        elif name == "Models":
            expected = self.models_page
        elif name == "Hardware":
            expected = self.hardware_page
        else:
            return
        # Alias views must also re-run when already selected so their focus target
        # is restored after navigation from another page or a stale stacked widget.
        if (
            expected is None
            or self.stack.currentWidget() is not expected
            or name in {"Pronunciation", "Sound Design"}
        ):
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

    def _open_generation_feature(self, feature: str) -> None:
        """Open the dedicated, book-specific Pronunciation or Sound Design screen."""
        key = "Pronunciation" if feature == "pronunciation" else "Sound Design"
        if not self.project:
            selected_projects = self.library._selected_projects()
            if selected_projects:
                self.open_project(selected_projects[0])
                for index in range(self.sidebar.count()):
                    if self.sidebar.item(index).data(32) == key:
                        self.sidebar.blockSignals(True)
                        try:
                            self.sidebar.setCurrentRow(index)
                        finally:
                            self.sidebar.blockSignals(False)
                        break
            else:
                self._show_page(self.library)
                self.page_subheading.setText(
                    f"Select a book in Library or import one to open {key}."
                )
                return
        if not self.project:
            return
        if (
            self.generation is None
            or self.stack.indexOf(self.generation) < 0
            or self.generation.project_folder != self.project.folder
        ):
            self.ensure_generation_page()
        target = self.pronunciation_page if feature == "pronunciation" else self.sound_design_page
        if target is None or self.stack.indexOf(target) < 0:
            QMessageBox.warning(self, key, f"{key} could not be initialized. Open Generate once and try again.")
            return
        self._show_page(target)


    def _install_generation_feature_pages(self, generation_page: GenerationPage) -> None:
        """Mount the existing production controls on dedicated reference-design screens."""
        old_pronunciation = getattr(self, "pronunciation_page", None)
        old_sound_design = getattr(self, "sound_design_page", None)
        for old_page in (old_pronunciation, old_sound_design):
            if old_page is not None:
                if self.stack.indexOf(old_page) >= 0:
                    self.stack.removeWidget(old_page)
                old_page.hide()
                old_page.deleteLater()

        self.pronunciation_page = QWidget()
        self.pronunciation_page.setObjectName("pronunciationStudioPage")
        pronunciation_layout = QVBoxLayout(self.pronunciation_page)
        pronunciation_layout.setContentsMargins(8, 6, 8, 8)
        pronunciation_layout.setSpacing(10)
        pronunciation_layout.addWidget(QLabel("<h2>Pronunciation Studio</h2>"))
        pronunciation_subtitle = QLabel(
            "Correct character names and story terms, audition changes with the selected voice, and save book-specific overrides."
        )
        pronunciation_subtitle.setObjectName("muted")
        pronunciation_subtitle.setWordWrap(True)
        pronunciation_layout.addWidget(pronunciation_subtitle)
        pronunciation_scroll = QScrollArea()
        pronunciation_scroll.setWidgetResizable(True)
        pronunciation_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        pronunciation_content = QWidget()
        pronunciation_content_layout = QVBoxLayout(pronunciation_content)
        pronunciation_content_layout.setContentsMargins(2, 2, 8, 8)
        pronunciation_content_layout.setSpacing(12)
        generation_page.content_root_layout.removeWidget(generation_page.pronunciation_box)
        pronunciation_content_layout.addWidget(generation_page.pronunciation_box)
        pronunciation_content_layout.addStretch(1)
        pronunciation_scroll.setWidget(pronunciation_content)
        pronunciation_layout.addWidget(pronunciation_scroll, 1)
        self.stack.addWidget(self.pronunciation_page)

        self.sound_design_page = QWidget()
        self.sound_design_page.setObjectName("soundDesignStudioPage")
        sound_layout = QVBoxLayout(self.sound_design_page)
        sound_layout.setContentsMargins(8, 6, 8, 8)
        sound_layout.setSpacing(10)
        sound_layout.addWidget(QLabel("<h2>Sound Design Studio</h2>"))
        sound_subtitle = QLabel(
            "Configure narration quality, contextual background music, opening sounds, chapter transitions, and closing cues."
        )
        sound_subtitle.setObjectName("muted")
        sound_subtitle.setWordWrap(True)
        sound_layout.addWidget(sound_subtitle)

        # Reusable local sound presets mirror the HTML's Save preset / Apply to book
        # controls. Presets contain settings only; imported audio remains in its
        # existing local library and is never copied to a cloud service.
        preset_toolbar = QHBoxLayout()
        preset_toolbar.setSpacing(8)
        preset_toolbar.addWidget(QLabel("Sound preset"))
        self.sound_preset_combo = QComboBox()
        self.sound_preset_combo.setObjectName("soundPresetSelector")
        self.sound_preset_combo.setMinimumWidth(220)
        preset_toolbar.addWidget(self.sound_preset_combo, 1)
        self.sound_preset_save_button = QPushButton("Save preset")
        self.sound_preset_save_button.setObjectName("soundPresetSave")
        self.sound_preset_save_button.clicked.connect(self._save_sound_preset)
        preset_toolbar.addWidget(self.sound_preset_save_button)
        self.sound_preset_apply_button = QPushButton("Apply to book")
        self.sound_preset_apply_button.setObjectName("soundPresetApply")
        self.sound_preset_apply_button.clicked.connect(self._apply_sound_preset)
        preset_toolbar.addWidget(self.sound_preset_apply_button)
        self.sound_preset_delete_button = QPushButton("Delete preset")
        self.sound_preset_delete_button.setObjectName("soundPresetDelete")
        self.sound_preset_delete_button.clicked.connect(self._delete_sound_preset)
        preset_toolbar.addWidget(self.sound_preset_delete_button)
        sound_layout.addLayout(preset_toolbar)
        self.sound_preset_status = QLabel("Presets are stored locally on this PC.")
        self.sound_preset_status.setObjectName("muted")
        self.sound_preset_status.setWordWrap(True)
        sound_layout.addWidget(self.sound_preset_status)
        self._refresh_sound_preset_list()

        sound_scroll = QScrollArea()
        sound_scroll.setWidgetResizable(True)
        sound_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        sound_content = QWidget()
        sound_content_layout = QVBoxLayout(sound_content)
        sound_content_layout.setContentsMargins(2, 2, 8, 8)
        sound_content_layout.setSpacing(12)
        # Cue cards are already part of Audio settings. Keep them nested there
        # so the settings form does not retain an empty placeholder row.
        generation_page.content_root_layout.removeWidget(generation_page.audio_settings_box)
        sound_content_layout.addWidget(generation_page.audio_settings_box)
        sound_content_layout.addStretch(1)
        sound_scroll.setWidget(sound_content)
        sound_layout.addWidget(sound_scroll, 1)
        self.stack.addWidget(self.sound_design_page)

    @staticmethod
    def _sound_preset_settings(page: GenerationPage) -> dict:
        """Capture supported sound controls as portable, local preset values."""
        return {
            "background_audio_enabled": page.background_audio_enabled.isChecked(),
            "background_audio_mode": str(page.background_audio_mode.currentData() or "auto"),
            "auto_music_style": str(page.auto_music_style.currentData() or "auto"),
            "auto_music_track_path": (
                str(page.bgm_variation.currentData() or "")
                if str(page.bgm_variation.currentData() or "auto") != "auto" else ""
            ),
            "chapter_transition_sound": page.chapter_transition_sound.isChecked(),
            "story_effects_enabled": page.story_effects_enabled.isChecked(),
            "story_effect_volume": float(page.story_effect_volume.value()) / 100.0,
            "background_audio_path": page.background_audio_path.text().strip(),
            "background_audio_volume": float(page.background_audio_volume.value()) / 100.0,
            "ambience_audio_path": page.ambience_audio_path.text().strip(),
            "ambience_audio_volume": float(page.ambience_audio_volume.value()) / 100.0,
            "background_audio_fade_in": int(page.background_audio_fade_in.value()),
            "background_audio_fade_out": int(page.background_audio_fade_out.value()),
            "opening_cue_path": page.opening_cue_path.text().strip(),
            "page_turn_cue_path": page.page_turn_cue_path.text().strip(),
            "ending_cue_path": page.ending_cue_path.text().strip(),
            "audio_bitrate": int(page.audio_bitrate.currentData() or 256),
        }

    @staticmethod
    def _sound_preset_store() -> QSettings:
        return QSettings("RyuBlanc", "Ryu's Audiobook")

    def _load_sound_presets(self) -> list[dict]:
        raw = self._sound_preset_store().value("sound/presets", "[]")
        try:
            parsed = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = []
        return [
            item for item in parsed
            if isinstance(item, dict) and str(item.get("name") or "").strip()
            and isinstance(item.get("settings"), dict)
        ] if isinstance(parsed, list) else []

    def _write_sound_presets(self, presets: list[dict]) -> None:
        settings = self._sound_preset_store()
        settings.setValue("sound/presets", json.dumps(presets, ensure_ascii=False))
        settings.sync()

    def _refresh_sound_preset_list(self, selected_name: str | None = None) -> None:
        combo = getattr(self, "sound_preset_combo", None)
        if combo is None:
            return
        presets = self._load_sound_presets()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Choose a saved preset…", "")
        for preset in presets:
            combo.addItem(str(preset["name"]), str(preset["name"]))
        target = selected_name or ""
        index = combo.findData(target)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)
        enabled = bool(presets)
        self.sound_preset_apply_button.setEnabled(enabled)
        self.sound_preset_delete_button.setEnabled(enabled and bool(combo.currentData()))

    def _save_sound_preset(self) -> None:
        if self.generation is None or self.project is None:
            self.sound_preset_status.setText("Open a book before saving its sound settings as a preset.")
            return
        current = self.sound_preset_combo.currentData()
        default_name = str(current or f"{self.project.title} sound")
        name, accepted = QInputDialog.getText(
            self, "Save sound preset", "Preset name:", text=default_name
        )
        name = name.strip()
        if not accepted or not name:
            return
        presets = self._load_sound_presets()
        settings = self._sound_preset_settings(self.generation)
        found = next((p for p in presets if str(p["name"]).casefold() == name.casefold()), None)
        if found is not None:
            found["name"] = name
            found["settings"] = settings
        else:
            presets.append({"name": name, "settings": settings})
        self._write_sound_presets(presets)
        self._refresh_sound_preset_list(name)
        self.sound_preset_status.setText(f"Saved “{name}” locally. Use Apply to book to save it to the open project.")

    def _apply_sound_preset(self) -> None:
        if self.generation is None or self.project is None:
            self.sound_preset_status.setText("Open a book before applying a sound preset.")
            return
        name = str(self.sound_preset_combo.currentData() or "")
        preset = next((p for p in self._load_sound_presets() if str(p["name"]) == name), None)
        if not preset:
            self.sound_preset_status.setText("Choose a saved sound preset first.")
            return
        values = dict(preset["settings"])
        page = self.generation
        def set_combo(combo, value) -> None:
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        for key, value in (
            ("background_audio_enabled", values.get("background_audio_enabled", False)),
            ("chapter_transition_sound", values.get("chapter_transition_sound", True)),
            ("story_effects_enabled", values.get("story_effects_enabled", True)),
        ):
            getattr(page, key).setChecked(bool(value))
        set_combo(page.background_audio_mode, values.get("background_audio_mode", "auto"))
        set_combo(page.auto_music_style, values.get("auto_music_style", "auto"))
        track_path = str(values.get("auto_music_track_path") or "")
        set_combo(page.bgm_variation, track_path or "auto")
        set_combo(page.audio_bitrate, int(values.get("audio_bitrate", 256)))
        page.story_effect_volume.setValue(float(values.get("story_effect_volume", 0.22)) * 100.0)
        page.background_audio_volume.setValue(float(values.get("background_audio_volume", 0.25)) * 100.0)
        page.ambience_audio_volume.setValue(float(values.get("ambience_audio_volume", 0.10)) * 100.0)
        page.background_audio_path.setText(str(values.get("background_audio_path") or ""))
        page.ambience_audio_path.setText(str(values.get("ambience_audio_path") or ""))
        page.background_audio_fade_in.setValue(int(values.get("background_audio_fade_in", 2)))
        page.background_audio_fade_out.setValue(int(values.get("background_audio_fade_out", 3)))
        page.opening_cue_path.setText(str(values.get("opening_cue_path") or ""))
        page.page_turn_cue_path.setText(str(values.get("page_turn_cue_path") or ""))
        page.ending_cue_path.setText(str(values.get("ending_cue_path") or ""))
        page._toggle_background_audio_controls(page.background_audio_enabled.isChecked())
        state = load_state(self.project.folder)
        state.update(values)
        save_state(self.project.folder, state)
        page.status.setText(f"Sound preset “{name}” applied and saved to this book.")
        self.sound_preset_status.setText(f"Applied “{name}” to {self.project.title} and saved the project settings.")

    def _delete_sound_preset(self) -> None:
        name = str(self.sound_preset_combo.currentData() or "")
        if not name:
            self.sound_preset_status.setText("Choose a saved preset to delete.")
            return
        presets = [p for p in self._load_sound_presets() if str(p["name"]) != name]
        self._write_sound_presets(presets)
        self._refresh_sound_preset_list()
        self.sound_preset_status.setText(f"Deleted local sound preset “{name}”.")

    def _sidebar_changed(self, row: int) -> None:
        if row < 0 or row >= self.sidebar.count():
            return
        item = self.sidebar.item(row)
        if item is None:
            return
        name = item.data(32)

        if name == "Dashboard":
            self.dashboard.refresh()
            self._show_page(self.dashboard)
        elif name == "Library":
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
                self.voice_cast.load_current_project()
            except Exception as exc:
                self._log_ui_failure("Refresh Voice Cast profiles", exc)
            self._show_page(self.voice_cast)
        elif name == "Character Library":
            self.character_library_page.refresh()
            self._show_page(self.character_library_page)
        elif name == "Pronunciation":
            self._open_generation_feature("pronunciation")
        elif name == "Sound Design":
            self._open_generation_feature("sound")
        elif name == "Audiobooks":
            self.audiobooks_page.refresh()
            self._show_page(self.audiobooks_page)
        elif name == "History":
            self.history_page.refresh()
            self._show_page(self.history_page)
        elif name == "Settings":
            self.settings_page.refresh()
            self._show_page(self.settings_page)
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
                        self.page_subheading.setText(
                            "Select a book in Library or import a new book to start generating."
                        )
                        return
                if not self._generation_page_is_current():
                    # Drop a stale/unregistered page reference before rebuilding;
                    # ensure_generation_page must not inspect a deleted Qt wrapper.
                    stale_generation = self.generation
                    self.generation = None
                    self._generation_index = -1
                    if stale_generation is not None:
                        try:
                            if self.stack.indexOf(stale_generation) >= 0:
                                self.stack.removeWidget(stale_generation)
                            stale_generation.hide()
                            stale_generation.deleteLater()
                        except RuntimeError:
                            # Qt may already have destroyed the underlying widget.
                            pass
                    self.ensure_generation_page()
                if not self._generation_page_is_current():
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
            self._show_page(self.models_page)
        elif name == "Hardware":
            self._show_page(self.hardware_page)

    def _navigate_workflow_step(self, name: str) -> None:
        current = self.sidebar.currentItem()
        if current is not None and current.data(32) == name:
            # Same-row clicks do not emit currentRowChanged; still recover a stale
            # stacked page (notably the Generate/Production destination).
            self._sidebar_changed(self.sidebar.currentRow())
            return
        self.select_section(name)

    def select_section(self, name: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(32) == name:
                self.sidebar.setCurrentRow(i)
                return

    def handle_import(self, path: Path, book=None, chapters=None) -> None:
        if self._import_worker is not None and self._import_worker.isRunning():
            return
        self.import_page.project_creation_started(path)
        self.loading_overlay.show_loading(
            "Importing your book",
            f"Adding {Path(path).name} to the local Library and saving its chapter structure…",
        )
        worker = ImportBookWorker(path, book=book, chapters=chapters)
        self._import_worker = worker
        worker.status.connect(self.loading_overlay.set_detail)
        worker.completed.connect(self._import_completed)
        worker.failed.connect(self._import_failed)
        worker.finished.connect(self._import_worker_finished)
        worker.start()

    def _import_completed(self, project: Project) -> None:
        self.loading_overlay.dismiss()
        self.import_page.project_created(project)
        self.project = project
        self._set_project_title(project.title)
        self._set_project_mini_status("Imported • saved locally")
        self.library.refresh()
        self.dashboard.refresh()
        self.open_editor()

    def _import_failed(self, message: str) -> None:
        self.loading_overlay.dismiss()
        self.import_page.project_creation_failed(message)
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
        self._set_project_mini_status("Renamed • saved locally")
        self.library.refresh()
        self.dashboard.refresh()
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
            self._set_project_mini_status("No project selected")
            return False
        self._set_project_mini_status("Saving…")
        try:
            self.project.chapters = list(chapters)
            self.project.save()
            self._set_project_mini_status("Autosaved just now")
            return True
        except Exception as exc:
            self._set_project_mini_status("Autosave failed • use Save")
            self._log_ui_failure("Autosave project", exc)
            return False

    def save_project(self, chapters: list[Chapter]) -> bool:
        if not self.project:
            self._set_project_mini_status("No project selected")
            return False
        self._set_project_mini_status("Saving…")
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
            self._set_project_mini_status("Saved just now")
            return True
        except Exception as exc:
            self._set_project_mini_status("Save failed • check details")
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

    def _generation_page_is_current(self) -> bool:
        """Return whether the Generate widget is alive and belongs to the active book.

        Qt widgets can be removed/recreated during project saves and renames. A
        stale Python wrapper or an unregistered page must never block the next
        Generate click; treat either case as a cache miss and rebuild safely.
        """
        page = self.generation
        project = self.project
        if page is None or project is None:
            return False
        try:
            return (
                self.stack.indexOf(page) >= 0
                and page.project_folder == project.folder
            )
        except RuntimeError:
            # Qt has already destroyed the underlying C++ widget.
            return False

    def ensure_generation_page(self) -> None:
        if not self.project:
            return

        # Build the replacement before touching the current widget. Previously,
        # the old page was removed and scheduled for deletion first; if the new
        # constructor raised, self.generation could still point at a deleted Qt
        # object and every later click on Generate failed with a C++ object error.
        old_generation = self.generation
        old_current_page = self.stack.currentWidget()
        old_was_pronunciation = old_current_page is getattr(self, "pronunciation_page", None)
        old_was_sound_design = old_current_page is getattr(self, "sound_design_page", None)
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
        # Register the core Generate page before installing the optional
        # Pronunciation and Sound Design wrappers. A failure in either wrapper
        # must never make the entire production screen inaccessible.
        self.generation = new_generation
        self._generation_index = self.stack.indexOf(new_generation)
        try:
            self._install_generation_feature_pages(new_generation)
        except Exception as exc:
            self._log_ui_failure("Install optional Generate feature pages", exc)
            for attribute in ("pronunciation_page", "sound_design_page"):
                page = getattr(self, attribute, None)
                if page is None:
                    continue
                try:
                    if self.stack.indexOf(page) >= 0:
                        self.stack.removeWidget(page)
                    page.hide()
                    page.deleteLater()
                except RuntimeError:
                    # Qt may already have destroyed a partially built wrapper.
                    pass
                setattr(self, attribute, None)
            if hasattr(new_generation, "status"):
                new_generation.status.setText(
                    "Generate is available, but Pronunciation/Sound Design screens "
                    f"could not be mounted ({type(exc).__name__}: {exc}). "
                    "See Logs/application.log for details."
                )
        if old_was_current or old_was_pronunciation or old_was_sound_design:
            self.stack.setCurrentWidget(new_generation)
        if old_generation is not None and old_generation is not new_generation:
            if self.stack.indexOf(old_generation) >= 0:
                self.stack.removeWidget(old_generation)
            old_generation.hide()
            old_generation.deleteLater()

    def _before_project_delete(self, project: Project) -> None:
        """Release local media handles before deleting their source files on Windows."""
        for page in (
            getattr(self, "audiobooks_page", None),
            getattr(self, "generation", None),
            getattr(self, "voice", None),
        ):
            if page is None:
                continue
            for name in ("player", "music_player", "preview_player", "pronunciation_player"):
                player = getattr(page, name, None)
                stop = getattr(player, "stop", None)
                if callable(stop):
                    try:
                        stop()
                    except RuntimeError:
                        pass

    def _on_project_deleted(self, project: Project) -> None:
        """Refresh dependent views and drop stale widget references after deletion."""
        active_folder = str(self.project.folder.resolve()) if self.project else ""
        deleted_folder = str(project.folder.resolve())
        if active_folder and active_folder == deleted_folder:
            self.project = None
            self._set_project_title("No book open")
            self._set_project_mini_status("No project selected")
            for attribute in ("pronunciation_page", "sound_design_page", "editor", "generation"):
                page = getattr(self, attribute, None)
                if page is None:
                    continue
                try:
                    if self.stack.indexOf(page) >= 0:
                        self.stack.removeWidget(page)
                    page.hide()
                    page.deleteLater()
                except RuntimeError:
                    pass
                setattr(self, attribute, None)
            self._editor_index = -1
            self._generation_index = -1
            try:
                self.voice_cast.load_current_project()
            except Exception as exc:
                self._log_ui_failure("Reset Character Studio after project deletion", exc)
            self.select_section("Library")
        try:
            self.import_page.clear_if_source_deleted(project.source_path)
        except Exception as exc:
            self._log_ui_failure("Clear stale Import Studio state after deletion", exc)
        self.history_page.refresh()
        self.dashboard.refresh()
        self.audiobooks_page.refresh()
        self.character_library_page.refresh()
        self._refresh_notification_count(force=True)

    def _open_character_in_studio(self, record: dict) -> None:
        """Open a volume belonging to a character's series, then focus that cast member."""
        from app.core.project import list_projects
        from app.core.state import load_state

        series = str(record.get("series") or "").strip()
        wanted = series.casefold()
        candidates = []
        for project in list_projects():
            state = load_state(project.folder)
            metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
            project_series = str(state.get("series_name") or state.get("series") or metadata.get("series") or project.title).strip()
            if project_series.casefold() == wanted:
                candidates.append(project)
        if self.project and str(self.project.folder.resolve()) in {str(item.folder.resolve()) for item in candidates}:
            target = self.project
        elif candidates:
            target = max(candidates, key=lambda item: item.folder.stat().st_mtime if item.folder.exists() else 0)
        else:
            QMessageBox.information(
                self,
                "Series not found in Library",
                f"No local book is currently assigned to the series '{series}'. Open a volume in Character Studio and save this same series name to link it.",
            )
            return
        self.open_project(target)
        self.select_section("Voice Cast")
        QTimer.singleShot(
            0,
            lambda name=str(record.get("primary_name") or ""): self.voice_cast.select_character_name(name),
        )

    def closeEvent(self, event) -> None:
        """Stop optional character-preview workers before their Qt widgets are destroyed."""
        try:
            if hasattr(self, "character_library_page"):
                self.character_library_page.shutdown()
        except Exception as exc:
            self._log_ui_failure("Character Library shutdown", exc)
        super().closeEvent(event)

    def open_project(self, project: Project) -> None:
        self.project = project
        self._set_project_title(project.title)
        self._set_project_mini_status("Opened • saved locally")
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
