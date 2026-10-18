from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from app.core.paths import app_root, audio_library_root, library_root, models_root, voices_root
from app.version import full_version


_LIGHT_COLOURS = {
    "#090A0F": "#F4EFE7",
    "#0F131A": "#FFFAF2",
    "#141821": "#FFFFFF",
    "#181D28": "#F8F1E8",
    "#1B1822": "#F4E9E1",
    "#11121A": "#FFFAF2",
    "#101016": "#F4EFE7",
    "#141018": "#FFFAF2",
    "#282E38": "#DED3C5",
    "#353C49": "#CABDAD",
    "#F5F5F6": "#231B1D",
    "#A5ACB8": "#6C6264",
    "#727B8B": "#8B7D80",
    "#D6B06A": "#966A24",
    "#EFE6F0": "#35282D",
    "#706977": "#8B7D80",
    "#14131A": "#FFFFFF",
    "#24212B": "#DED3C5",
    "#504354": "#CABDAD",
    "#F7EDF4": "#231B1D",
    "#84142E": "#8B1832",
    "#C51E4C": "#B21F3F",
    "#EE6849": "#D4375D",
    "#9045B1": "#8B4C86",
    "#1B1722": "#F8F1E8",
    "#19151E": "#F8F1E8",
    "#D8CBDC": "#35282D",
    "#101014": "#F4EFE7",
    "#3A3442": "#CABDAD",
    "#A92B4C": "#B21F3F",
    "#17131D": "#FFFAF2",
    "#FFF4FA": "#231B1D",
    "#2C2632": "#DED3C5",
    "#6F1023": "#8B1732",
    "#31121F": "#F1DDE3",
    "#1B1723": "#F8F1E8",
    "#473143": "#CABDAD",
    "#2B2431": "#F8E5E7",
    "#684052": "#D7A2B0",
    "#27151D": "#F8E5E7",
    "#743047": "#D7A2B0",
    "#F0B4C2": "#8B1732",
    "#3A1925": "#F1DDE3",
    "#B63C5A": "#B21F3F",
    "#28121C": "#F8E5E7",
    "#FFF6F8": "#231B1D",
    "#3E2531": "#E1C6CE",
    "#DF5369": "#D4375D",
    "#F06B77": "#B21F3F",
    "#6F1023": "#8B1732",
}


def apply_application_theme(app, theme: str, accent: str | None = None, scale: int | None = None) -> None:
    """Apply theme, crimson-family accent and accessible interface scaling."""
    settings = QSettings("RyuBlanc", "Ryu's Audiobook")
    accent = str(accent or settings.value("ui/accent", "crimson")).casefold()
    try:
        scale = max(80, min(150, int(scale if scale is not None else settings.value("ui/interface_scale", 100))))
    except (TypeError, ValueError):
        scale = 100

    base = app.property("_ryuDarkStylesheet")
    if not isinstance(base, str) or not base:
        base = app.styleSheet()
        app.setProperty("_ryuDarkStylesheet", base)

    style = base
    if accent == "velvet":
        for original, replacement in (
            ("#B21F3F", "#8B1732"),
            ("#D4375D", "#B21F3F"),
            ("#6F1023", "#5C1025"),
            ("#84142E", "#6E142A"),
            ("#C51E4C", "#9C1A3A"),
            ("#A92B4C", "#8B1732"),
        ):
            style = style.replace(original, replacement)

    if scale != 100:
        factor = scale / 100.0
        scalable = re.compile(
            r"((?:font-size|min-height|min-width|max-height|max-width|padding(?:-[\w-]+)?|"
            r"margin(?:-[\w-]+)?|spacing|border-radius)\s*:\s*)([^;]+)",
            re.IGNORECASE,
        )

        def scale_declaration(match):
            def scale_px(number):
                value = float(number.group(1))
                scaled = 0 if value == 0 else max(1, round(value * factor))
                return f"{scaled}px"
            return match.group(1) + re.sub(r"(\d+(?:\.\d+)?)px", scale_px, match.group(2))

        style = scalable.sub(scale_declaration, style)

    if str(theme).lower() == "light":
        style = re.sub(
            r"#[0-9A-Fa-f]{6}",
            lambda match: _LIGHT_COLOURS.get(match.group(0).upper(), match.group(0)),
            style,
        )
    app.setStyleSheet(style)


class SettingsPage(QWidget):
    """Settings for the local desktop app, without introducing cloud storage."""

    def __init__(self, on_saved=None) -> None:
        super().__init__()
        self.on_saved = on_saved
        self.settings = QSettings("RyuBlanc", "Ryu's Audiobook")

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        eyebrow = QLabel("YOUR STUDIO PREFERENCES")
        eyebrow.setObjectName("brandEdition")
        title_col.addWidget(eyebrow)
        title = QLabel("Settings")
        title.setObjectName("pageHeading")
        title_col.addWidget(title)
        subtitle = QLabel("Appearance, local storage, and diagnostics for this Windows installation.")
        subtitle.setObjectName("pageSubheading")
        subtitle.setWordWrap(True)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        self.save_button = QPushButton("Save Settings")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_settings)
        header.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        appearance = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance)
        self.theme = QComboBox()
        self.theme.addItem("Dark · Obsidian", "dark")
        self.theme.addItem("Light · Cream", "light")
        stored_theme = str(self.settings.value("ui/theme", "dark")).lower()
        self.theme.setCurrentIndex(max(0, self.theme.findData(stored_theme)))
        appearance_layout.addRow("Application theme", self.theme)
        self.accent = QComboBox()
        self.accent.addItem("Dragon Crimson", "crimson")
        self.accent.addItem("Velvet Red", "velvet")
        stored_accent = str(self.settings.value("ui/accent", "crimson")).lower()
        self.accent.setCurrentIndex(max(0, self.accent.findData(stored_accent)))
        appearance_layout.addRow("Accent", self.accent)
        self.interface_scale = QComboBox()
        for scale in (100, 110, 125):
            self.interface_scale.addItem(f"{scale}%", scale)
        stored_scale = int(self.settings.value("ui/interface_scale", 100) or 100)
        self.interface_scale.setCurrentIndex(max(0, self.interface_scale.findData(stored_scale)))
        appearance_layout.addRow("Interface scale", self.interface_scale)
        self.reduce_motion = QCheckBox("Reduce page and waveform motion")
        self.reduce_motion.setChecked(self.settings.value("ui/reduce_motion", False, type=bool))
        appearance_layout.addRow("Motion", self.reduce_motion)
        root.addWidget(appearance)

        output = QGroupBox("Default output")
        output_layout = QFormLayout(output)
        self.default_bitrate = QComboBox()
        for kbps in (128, 160, 192, 224, 256, 288, 320):
            self.default_bitrate.addItem(f"M4B · AAC · {kbps} kbps", kbps)
        stored_bitrate = int(self.settings.value("audio/default_bitrate", 256) or 256)
        self.default_bitrate.setCurrentIndex(max(0, self.default_bitrate.findData(stored_bitrate)))
        output_layout.addRow("Default audiobook quality", self.default_bitrate)
        output_note = QLabel("A book's saved bitrate overrides this default. M4B is the supported export container.")
        output_note.setObjectName("muted")
        output_note.setWordWrap(True)
        output_layout.addRow("", output_note)
        root.addWidget(output)

        storage = QGroupBox("Local storage")
        storage_layout = QVBoxLayout(storage)
        note = QLabel("Books, voice profiles, models, audio and logs remain on this PC. No cloud storage is used by these settings.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        storage_layout.addWidget(note)
        for label, folder in (
            ("Open Application Data", app_root()),
            ("Open Audiobook Library", library_root()),
            ("Open Voice Profiles", voices_root()),
            ("Open Audio Library", audio_library_root()),
            ("Open Models Folder", models_root()),
            ("Open Logs Folder", app_root() / "Logs"),
        ):
            row = QHBoxLayout()
            detail = QLabel(label)
            detail.setMinimumWidth(200)
            path_label = QLabel(str(folder))
            path_label.setObjectName("muted")
            path_label.setWordWrap(True)
            button = QPushButton("Open Folder")
            button.clicked.connect(lambda _checked=False, target=folder: self.open_folder(target))
            row.addWidget(detail)
            row.addWidget(path_label, 1)
            row.addWidget(button)
            storage_layout.addLayout(row)
        root.addWidget(storage)

        diagnostics = QGroupBox("Diagnostics")
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_hint = QLabel("If a page fails to open, the application log can help identify the exact error. Opening logs does not delete or upload anything.")
        diagnostics_hint.setObjectName("muted")
        diagnostics_hint.setWordWrap(True)
        diagnostics_layout.addWidget(diagnostics_hint)
        diagnostics_actions = QHBoxLayout()
        self.open_log_button = QPushButton("Open application.log")
        self.open_log_button.clicked.connect(self.open_application_log)
        diagnostics_actions.addWidget(self.open_log_button)
        diagnostics_actions.addStretch(1)
        diagnostics_layout.addLayout(diagnostics_actions)
        root.addWidget(diagnostics)

        about = QGroupBox("About Ryu's Audiobook")
        about_layout = QVBoxLayout(about)
        self.version_label = QLabel(f"Dragon Studio Edition · {full_version()}")
        self.version_label.setObjectName("sectionTitle")
        about_layout.addWidget(self.version_label)
        about_note = QLabel("Local-first desktop audiobook creation, with real project status and no fabricated generation metrics.")
        about_note.setObjectName("muted")
        about_note.setWordWrap(True)
        about_layout.addWidget(about_note)
        root.addWidget(about)
        self.status = QLabel("Preferences are stored in this Windows user profile.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self) -> None:
        stored_theme = str(self.settings.value("ui/theme", "dark")).lower()
        self.theme.setCurrentIndex(max(0, self.theme.findData(stored_theme)))
        self.reduce_motion.setChecked(self.settings.value("ui/reduce_motion", False, type=bool))
        self.accent.setCurrentIndex(max(0, self.accent.findData(str(self.settings.value("ui/accent", "crimson")).lower())))
        self.interface_scale.setCurrentIndex(max(0, self.interface_scale.findData(int(self.settings.value("ui/interface_scale", 100) or 100))))
        self.default_bitrate.setCurrentIndex(max(0, self.default_bitrate.findData(int(self.settings.value("audio/default_bitrate", 256) or 256))))

    def save_settings(self) -> None:
        theme = str(self.theme.currentData() or "dark")
        self.settings.setValue("ui/theme", theme)
        self.settings.setValue("ui/accent", str(self.accent.currentData() or "crimson"))
        self.settings.setValue("ui/interface_scale", int(self.interface_scale.currentData() or 100))
        self.settings.setValue("audio/default_bitrate", int(self.default_bitrate.currentData() or 256))
        self.settings.setValue("ui/reduce_motion", self.reduce_motion.isChecked())
        self.settings.sync()
        app = QApplication.instance()
        if app is not None:
            apply_application_theme(app, theme)
        if self.on_saved:
            try:
                self.on_saved(self.reduce_motion.isChecked())
            except Exception as exc:
                self.status.setText(f"Settings saved, but one live preference could not refresh: {exc}")
                return
        self.status.setText(
            "Settings saved locally. Theme, accent and interface scale preferences are recorded; "
            "default bitrate is used for new books unless a book already has its own saved quality."
        )

    @staticmethod
    def open_folder(folder: Path) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except OSError as exc:
            QMessageBox.warning(None, "Folder unavailable", f"Could not open {folder}:\n{exc}")

    def open_application_log(self) -> None:
        path = app_root() / "Logs" / "application.log"
        if not path.is_file():
            QMessageBox.information(self, "No log yet", "There is no application.log yet. The app creates it when a UI failure is recorded.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
