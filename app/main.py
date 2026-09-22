from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget
from .core.paths import APP_NAME
from .hardware.detect import detect_hardware, recommended_mode
from .ui.import_page import ImportPage
from .ui.voice_page import VoicePage

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 750)
        info = detect_hardware()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Ryu's Audiobook"))
        layout.addWidget(QLabel(f"Detected GPU: {info.gpu_name or 'No NVIDIA GPU detected'}"))
        layout.addWidget(QLabel(f"Initial processing mode: {recommended_mode(info)}"))
        tabs = QTabWidget()
        tabs.addTab(ImportPage(), "Book Import")
        tabs.addTab(VoicePage(), "Voice")
        layout.addWidget(tabs)
        self.setCentralWidget(central)

def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
