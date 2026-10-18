from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt, QSettings
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
    background: #090A0F;
    color: #F5F5F6;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow {
    background: #090A0F;
}
QStackedWidget#studioStack {
    background: #090A0F;
    border: 0;
}
QLabel {
    color: #F5F5F6;
}
QLabel#brand {
    color: #F5F5F6;
    font-size: 15pt;
    letter-spacing: 1.4px;
}
QLabel#muted {
    color: #A5ACB8;
}
QLabel#projectTitle {
    color: #F5F5F6;
    font-size: 10pt;
    font-weight: 600;
}
QLabel#stat {
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 8px;
    padding: 8px 10px;
    color: #A5ACB8;
}
QTabWidget::pane {
    border: 1px solid #282E38;
    background: #0F131A;
    border-radius: 12px;
}
QTabBar {
    background: #0F131A;
}
QTabBar::tab {
    background: #141821;
    color: #A5ACB8;
    padding: 12px 16px;
    margin: 0 6px 5px 0;
    min-width: 100px;
    border: 1px solid #282E38;
    border-radius: 8px;
}
QTabBar::tab:hover {
    background: #211a25;
    color: #F5F5F6;
    border-color: #353C49;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #31121f, stop:1 #1b1723);
    border: 1px solid #6F1023;
    color: #ffffff;
}
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #141821, stop:1 #0F131A);
    border: 1px solid #282E38;
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
    background: #141821;
    color: #F5F5F6;
    border: 1px solid #282E38;
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: #B21F3F;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 1px solid #D4375D;
}
QComboBox QAbstractItemView {
    background: #141821;
    color: #F5F5F6;
    selection-background-color: #B21F3F;
    selection-color: #ffffff;
    border: 1px solid #473143;
    padding: 5px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #181D28, stop:1 #181D28);
    color: #F5F5F6;
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
    border: 1px solid #D4375D;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6F1023, stop:0.58 #B21F3F, stop:1 #B21F3F);
    border: 1px solid #df5369;
    color: #fff8fb;
    font-weight: 700;
    padding: 11px 20px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D4375D, stop:1 #D4375D);
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
    color: #F5F5F6;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #504354;
    background: #141821;
}
QCheckBox::indicator:checked {
    background: #B21F3F;
    border: 1px solid #D4375D;
}
QProgressBar {
    background: #0F131A;
    border: 1px solid #282E38;
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
    border: 1px solid #282E38;
    border-radius: 13px;
    padding: 8px 6px;
    outline: 0;
}
QListWidget#sidebar::item {
    background: transparent;
    color: #A5ACB8;
    border: 1px solid transparent;
    border-left: 2px solid transparent;
    border-radius: 7px;
    padding: 9px 8px;
    margin: 2px 1px;
}
QListWidget#sidebar::item:hover {
    background: #1b1822;
    color: #F5F5F6;
    border-color: #282E38;
}
QListWidget#sidebar::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #29121d, stop:0.8 #1b1722, stop:1 #17151d);
    color: #fff6f8;
    border: 1px solid #3e2531;
    border-left: 3px solid #D4375D;
}
QHeaderView::section {
    background: #19151e;
    color: #d8cbdc;
    border: 1px solid #282E38;
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
    border: 1px solid #6F1023;
    padding: 6px 8px;
}
QStatusBar {
    background: #090A0F;
    color: #A5ACB8;
    border-top: 1px solid #2c2632;
}

QLabel#brandEdition {
    color: #D6B06A;
    font-size: 9pt;
    font-weight: 600;
}
QWidget#studioSidebar {
    background: #0F131A;
    border-right: 1px solid #282E38;
}
QWidget#studioMainPanel {
    background: #090A0F;
}
QWidget#sidebarDivider {
    background: #282E38;
    max-height: 1px;
}
QFrame#importDropZone {
    background: #141821;
    border: 1px dashed #353C49;
    border-radius: 18px;
}
QFrame#importDropZone[dragging="true"] {
    background: #28121C;
    border: 2px solid #D4375D;
}
QLabel#dropTitle {
    color: #F5F5F6;
    font-size: 15pt;
    font-weight: 700;
}
QLabel#importDropIcon {
    color: #D6B06A;
    background: #28121C;
    border: 1px solid #6F1023;
    border-radius: 25px;
    font-size: 22pt;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
}
QLabel#formatTag {
    color: #D6B06A;
    background: #181D28;
    border: 1px solid #282E38;
    border-radius: 7px;
    padding: 5px 9px;
    font-size: 8pt;
    font-weight: 700;
}
QListWidget#libraryCollection {
    background: transparent;
    border: 0;
    padding: 4px;
}
QListWidget#libraryCollection::item {
    background: #141821;
    color: #F5F5F6;
    border: 1px solid #282E38;
    border-radius: 12px;
    padding: 10px;
    margin: 3px;
}
QListWidget#libraryCollection::item:selected {
    background: #28121C;
    border: 1px solid #D4375D;
}
QWidget#dashboardMetric {
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 14px;
}
QGroupBox#dashboardContinueCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #181D28, stop:1 #141821);
    border: 1px solid #353C49;
    border-radius: 18px;
    padding-top: 11px;
}
QLabel#dashboardHeroCover {
    color: #FFE3A8;
    background: qradialgradient(cx:0.65, cy:0.25, radius:0.95, fx:0.65, fy:0.25, stop:0 #D6B06A, stop:0.22 #51111E, stop:0.72 #25080F, stop:1 #090A0F);
    border: 1px solid #6F1023;
    border-radius: 14px;
    font-size: 10pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#dashboardMetricLabel {
    color: #D6B06A;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#dashboardMetricValue {
    color: #F5F5F6;
    font-size: 22pt;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #F5F5F6;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#pageHeading {
    color: #F5F5F6;
    font-size: 19pt;
    font-weight: 700;
}
QLabel#pageSubheading {
    color: #A5ACB8;
    font-size: 9pt;
}
QLabel#projectPill {
    color: #F5F5F6;
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 10px;
    padding: 8px 12px;
}
QLabel#projectMiniTitle {
    color: #F5F5F6;
    font-size: 10pt;
    font-weight: 600;
}
QWidget#currentProjectCard {
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 12px;
}
QLineEdit#globalSearch {
    min-height: 22px;
    border-radius: 10px;
    padding-left: 12px;
}
QListWidget#sidebar {
    background: transparent;
    border: 0;
    border-radius: 8px;
    padding: 2px;
    outline: 0;
}
QListWidget#sidebar::item {
    color: #A5ACB8;
    padding: 10px 8px;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 9px;
    margin: 1px 0;
}
QListWidget#sidebar::item:selected {
    color: #F5F5F6;
    background: #28121C;
    border: 1px solid #6F1023;
    border-left: 3px solid #D4375D;
}
QListWidget#sidebar::item:hover {
    background: #181D28;
    border-color: #282E38;
}
QFrame, QSplitter::handle {
    border-color: #282E38;
}
QToolButton {
    color: #F5F5F6;
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 10px;
    padding: 7px 10px;
}
QToolButton:hover {
    background: #181D28;
    border-color: #D4375D;
}
QWidget#workflowRail {
    background: #0F131A;
    border-bottom: 1px solid #282E38;
}
QWidget#miniPlayerBar {
    background: #0F131A;
    border-top: 1px solid #353C49;
}
QPushButton#libraryFilter {
    background: transparent;
    color: #A5ACB8;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 7px 13px;
    min-height: 20px;
    font-weight: 600;
}
QPushButton#libraryFilter:hover {
    background: #181D28;
    border-color: #353C49;
    color: #F5F5F6;
}
QPushButton#libraryFilter:checked {
    background: #31121F;
    color: #FFFFFF;
    border: 1px solid #B21F3F;
}
QPushButton#shellIconButton {
    background: #141821;
    color: #F5F5F6;
    border: 1px solid #353C49;
    border-radius: 10px;
    padding: 7px 10px;
    min-height: 22px;
    font-size: 12pt;
    font-weight: 700;
}
QPushButton#shellIconButton:hover {
    background: #1B1822;
    border-color: #B21F3F;
}
QPushButton#workflowStep {
    background: #141821;
    color: #A5ACB8;
    border: 1px solid #282E38;
    border-radius: 12px;
    padding: 6px 7px;
    min-height: 18px;
    font-size: 8pt;
    font-weight: 600;
}
QPushButton#workflowStep:hover {
    color: #F5F5F6;
    background: #1B1822;
    border-color: #684052;
}
QPushButton#workflowStep:checked {
    color: #FFFFFF;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #31121F, stop:1 #1B1723);
    border: 1px solid #B21F3F;
}
QPushButton#workflowStep:focus {
    border: 1px solid #D4375D;
}

/* Dragon Studio Stage 5: consistent, high-contrast control surfaces. */
QWidget#studioMainPanel, QStackedWidget#studioStack, QScrollArea,
QScrollArea > QWidget > QWidget {
    background: #090A0F;
    border: 0;
}
QFrame[card="true"], QWidget[card="true"], QGroupBox[card="true"] {
    background: #141821;
    border: 1px solid #282E38;
    border-radius: 14px;
}
QLabel#eyebrow, QLabel[role="eyebrow"] {
    color: #D6B06A;
    font-size: 8pt;
    font-weight: 700;
}
QLabel#muted, QLabel[role="muted"] {
    color: #A5ACB8;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit, QListWidget, QTableWidget, QTreeWidget {
    min-height: 22px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTimeEdit:hover {
    border-color: #353C49;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus,
QListWidget:focus, QTableWidget:focus, QTreeWidget:focus {
    border: 1px solid #D4375D;
}
QComboBox::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {
    border: 0;
    border-left: 1px solid #282E38;
    width: 26px;
}
QTableWidget, QTreeWidget {
    gridline-color: #282E38;
    alternate-background-color: #0F131A;
    selection-background-color: #31121F;
    selection-color: #F5F5F6;
}
QTableWidget::item, QTreeWidget::item {
    padding: 5px;
}
QMenu {
    background: #141821;
    color: #F5F5F6;
    border: 1px solid #353C49;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #28121C;
    color: #FFFFFF;
}
QToolButton:pressed, QCheckBox:pressed {
    background: #28121C;
}
QPushButton#primary:disabled {
    color: #A5ACB8;
    background: #282E38;
    border-color: #353C49;
}
QLabel#pageHeading {
    letter-spacing: -0.4px;
}
QLabel#pageSubheading {
    line-height: 1.35;
}
"""

def main() -> int:
    ensure_roots()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setProperty("_ryuDarkStylesheet", APP_STYLE)
    app.setStyleSheet(APP_STYLE)
    saved_theme = str(QSettings("RyuBlanc", "Ryu's Audiobook").value("ui/theme", "dark")).lower()
    from app.ui.settings_page import apply_application_theme
    # Apply the saved theme, accent and interface scale on every launch,
    # including dark mode. The preference helper reads the remaining values
    # from the same local QSettings store.
    apply_application_theme(app, saved_theme)
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
    app_icon = QIcon()
    # Prefer a lossless PNG if one is present; the branded SVG is the
    # packaged fallback so the executable never falls back to a generic icon.
    for icon_name in ("ryu_audiobook_logo.svg", "ryu_audiobook_logo.png", "ryu_audiobook_logo.jpg"):
        icon_path = asset_path(icon_name)
        if icon_path.is_file():
            candidate_icon = QIcon(str(icon_path))
            if not candidate_icon.isNull():
                app_icon = candidate_icon
                break
    app.setWindowIcon(app_icon)
    window = ProjectWorkflow()
    window.setWindowTitle(f"{APP_NAME} • {full_version()}")
    window.setWindowIcon(app_icon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
