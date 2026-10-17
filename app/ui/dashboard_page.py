from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.project import Project, list_projects
from app.core.state import load_state
from app.ui.library import project_status


class DashboardPage(QWidget):
    """Project-backed home dashboard; it never invents generation progress."""

    def __init__(self, on_open_project=None, on_import=None, on_open_library=None) -> None:
        super().__init__()
        self.on_open_project = on_open_project
        self.on_import = on_import
        self.on_open_library = on_open_library
        self.projects: list[Project] = []
        self.visible_projects: list[Project] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(16)

        hero = QHBoxLayout()
        intro = QVBoxLayout()
        eyebrow = QLabel("DRAGON STUDIO EDITION")
        eyebrow.setObjectName("brandEdition")
        intro.addWidget(eyebrow)
        title = QLabel("Welcome to Ryu's Audiobook")
        title.setObjectName("pageHeading")
        intro.addWidget(title)
        description = QLabel(
            "Your local workspace for importing books, shaping narration, "
            "and producing polished audiobooks."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        intro.addWidget(description)
        hero.addLayout(intro, 1)

        self.import_button = QPushButton("Import a Book")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._import)
        hero.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.library_button = QPushButton("Open Library")
        self.library_button.clicked.connect(self._open_library)
        hero.addWidget(self.library_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(hero)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metric_total = self._metric("LOCAL PROJECTS", "0", "All imported books")
        self.metric_completed = self._metric("COMPLETED", "0", "Validated audiobook output")
        self.metric_active = self._metric("IN PROGRESS", "0", "Jobs marked as running")
        self.metric_attention = self._metric("NEEDS ATTENTION", "0", "Failed or recoverable projects")
        for card in (
            self.metric_total, self.metric_completed, self.metric_active, self.metric_attention
        ):
            metrics.addWidget(card, 1)
        root.addLayout(metrics)

        lower = QHBoxLayout()
        lower.setSpacing(14)

        recent_card = QGroupBox("Recent local projects")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setSpacing(8)
        self.recent_list = QListWidget()
        self.recent_list.setMinimumHeight(230)
        self.recent_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.recent_list.currentRowChanged.connect(self._show_selected)
        recent_layout.addWidget(self.recent_list, 1)
        recent_actions = QHBoxLayout()
        self.continue_button = QPushButton("Open / Continue Project")
        self.continue_button.setObjectName("primary")
        self.continue_button.clicked.connect(self._continue_selected)
        recent_actions.addWidget(self.continue_button)
        recent_actions.addStretch(1)
        recent_layout.addLayout(recent_actions)
        lower.addWidget(recent_card, 3)

        attention_card = QGroupBox("Project status")
        attention_layout = QVBoxLayout(attention_card)
        self.status_title = QLabel("Your library is ready")
        self.status_title.setObjectName("sectionTitle")
        self.status_detail = QLabel(
            "Project status is read from your local project files. "
            "No generation estimates are shown until real job data is available."
        )
        self.status_detail.setObjectName("muted")
        self.status_detail.setWordWrap(True)
        attention_layout.addWidget(self.status_title)
        attention_layout.addWidget(self.status_detail)
        attention_layout.addStretch(1)
        self.refresh_button = QPushButton("Refresh Dashboard")
        self.refresh_button.clicked.connect(self.refresh)
        attention_layout.addWidget(self.refresh_button)
        lower.addWidget(attention_card, 2)
        root.addLayout(lower, 1)

        self.empty_note = QLabel(
            "No local projects yet. Import a book to create your first audiobook project."
        )
        self.empty_note.setObjectName("muted")
        self.empty_note.setWordWrap(True)
        root.addWidget(self.empty_note)

        self.refresh()

    def _metric(self, label: str, value: str, detail: str) -> QWidget:
        card = QWidget()
        card.setObjectName("dashboardMetric")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        name = QLabel(label)
        name.setObjectName("dashboardMetricLabel")
        layout.addWidget(name)
        number = QLabel(value)
        number.setObjectName("dashboardMetricValue")
        number.setProperty("metricValue", True)
        layout.addWidget(number)
        caption = QLabel(detail)
        caption.setObjectName("muted")
        caption.setWordWrap(True)
        layout.addWidget(caption)
        card.metric_value = number
        return card

    @staticmethod
    def _project_sort_key(project: Project) -> float:
        try:
            return project.folder.stat().st_mtime
        except OSError:
            return 0.0

    def refresh(self) -> None:
        try:
            self.projects = sorted(list_projects(), key=self._project_sort_key, reverse=True)
        except Exception as exc:
            self.projects = []
            self.status_title.setText("Library could not be refreshed")
            self.status_detail.setText(f"Check the local library folder and retry. Details: {exc}")
            self.empty_note.setVisible(True)
            self.empty_note.setText("The dashboard could not read your local project list.")
            return

        statuses = [(project, project_status(project)[0]) for project in self.projects]
        completed = sum(status == "Completed" for _, status in statuses)
        active = sum(status == "In Progress" for _, status in statuses)
        attention = sum(status == "Needs Attention" for _, status in statuses)

        self.metric_total.metric_value.setText(str(len(self.projects)))
        self.metric_completed.metric_value.setText(str(completed))
        self.metric_active.metric_value.setText(str(active))
        self.metric_attention.metric_value.setText(str(attention))

        self.visible_projects = self.projects[:8]
        self.recent_list.blockSignals(True)
        self.recent_list.clear()
        for project in self.visible_projects:
            status, output = project_status(project)
            chapter_count = len(project.chapters)
            completed_chapters = load_state(project.folder).get("completed_chapters") or []
            detail = f"{chapter_count} chapter(s)"
            if completed_chapters:
                detail += f" · {len(completed_chapters)} generated"
            if output:
                detail += " · output available"
            label = f"{project.title}\n{status}  ·  {detail}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(project.folder))
            self.recent_list.addItem(item)
        self.recent_list.blockSignals(False)

        self.empty_note.setVisible(not self.projects)
        self.recent_list.setVisible(bool(self.projects))
        self.continue_button.setEnabled(bool(self.projects))
        if self.visible_projects:
            self.recent_list.setCurrentRow(0)
        else:
            self.status_title.setText("Your library is ready")
            self.status_detail.setText(
                "Import your first book to start a local project. Existing supported "
                "formats and production features remain available through the workflow."
            )

    def _show_selected(self, row: int) -> None:
        if not 0 <= row < len(self.visible_projects):
            return
        project = self.visible_projects[row]
        status, output = project_status(project)
        state = load_state(project.folder)
        failed = state.get("failed_chapters") or []
        completed = state.get("completed_chapters") or []
        self.status_title.setText(project.title)
        lines = [
            f"Status: {status}",
            f"Chapters: {len(project.chapters)}",
            f"Generated chapters recorded: {len(completed)}",
        ]
        if failed:
            lines.append(f"Failed chapters: {len(failed)}")
        if output:
            lines.append(f"Output: {output}")
        lines.append(f"Local project folder: {project.folder}")
        self.status_detail.setText("\n".join(lines))
        self.status_detail.setTextFormat(Qt.TextFormat.PlainText)

    def _continue_selected(self) -> None:
        row = self.recent_list.currentRow()
        if 0 <= row < len(self.visible_projects) and self.on_open_project:
            self.on_open_project(self.visible_projects[row])

    def _import(self) -> None:
        if self.on_import:
            self.on_import()

    def _open_library(self) -> None:
        if self.on_open_library:
            self.on_open_library()
