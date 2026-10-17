from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, QSize, Qt
from PySide6.QtGui import QDesktopServices, QIcon
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

    state = load_state(project.folder)
    parts = [project.title, project.source_path.name if project.source_path else ""]
    for key in ("author", "series", "narrator", "narrator_name", "voice_name", "selected_voice"):
        value = state.get(key)
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
    metadata = state.get("metadata")
    if isinstance(metadata, dict):
        for key in ("title", "author", "series", "narrator", "language"):
            value = metadata.get(key)
            if isinstance(value, (str, int, float)):
                parts.append(str(value))
    profiles = state.get("voice_profiles") or state.get("selected_profiles") or []
    if isinstance(profiles, (list, tuple)):
        parts.extend(str(value) for value in profiles if isinstance(value, (str, int, float)))
    searchable = " ".join(parts).casefold()
    normalized_filter = (status_filter or "All").strip().casefold()
    if normalized_filter == "active" and status not in {"In Progress", "Ready"}:
        return False
    if normalized_filter == "completed" and status != "Completed":
        return False
    if normalized_filter in {"attention", "needs attention", "failed"} and status != "Needs Attention":
        return False
    if normalized_filter not in {"", "all", "active", "completed", "attention", "needs attention", "failed"} and status != status_filter:
        return False
    return not query or query in searchable


class LibraryPage(QWidget):
    def __init__(self, on_open=None, on_import=None) -> None:
        super().__init__()
        self.on_open = on_open
        self.on_import = on_import
        self.projects = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        eyebrow = QLabel("YOUR LOCAL COLLECTION")
        eyebrow.setObjectName("brandEdition")
        title_col.addWidget(eyebrow)
        title = QLabel("Audiobook Library")
        title.setObjectName("pageHeading")
        title_col.addWidget(title)
        self.subtitle = QLabel("Manage imported books, production projects, and completed audiobooks.")
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        title_col.addWidget(self.subtitle)
        header.addLayout(title_col, 1)

        self.grid_button = QPushButton("Grid View")
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(True)
        self.grid_button.clicked.connect(lambda: self.set_view_mode("grid"))
        header.addWidget(self.grid_button)
        self.list_button = QPushButton("List View")
        self.list_button.setCheckable(True)
        self.list_button.clicked.connect(lambda: self.set_view_mode("list"))
        header.addWidget(self.list_button)
        self.import_button = QPushButton("Import Book")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._import_book)
        header.addWidget(self.import_button)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, author or narrator…")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Completed", "Attention"])
        self.status_filter.setVisible(False)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.filter_buttons: dict[str, QPushButton] = {}
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        for label in ("All", "Active", "Completed", "Attention"):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("libraryFilter")
            button.setChecked(label == "All")
            button.clicked.connect(lambda _checked=False, value=label: self._set_status_filter(value))
            self.filter_buttons[label] = button
            filter_row.addWidget(button)
        filters.addLayout(filter_row)
        layout.addLayout(filters)

        stats_box = QGroupBox("Collection Summary")
        stats = QHBoxLayout(stats_box)
        self.total_label = QLabel("Local projects  ·  0")
        self.completed_label = QLabel("Completed  ·  0")
        self.in_progress_label = QLabel("In progress  ·  0")
        self.attention_label = QLabel("Needs attention  ·  0")
        for label in (self.total_label, self.completed_label, self.in_progress_label, self.attention_label):
            label.setObjectName("stat")
            stats.addWidget(label)
        layout.addWidget(stats_box)

        body = QHBoxLayout()

        self.list = QListWidget()
        self.list.setObjectName("libraryCollection")
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWrapping(True)
        self.list.setUniformItemSizes(True)
        self.list.setIconSize(QSize(82, 104))
        self.list.setGridSize(QSize(178, 192))
        self.list.setSpacing(8)
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
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

    def _set_status_filter(self, value: str) -> None:
        index = self.status_filter.findText(value)
        if index >= 0 and self.status_filter.currentIndex() != index:
            self.status_filter.setCurrentIndex(index)
        for label, button in self.filter_buttons.items():
            button.setChecked(label == value)
        self.refresh()

    def refresh(self) -> None:
        query = self.search.text() if hasattr(self, "search") else ""
        status_filter = self.status_filter.currentText() if hasattr(self, "status_filter") else "All"
        for label, button in getattr(self, "filter_buttons", {}).items():
            button.blockSignals(True)
            button.setChecked(label == status_filter)
            button.blockSignals(False)

        self.projects = list_projects()
        visible = [
            project for project in self.projects
            if project_matches(project, query, status_filter)
        ]

        self.list.blockSignals(True)
        self.list.clear()
        self._visible_projects = visible
        for project in visible:
            status, _output = project_status(project)
            marker = {
                "Completed": "✓",
                "In Progress": "▶",
                "Needs Attention": "!",
                "Ready": "•",
                "Imported": "○",
            }.get(status, "•")
            item = QListWidgetItem(
                f"{project.title}\n{marker} {status}\n{len(project.chapters)} chapter(s)"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(project.folder))
            state = load_state(project.folder)
            cover_path = Path(str(state.get("cover_path") or "")).expanduser()
            if cover_path.is_file():
                item.setIcon(QIcon(str(cover_path)))
            else:
                brand_path = Path(__file__).resolve().parents[2] / "assets" / "ryu_audiobook_logo.svg"
                if brand_path.is_file():
                    item.setIcon(QIcon(str(brand_path)))
            item.setSizeHint(QSize(170, 188))
            item.setToolTip(f"{project.title}\n{status}\n{project.folder}")
            self.list.addItem(item)
        self.list.blockSignals(False)

        completed = sum(project_status(project)[0] == "Completed" for project in self.projects)
        in_progress = sum(project_status(project)[0] == "In Progress" for project in self.projects)
        attention = sum(project_status(project)[0] == "Needs Attention" for project in self.projects)
        self.total_label.setText(f"Local projects  ·  {len(self.projects)}")
        self.completed_label.setText(f"Completed  ·  {completed}")
        self.in_progress_label.setText(f"In progress  ·  {in_progress}")
        self.attention_label.setText(f"Needs attention  ·  {attention}")
        self.subtitle.setText(
            f"{len(visible)} book(s) shown • completed books remain available from the local library."
        )

        if visible:
            self.list.setCurrentRow(0)
        else:
            self.details.setText("No books match the current search/filter.")
        self.list.setViewMode(
            QListWidget.ViewMode.IconMode if self.grid_button.isChecked()
            else QListWidget.ViewMode.ListMode
        )

    def set_view_mode(self, mode: str) -> None:
        grid = str(mode).casefold() == "grid"
        self.grid_button.setChecked(grid)
        self.list_button.setChecked(not grid)
        self.list.setViewMode(
            QListWidget.ViewMode.IconMode if grid else QListWidget.ViewMode.ListMode
        )
        if grid:
            self.list.setIconSize(QSize(82, 104))
            self.list.setGridSize(QSize(178, 192))
        else:
            self.list.setIconSize(QSize(42, 54))
            self.list.setGridSize(QSize())

    def _import_book(self) -> None:
        if self.on_import:
            self.on_import()

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
