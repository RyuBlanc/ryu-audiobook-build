from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QMessageBox, QLineEdit, QComboBox, QGroupBox,
)

from app.core.project import list_projects, delete_project
from app.core.state import load_state


def project_status(project) -> tuple[str, str]:
    state = load_state(project.folder)
    output_value = state.get("output_path")
    output = Path(output_value) if output_value else None
    status = str(state.get("status") or "new").lower()

    if status in {"failed", "cancelled"} or state.get("failed_chapters"):
        return "Needs Attention", str(output) if output and output.exists() else ""
    if status == "generating":
        return "In Progress", str(output) if output and output.exists() else ""
    if (
        status == "completed"
        and output
        and output.exists()
        and output.stat().st_size > 0
    ):
        return "Completed", str(output)
    if project.chapters:
        return "Ready", ""
    return "Imported", ""


def project_matches(project, query: str, status_filter: str) -> bool:
    query = (query or "").strip().casefold()
    status, _ = project_status(project)

    if status_filter and status_filter != "All" and status != status_filter:
        return False

    searchable = f"{project.title} {project.source_path.name if project.source_path else ''}".casefold()
    return not query or query in searchable


class LibraryPage(QWidget):
    def __init__(self, on_open=None) -> None:
        super().__init__()
        self.on_open = on_open
        self.projects = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(QLabel("<h1>My Audiobooks</h1>"))
        self.subtitle = QLabel("Your local audiobook projects, generated books and resumable work.")
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        title_col.addWidget(self.subtitle)
        header.addLayout(title_col, 1)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search books…")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "All", "Completed", "In Progress", "Needs Attention", "Ready", "Imported"
        ])
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.status_filter)
        layout.addLayout(filters)

        stats = QHBoxLayout()
        self.total_label = QLabel("Books: 0")
        self.completed_label = QLabel("Completed: 0")
        self.in_progress_label = QLabel("In progress: 0")
        stats.addWidget(self.total_label)
        stats.addWidget(self.completed_label)
        stats.addWidget(self.in_progress_label)
        stats.addStretch(1)
        layout.addLayout(stats)

        body = QHBoxLayout()

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.currentRowChanged.connect(self.show_selected_details)
        body.addWidget(self.list, 3)

        details_box = QGroupBox("Book Details")
        details_layout = QVBoxLayout(details_box)
        self.details = QLabel("Select a book to view its project status.")
        self.details.setWordWrap(True)
        details_layout.addWidget(self.details)
        details_layout.addStretch(1)
        body.addWidget(details_box, 2)
        layout.addLayout(body, 1)

        actions = QHBoxLayout()
        self.open_button = QPushButton("Open / Continue")
        self.open_button.setObjectName("primary")
        self.delete_button = QPushButton("Delete Selected Book(s)")
        self.delete_button.setObjectName("danger")
        self.folder_button = QPushButton("Open Book Folder")
        actions.addWidget(self.open_button)
        actions.addWidget(self.folder_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.open_button.clicked.connect(self.open_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.folder_button.clicked.connect(self.open_selected_folder)

        self.refresh()

    def refresh(self) -> None:
        query = self.search.text() if hasattr(self, "search") else ""
        status_filter = self.status_filter.currentText() if hasattr(self, "status_filter") else "All"

        self.projects = list_projects()
        visible = [
            project for project in self.projects
            if project_matches(project, query, status_filter)
        ]

        self.list.blockSignals(True)
        self.list.clear()
        for project in visible:
            status, output = project_status(project)
            marker = {
                "Completed": "✓",
                "In Progress": "▶",
                "Needs Attention": "⚠",
                "Ready": "●",
                "Imported": "○",
            }.get(status, "•")
            self.list.addItem(
                QListWidgetItem(
                    f"{marker}  {project.title}  ·  {status}  ·  "
                    f"{len(project.chapters)} chapter(s)"
                )
            )
        self.list.blockSignals(False)

        completed = sum(project_status(project)[0] == "Completed" for project in self.projects)
        in_progress = sum(project_status(project)[0] == "In Progress" for project in self.projects)
        self.total_label.setText(f"Books: {len(self.projects)}")
        self.completed_label.setText(f"Completed: {completed}")
        self.in_progress_label.setText(f"In progress: {in_progress}")
        self.subtitle.setText(
            f"{len(visible)} book(s) shown • completed books remain available from the local library."
        )

        if visible:
            self.list.setCurrentRow(0)
        else:
            self.details.setText("No books match the current search/filter.")
        self._visible_projects = visible

    def show_selected_details(self, row: int) -> None:
        visible = getattr(self, "_visible_projects", [])
        if not 0 <= row < len(visible):
            return

        project = visible[row]
        status, output = project_status(project)
        state = load_state(project.folder)
        failed = state.get("failed_chapters") or []
        completed_chapters = state.get("completed_chapters") or []

        details = [
            f"<h3>{project.title}</h3>",
            f"<b>Status:</b> {status}",
            f"<b>Chapters:</b> {len(project.chapters)}",
            f"<b>Completed chapters:</b> {len(completed_chapters)}",
        ]

        if project.source_path:
            details.append(f"<b>Source:</b> {project.source_path.name}")
        if output:
            details.append(f"<b>Audiobook:</b> {output}")
        if failed:
            details.append(f"<b>Failed chapters:</b> {', '.join(map(str, failed))}")
        details.append(f"<b>Project folder:</b> {project.folder}")

        self.details.setText("<br>".join(details))

    def _selected_projects(self):
        rows = sorted({index.row() for index in self.list.selectedIndexes()})
        if not rows:
            row = self.list.currentRow()
            if row >= 0:
                rows = [row]
        visible = getattr(self, "_visible_projects", [])
        return [visible[row] for row in rows if 0 <= row < len(visible)]

    def open_selected(self) -> None:
        selected = self._selected_projects()
        if selected and self.on_open:
            self.on_open(selected[0])

    def open_selected_folder(self) -> None:
        selected = self._selected_projects()
        if not selected:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(selected[0].folder)))

    def delete_selected(self) -> None:
        selected = self._selected_projects()
        if not selected:
            return

        names = "\n".join(f"• {project.title}" for project in selected[:8])
        if len(selected) > 8:
            names += f"\n• … and {len(selected) - 8} more"

        answer = QMessageBox.question(
            self,
            "Delete Books",
            f"Delete {len(selected)} selected book(s)?\n\n{names}\n\n"
            "This removes each imported source, chapters, generated audio, cover, "
            "settings and project data from the local Ryu's Audiobook library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            for project in selected:
                delete_project(project)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Delete Books Failed", str(exc))
