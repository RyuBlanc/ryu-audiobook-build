from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QMessageBox

from app.core.project import list_projects, delete_project

class LibraryPage(QWidget):
    def __init__(self, on_open=None) -> None:
        super().__init__()
        self.on_open = on_open
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("My Audiobooks"))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open Selected Project")
        self.delete_button = QPushButton("Delete Selected Book(s)")
        self.delete_button.setObjectName("danger")
        actions.addWidget(self.open_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        layout.addWidget(self.list)
        layout.addLayout(actions)
        self.open_button.clicked.connect(self.open_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for project in list_projects():
            self.list.addItem(project.title)

    def open_selected(self) -> None:
        row = self.list.currentRow()
        projects = list_projects()
        if 0 <= row < len(projects) and self.on_open:
            self.on_open(projects[row])


    def delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.list.selectedIndexes()})
        if not rows:
            row = self.list.currentRow()
            if row >= 0:
                rows = [row]
        projects = list_projects()
        selected = [projects[row] for row in rows if 0 <= row < len(projects)]
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
