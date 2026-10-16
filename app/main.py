from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QIcon, QPixmap
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
QMainWindow {
    background: #08090e;
}
QStackedWidget#studioStack {
    background: #090a10;
    border: 0;
}
QLabel {
    color: #e9e4ee;
}
QLabel#brand {
    color: #fff7fb;
    font-size: 15pt;
    letter-spacing: 1.4px;
}
QLabel#muted {
    color: #a29baa;
}
QLabel#projectTitle {
    color: #efe8f2;
    font-size: 10pt;
    font-weight: 600;
}
QLabel#stat {
    background: #14131b;
    border: 1px solid #2d2735;
    border-radius: 8px;
    padding: 8px 10px;
    color: #d3cad9;
}
QTabWidget::pane {
    border: 1px solid #302b38;
    background: #101017;
    border-radius: 12px;
}
QTabBar {
    background: #0b0c12;
}
QTabBar::tab {
    background: #15151d;
    color: #aaa3b3;
    padding: 12px 16px;
    margin: 0 6px 5px 0;
    min-width: 100px;
    border: 1px solid #292632;
    border-radius: 8px;
}
QTabBar::tab:hover {
    background: #211a25;
    color: #fff7fb;
    border-color: #493044;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #31121f, stop:1 #1b1723);
    border: 1px solid #6c2942;
    color: #ffffff;
}
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #13131b, stop:1 #101017);
    border: 1px solid #302b38;
    border-radius: 13px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 7px;
    color: #efe6f0;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QListWidget, QTableWidget {
    background: #15151d;
    color: #f3eef6;
    border: 1px solid #302d3a;
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: #81223f;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 1px solid #df425f;
}
QComboBox QAbstractItemView {
    background: #15151d;
    color: #f3eef6;
    selection-background-color: #81223f;
    selection-color: #ffffff;
    border: 1px solid #473143;
    padding: 5px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22212b, stop:1 #191923);
    color: #f3eef6;
    border: 1px solid #383342;
    border-radius: 8px;
    padding: 9px 14px;
    min-height: 20px;
}
QPushButton:hover {
    background: #2b2431;
    border-color: #684052;
}
QPushButton:pressed {
    background: #15131b;
}
QPushButton:focus {
    border: 1px solid #cf3d5a;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #95142f, stop:0.58 #bd2345, stop:1 #d54a47);
    border: 1px solid #df5369;
    color: #fff8fb;
    font-weight: 700;
    padding: 11px 20px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91f43, stop:1 #e35b52);
    border-color: #f06b77;
}
QPushButton#danger {
    background: #27151d;
    border: 1px solid #743047;
    color: #f0b4c2;
}
QPushButton#danger:hover {
    background: #3a1925;
    border-color: #b63c5a;
}
QPushButton:disabled {
    color: #706977;
    background: #14131a;
    border-color: #24212b;
}
QCheckBox {
    spacing: 8px;
    color: #e9e3ed;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #504354;
    background: #14131b;
}
QCheckBox::indicator:checked {
    background: #c82a50;
    border: 1px solid #e5526c;
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
QHeaderView::section {
    background: #19151e;
    color: #d8cbdc;
    border: 1px solid #342938;
    padding: 7px 9px;
}
QScrollBar:vertical {
    background: #101014;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #3a3442;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #a92b4c;
}
QScrollBar:horizontal {
    background: #101014;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #3a3442;
    border-radius: 5px;
    min-width: 30px;
}
QToolTip {
    background: #17131d;
    color: #fff4fa;
    border: 1px solid #8c2947;
    padding: 6px 8px;
}
QStatusBar {
    background: #08080b;
    color: #aaa2b0;
    border-top: 1px solid #2c2632;
}
"""

def main() -> int:
    ensure_roots()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLE)
    # Small transparent four-winged crimson dragon cursor. The hotspot is
    # placed at the nose so clicking and text selection remain predictable.
    dragon_cursor_path = asset_path("dragon_cursor.png")
    if dragon_cursor_path.is_file():
        cursor_pixmap = QPixmap(str(dragon_cursor_path))
        if not cursor_pixmap.isNull():
            cursor_pixmap = cursor_pixmap.scaled(
                30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            app.setOverrideCursor(QCursor(cursor_pixmap, 21, 13))
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
