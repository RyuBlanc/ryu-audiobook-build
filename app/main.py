from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.paths import ensure_roots
from app.version import APP_NAME, full_version
from app.ui.workflow import ProjectWorkflow


def asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / name


APP_STYLE = """
QMainWindow, QWidget {
    background: #090a10;
    color: #f1edf5;
    font-family: "Segoe UI";
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
QLabel#brand {
    color: #fff7fb;
    font-size: 15pt;
    letter-spacing: 1.4px;
}
QLabel#muted {
    color: #8f8f99;
}
QTabBar::tab {
    background: #151519;
    color: #a9a9b2;
    padding: 14px 18px;
    margin: 0 8px 6px 0;
    min-width: 118px;
    text-align: left;
    border: 1px solid #25252b;
    border-radius: 9px;
}
QTabBar::tab:hover {
    background: #1e1e23;
    color: #ffffff;
}
QTabWidget::pane {
    border: 0;
    background: #0f0f12;
}
QTabBar {
    background: #0d0d10;
    padding: 10px 8px 10px 8px;
}
QTabBar::tab:selected {
    background: #7f1024;
    border: 1px solid #a51b35;
    color: #ffffff;
}
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #13131b, stop:1 #101017);
    border: 1px solid #302b38;
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #95142f, stop:0.58 #bd2345, stop:1 #d54a47);
    border: 1px solid #df5369;
    font-weight: 700;
    padding: 11px 20px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91f43, stop:1 #e35b52);
}
QPushButton:disabled {
    color: #66666e;
    background: #17171b;
}
QProgressBar {
    background: #17171d;
    border: 1px solid #2f3038;
    border-radius: 7px;
    height: 14px;
    padding: 1px;
    text-align: center;
    color: #f5f5f7;
    font-weight: 600;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7f142d, stop:0.40 #cf234f, stop:0.72 #f06b4c, stop:1 #9d3fa3);
    border-radius: 6px;
    margin: 1px;
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
    background: #a92b4c;
}
QListWidget#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0.85, y2:1, stop:0 #11121a, stop:0.55 #101016, stop:1 #141018);
    border: 1px solid #2c2935;
    border-radius: 13px;
    padding: 8px 6px;
    outline: 0;
}
QListWidget#sidebar::item {
    background: transparent;
    color: #b7b1bf;
    border: 1px solid transparent;
    border-left: 2px solid transparent;
    border-radius: 7px;
    padding: 9px 8px;
    margin: 2px 1px;
}
QListWidget#sidebar::item:hover {
    background: #1b1822;
    color: #fff7fb;
    border-color: #302535;
}
QListWidget#sidebar::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #29121d, stop:0.8 #1b1722, stop:1 #17151d);
    color: #fff6f8;
    border: 1px solid #3e2531;
    border-left: 3px solid #ec4b68;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus {
    border: 1px solid #df425f;
}
QPushButton:focus {
    border: 1px solid #cf3d5a;
}
QProgressBar {
    background: #101017;
    border: 1px solid #302938;
    border-radius: 6px;
    height: 14px;
    padding: 1px;
    text-align: center;
    color: #f7edf4;
    font-weight: 600;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #84142e, stop:0.38 #c51e4c, stop:0.72 #ee6849, stop:1 #9045b1);
    border-radius: 5px;
    margin: 1px;
}
QToolTip {
    background: #17131d;
    color: #fff4fa;
    border: 1px solid #8c2947;
    padding: 6px 8px;
}
QLabel#muted {
    color: #a29baa;
}
QStatusBar {
    border-top: 1px solid #2c2632;
}
"""

def main() -> int:
    ensure_roots()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLE)
    icon_path = asset_path("ryu_audiobook_logo.png")
    app_icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    app.setWindowIcon(app_icon)
    window = ProjectWorkflow()
    window.setWindowTitle(f"{APP_NAME} • {full_version()}")
    window.setWindowIcon(app_icon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
