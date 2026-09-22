from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from app.core.project import list_projects

class LibraryPage(QWidget):
    def __init__(self, on_open=None) -> None:
        super().__init__()
        self.on_open = on_open
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("My Audiobooks"))
        self.list = QListWidget()
        self.open_button = QPushButton("Open Selected Project")
        layout.addWidget(self.list)
        layout.addWidget(self.open_button)
        self.open_button.clicked.connect(self.open_selected)
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
