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
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open Selected Project")
        self.delete_button = QPushButton("Delete Selected Book")
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
        row = self.list.currentRow()
        projects = list_projects()
        if not (0 <= row < len(projects)):
            return
        project = projects[row]
        answer = QMessageBox.question(
            self,
            "Delete Book",
            f"Delete '{project.title}' from Ryu's Audiobook?\n\n"
            "This removes its imported source, chapters, generated audio, cover, "
            "settings and project data from the local Ryu's Audiobook library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_project(project)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Delete Book Failed", str(exc))
