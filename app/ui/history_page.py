from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from app.core.project import Project, list_projects
from app.core.state import load_state


def _output_for(project: Project, state: dict) -> Path | None:
    raw = str(state.get("output_path") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project.folder / path
    try:
        return path if path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None


def _status_for(project: Project, state: dict) -> str:
    status = str(state.get("status") or "new").strip().lower()
    output = _output_for(project, state)
    if status in {"failed", "cancelled"} or state.get("failed_chapters"):
        return "Needs attention"
    if status in {"generating", "running", "queued"}:
        return "In progress"
    if status == "completed" and output:
        return "Completed"
    return "Ready" if project.chapters else "Imported"


class HistoryPage(QWidget):
    """Generation overview derived from each real project's persisted state."""

    def __init__(self, on_open_project=None, on_open_generation=None) -> None:
        super().__init__()
        self.on_open_project = on_open_project
        self.on_open_generation = on_open_generation
        self._projects_by_folder: dict[str, Project] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        eyebrow = QLabel("LOCAL JOB RECORDS")
        eyebrow.setObjectName("brandEdition")
        title_col.addWidget(eyebrow)
        title = QLabel("Generation History")
        title.setObjectName("pageHeading")
        title_col.addWidget(title)
        subtitle = QLabel("Review the real status of local projects, completed output, and chapters needing attention.")
        subtitle.setObjectName("pageSubheading")
        subtitle.setWordWrap(True)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        self.refresh_button = QPushButton("Refresh History")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        self.summary = QLabel("Reading local project status…")
        self.summary.setObjectName("stat")
        root.addWidget(self.summary)

        table_box = QGroupBox("Projects and production status")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Audiobook", "Status", "Chapters done", "Needs review", "Last updated", "Output"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(300)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.table, 1)
        root.addWidget(table_box, 1)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Open Project")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self._open_project)
        self.production_button = QPushButton("Open in Production Studio")
        self.production_button.clicked.connect(self._open_generation)
        self.output_button = QPushButton("Open Output Folder")
        self.output_button.clicked.connect(self._open_output_folder)
        self.open_button.setEnabled(False)
        self.production_button.setEnabled(False)
        self.output_button.setEnabled(False)
        actions.addWidget(self.open_button)
        actions.addWidget(self.production_button)
        actions.addWidget(self.output_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QLabel("History is reconstructed from local state files; no synthetic job entries are shown.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.refresh()

    def _selected_project(self) -> Project | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        folder = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        return self._projects_by_folder.get(folder)

    def _selection_changed(self) -> None:
        project = self._selected_project()
        enabled = project is not None
        self.open_button.setEnabled(enabled)
        self.production_button.setEnabled(enabled)
        self.output_button.setEnabled(enabled and _output_for(project, load_state(project.folder)) is not None)

    def refresh(self) -> None:
        previous = self._selected_project()
        previous_folder = str(previous.folder) if previous else ""
        projects = sorted(
            list_projects(),
            key=lambda project: project.folder.stat().st_mtime if project.folder.exists() else 0,
            reverse=True,
        )
        self._projects_by_folder = {str(project.folder): project for project in projects}
        self.table.setRowCount(0)
        counts = {"Completed": 0, "In progress": 0, "Needs attention": 0, "Ready": 0, "Imported": 0}
        for project in projects:
            state = load_state(project.folder)
            status = _status_for(project, state)
            count_key = {
                "Completed": "Completed",
                "In progress": "In progress",
                "Needs attention": "Needs attention",
                "Ready": "Ready",
                "Imported": "Imported",
            }.get(status, "Ready")
            counts[count_key] = counts.get(count_key, 0) + 1
            output = _output_for(project, state)
            done = len(state.get("completed_chapters") or [])
            failed = len(state.get("failed_chapters") or [])
            stamp_path = project.folder / "state.json"
            if not stamp_path.exists():
                stamp_path = project.project_file
            try:
                stamp = datetime.fromtimestamp(stamp_path.stat().st_mtime).strftime("%d %b %Y, %H:%M")
            except OSError:
                stamp = "—"
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                project.title,
                status,
                f"{done} / {len(project.chapters)}",
                str(failed),
                stamp,
                output.name if output else "No output",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(project.folder))
                if column == 1:
                    if status == "Completed":
                        item.setForeground(QColor("#33C76F"))
                    elif status == "Needs attention":
                        item.setForeground(QColor("#F4B740"))
                    elif status == "In progress":
                        item.setForeground(QColor("#4898FF"))
                    else:
                        item.setForeground(QColor("#A5ACB8"))
                self.table.setItem(row, column, item)
            if str(project.folder) == previous_folder:
                self.table.selectRow(row)
        self.summary.setText(
            f"{len(projects)} local projects · {counts['Completed']} completed · "
            f"{counts['In progress']} in progress · {counts['Needs attention']} need attention"
        )
        if projects and self.table.currentRow() < 0:
            self.table.selectRow(0)
        if not projects:
            self.status.setText("No local project history is available yet. Import a book to begin a project.")
        self._selection_changed()

    def _open_project(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Select a project", "Choose a project row first.")
            return
        if self.on_open_project:
            self.on_open_project(project)

    def _open_generation(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Select a project", "Choose a project row first.")
            return
        if self.on_open_project:
            self.on_open_project(project)
        if self.on_open_generation:
            self.on_open_generation()

    def _open_output_folder(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        output = _output_for(project, load_state(project.folder))
        if output is None:
            QMessageBox.information(self, "No output yet", "This project does not have a verified output file yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.parent)))
