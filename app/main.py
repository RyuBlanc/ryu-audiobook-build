from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.core.paths import ensure_roots
from app.ui.workflow import ProjectWorkflow


APP_STYLE = """
QMainWindow, QWidget {
    background: #0b0b0d;
    color: #f5f5f7;
    font-size: 10pt;
}
QTabWidget::pane {
    border: 1px solid #29292e;
    background: #0f0f12;
    border-radius: 14px;
}
QTabBar {
    background: #0b0b0d;
}
QTabBar::tab {
    background: #151519;
    color: #a9a9b2;
    padding: 11px 18px;
    margin: 6px 3px 0 0;
    border: 1px solid #25252b;
    border-radius: 9px;
}
QTabBar::tab:hover {
    background: #1e1e23;
    color: #ffffff;
}
QTabBar::tab:selected {
    background: #7f1024;
    border: 1px solid #a51b35;
    color: #ffffff;
}
QGroupBox {
    background: #121216;
    border: 1px solid #28282e;
    border-radius: 14px;
    margin-top: 14px;
    padding: 16px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 7px;
    color: #e8e8ed;
}
QLineEdit, QTextEdit, QComboBox, QListWidget {
    background: #18181d;
    color: #f5f5f7;
    border: 1px solid #33333a;
    border-radius: 9px;
    padding: 9px 11px;
    selection-background-color: #8f1730;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus {
    border: 1px solid #b51e3d;
}
QComboBox QAbstractItemView {
    background: #18181d;
    color: #f5f5f7;
    selection-background-color: #8f1730;
    selection-color: #ffffff;
    border: 1px solid #3a3a42;
    padding: 5px;
}
QTextEdit {
    padding: 10px;
}
QPushButton {
    background: #24242a;
    color: #f5f5f7;
    border: 1px solid #3a3a42;
    border-radius: 9px;
    padding: 9px 15px;
    min-height: 20px;
}
QPushButton:hover {
    background: #313139;
    border-color: #555560;
}
QPushButton:pressed {
    background: #19191e;
}
QPushButton#primary {
    background: #a31734;
    border: 1px solid #c3284a;
    font-weight: 700;
    padding: 11px 20px;
}
QPushButton#primary:hover {
    background: #bd2040;
}
QPushButton:disabled {
    color: #66666e;
    background: #17171b;
}
QProgressBar {
    background: #1b1b20;
    border: 1px solid #303038;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background: #a31734;
    border-radius: 5px;
}
QCheckBox {
    spacing: 8px;
}
QLabel {
    color: #e7e7ec;
}
QLabel#muted {
    color: #9999a4;
}
QLabel#stat {
    background: #19191e;
    border: 1px solid #292930;
    border-radius: 8px;
    padding: 8px 10px;
    color: #c9c9d1;
}
QStatusBar {
    background: #08080a;
    color: #a8a8b0;
}
QScrollBar:vertical {
    background: #101014;
    width: 11px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #3a3a43;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #6d1a2e;
}
"""

def main() -> int:
    ensure_roots()
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = ProjectWorkflow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
