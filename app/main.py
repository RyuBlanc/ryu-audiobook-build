from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.core.paths import ensure_roots
from app.ui.workflow import ProjectWorkflow


APP_STYLE = """
QMainWindow, QWidget {
    background: #202124;
    color: #f1f3f4;
    font-size: 10pt;
}
QTabWidget::pane {
    border: 1px solid #3c4043;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: #292a2d;
    color: #c9cdd1;
    padding: 9px 16px;
    margin-right: 3px;
    border: 1px solid #3c4043;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}
QTabBar::tab:selected {
    background: #35363a;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #3c4043;
    border-radius: 9px;
    margin-top: 10px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
}
QLineEdit, QTextEdit, QComboBox, QListWidget {
    background: #292a2d;
    color: #f1f3f4;
    border: 1px solid #4a4d51;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #5b4b8a;
}
QTextEdit {
    padding: 9px;
}
QPushButton {
    background: #34363a;
    color: #f1f3f4;
    border: 1px solid #4a4d51;
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 18px;
}
QPushButton:hover {
    background: #414348;
}
QPushButton:pressed {
    background: #2b2d30;
}
QPushButton:disabled {
    color: #777b80;
    background: #292a2d;
}
QCheckBox {
    spacing: 8px;
}
QLabel {
    color: #e5e7eb;
}
QStatusBar {
    background: #1b1c1e;
}
QScrollBar:vertical {
    background: #242528;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #4a4d51;
    border-radius: 5px;
    min-height: 25px;
}
"""

def main() -> int:
    # The Library tab reads the local project directory during startup.
    ensure_roots()

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = ProjectWorkflow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
