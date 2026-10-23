from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QMessageBox, QLineEdit, QComboBox, QGroupBox,
    QDialog, QDialogButtonBox,
)

from app.core.project import list_projects
from app.core.project_trash import (
    trash_project, list_trashed_projects, restore_project, purge_trashed_project,
)
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


class TrashDialog(QDialog):
    """Recover or permanently purge projects previously deleted from the Library."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deleted Books • Recovery")
        self.resize(680, 420)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Books moved here are hidden from your active Library. Restore returns the "
            "project, chapters, saved pronunciations and local generation work. "
            "Permanent deletion cannot be undone."
        ))
        self.entries = QListWidget()
        root.addWidget(self.entries, 1)
        actions = QHBoxLayout()
        self.restore_button = QPushButton("Restore Selected")
        self.purge_button = QPushButton("Delete Permanently")
        self.purge_button.setObjectName("danger")
        actions.addWidget(self.restore_button)
        actions.addWidget(self.purge_button)
        actions.addStretch(1)
        root.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.restore_button.clicked.connect(self.restore_selected)
        self.purge_button.clicked.connect(self.purge_selected)
        self.refresh()

    def refresh(self):
        self.rows = list_trashed_projects()
        self.entries.clear()
        for item in self.rows:
            label = f"{item.get('title', 'Untitled')}  ·  Deleted {item.get('deleted_at', 'unknown time')}"
            self.entries.addItem(QListWidgetItem(label))
        self.restore_button.setEnabled(bool(self.rows))
        self.purge_button.setEnabled(bool(self.rows))

    def _selected_entry(self):
        row = self.entries.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def restore_selected(self):
        item = self._selected_entry()
        if not item:
            return
        try:
            restored = restore_project(Path(item["project_folder"]).parent)
            QMessageBox.information(self, "Book Restored", f"Restored to:\\n{restored}")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))

    def purge_selected(self):
        item = self._selected_entry()
        if not item:
            return
        answer = QMessageBox.question(
            self,
            "Delete Permanently",
            f"Permanently delete '{item.get('title', 'Untitled')}' and its saved project data? "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            purge_trashed_project(Path(item["project_folder"]).parent)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Permanent Delete Failed", str(exc))


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
        self.trash_button = QPushButton("Deleted Books / Recover")
        header.addWidget(self.trash_button)
        layout.addLayout(header)
        self.trash_button.clicked.connect(self.open_trash)

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
        previous_folder = None
        if hasattr(self, "list") and self.list.currentRow() >= 0:
            selected_before = getattr(self, "_visible_projects", [])
            if self.list.currentRow() < len(selected_before):
                previous_folder = str(selected_before[self.list.currentRow()].folder)

        self.projects = list_projects()
        visible = [
            project for project in self.projects
            if project_matches(project, query, status_filter)
        ]

        self.list.blockSignals(True)
        self.list.clear()
        for project in visible:
            status, _ = project_status(project)
            marker = {
                "Completed": "✓", "In Progress": "▶", "Needs Attention": "⚠",
                "Ready": "●", "Imported": "○",
            }.get(status, "•")
            self.list.addItem(QListWidgetItem(
                f"{marker}  {project.title}  ·  {status}  ·  {len(project.chapters)} chapter(s)"
            ))
        self.list.blockSignals(False)
        self._visible_projects = visible

        completed = sum(project_status(project)[0] == "Completed" for project in self.projects)
        in_progress = sum(project_status(project)[0] == "In Progress" for project in self.projects)
        self.total_label.setText(f"Books: {len(self.projects)}")
        self.completed_label.setText(f"Completed: {completed}")
        self.in_progress_label.setText(f"In progress: {in_progress}")
        self.subtitle.setText(
            f"{len(visible)} book(s) shown • deletion moves books to recovery Trash; "
            "saved project data remains recoverable until permanently deleted."
        )

        selected_index = next(
            (i for i, project in enumerate(visible) if str(project.folder) == previous_folder),
            0 if visible else -1,
        )
        if selected_index >= 0:
            self.list.setCurrentRow(selected_index)
        else:
            self.details.setText("No books match the current search/filter.")

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
            f"<h3>{project.title}</h3>", f"<b>Status:</b> {status}",
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
        if selected:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(selected[0].folder)))

    def open_trash(self) -> None:
        dialog = TrashDialog(self)
        dialog.exec()
        self.refresh()

    def delete_selected(self) -> None:
        selected = self._selected_projects()
        if not selected:
            return
        names = "\\n".join(f"• {project.title}" for project in selected[:8])
        if len(selected) > 8:
            names += f"\\n• … and {len(selected) - 8} more"

        answer = QMessageBox.question(
            self,
            "Move Books to Recovery",
            f"Move {len(selected)} selected book(s) to Deleted Books?\\n\\n{names}\\n\\n"
            "Their source file copy, chapters, generated files and pronunciation settings "
            "will be retained in recovery Trash. Recent history records remain outside the project. "
            "Use Deleted Books / Recover to restore them or permanently delete them.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            for project in selected:
                trash_project(project)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Delete Books Failed", str(exc))
