from __future__ import annotations

from PySide6.QtWidgets import QLabel, QComboBox, QVBoxLayout, QWidget

from app.hardware.backend import detect_hardware

class HardwarePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hardware & Acceleration"))
        profile = detect_hardware()
        layout.addWidget(QLabel(f"CPU: {profile.cpu}"))
        layout.addWidget(QLabel(f"Architecture: {profile.architecture}"))

        self.mode = QComboBox()
        self.mode.addItem("Automatic", "auto")
        for backend in profile.backends:
            if backend.available:
                label = backend.name
                if backend.memory_mb:
                    label += f" — {backend.memory_mb} MB"
                self.mode.addItem(label, backend.name)
        self.mode.addItem("CPU Only", "CPU")
        self.mode.setCurrentIndex(max(0, self.mode.findData("auto")))
        layout.addWidget(QLabel(f"Recommended backend: {profile.recommended}"))
        layout.addWidget(self.mode)
