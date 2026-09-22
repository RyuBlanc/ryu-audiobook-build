from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from .core.paths import APP_NAME
from .hardware.detect import detect_hardware, recommended_mode


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 600)

        info = detect_hardware()
        gpu = info.gpu_name or "No NVIDIA GPU detected"
        mode = recommended_mode(info)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Ryu's Audiobook"))
        layout.addWidget(QLabel("Local audiobook generator — foundation build"))
        layout.addWidget(QLabel(f"GPU: {gpu}"))
        layout.addWidget(QLabel(f"Recommended processing mode: {mode}"))
        layout.addWidget(QLabel("Next: book import → chapter editor → voice preview → M4B generation"))
        self.setCentralWidget(central)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
