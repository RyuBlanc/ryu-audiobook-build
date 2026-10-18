from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QScrollArea,
    QWidget,
)
from PySide6.QtGui import QDesktopServices

from app.core.paths import app_root
from app.core.project import Project, list_projects
from app.core.state import load_state


_AUDIO_EXTENSIONS = {".m4b", ".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg"}


def _stored_output(project: Project, state: dict) -> Path | None:
    """Return only a real, non-empty generated audio file for this local project."""
    raw = str(state.get("output_path") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidate = Path(raw).expanduser()
        candidates.append(candidate if candidate.is_absolute() else project.folder / candidate)
        if not candidate.is_absolute():
            candidates.append(app_root() / candidate)
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.suffix.lower() in _AUDIO_EXTENSIONS and candidate.stat().st_size > 0:
                return candidate.resolve()
        except OSError:
            continue

    # Compatibility fallback for projects from builds that did not persist output_path.
    # Avoid scanning the working directory so chapter intermediates and previews do not
    # appear as finished audiobooks in this library.
    search_dirs = [
        project.folder,
        project.folder / "output",
        project.folder / "outputs",
        project.folder / "Audiobooks",
    ]
    found: list[Path] = []
    for folder in search_dirs:
        if not folder.is_dir():
            continue
        try:
            for path in folder.iterdir():
                if (
                    path.is_file()
                    and path.suffix.lower() in _AUDIO_EXTENSIONS
                    and path.stat().st_size > 0
                    and "preview" not in path.stem.casefold()
                    and "temp" not in path.stem.casefold()
                ):
                    found.append(path)
        except OSError:
            continue
    if not found:
        return None
    found.sort(key=lambda path: (path.suffix.lower() == ".m4b", path.stat().st_mtime), reverse=True)
    try:
        return found[0].resolve()
    except OSError:
        return found[0]


def _time_text(milliseconds: int) -> str:
    seconds = max(0, int(milliseconds // 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


class AudiobooksPage(QWidget):
    """A local-only, in-app player for verified audiobook output files."""

    def __init__(self, on_open_project=None) -> None:
        super().__init__()
        self.on_open_project = on_open_project
        self._projects_by_folder: dict[str, Project] = {}
        self._active_path: Path | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("audiobooksScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        eyebrow = QLabel("YOUR FINISHED AUDIO")
        eyebrow.setObjectName("brandEdition")
        title_col.addWidget(eyebrow)
        title = QLabel("Audiobooks")
        title.setObjectName("pageHeading")
        title_col.addWidget(title)
        subtitle = QLabel("Listen to generated files stored on this device. Nothing is uploaded.")
        subtitle.setObjectName("pageSubheading")
        subtitle.setWordWrap(True)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        self.refresh_button = QPushButton("Refresh Library")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        self.summary = QLabel("Searching local project outputs…")
        self.summary.setObjectName("stat")
        root.addWidget(self.summary)

        body = QHBoxLayout()
        body.setSpacing(14)

        library_box = QGroupBox("Finished local audiobooks")
        library_layout = QVBoxLayout(library_box)
        self.items = QListWidget()
        self.items.setObjectName("libraryCollection")
        self.items.setMinimumWidth(270)
        self.items.setSpacing(5)
        self.items.currentItemChanged.connect(self._selection_changed)
        library_layout.addWidget(self.items, 1)
        self.open_project_button = QPushButton("Open Book Project")
        self.open_project_button.clicked.connect(self._open_project)
        library_layout.addWidget(self.open_project_button)
        body.addWidget(library_box, 3)

        player_box = QGroupBox("In-App Player")
        player_layout = QVBoxLayout(player_box)
        self.now_playing = QLabel("Select a finished audiobook to begin.")
        self.now_playing.setObjectName("sectionTitle")
        self.now_playing.setWordWrap(True)
        player_layout.addWidget(self.now_playing)

        self.file_detail = QLabel("Audio stays in its original local output folder.")
        self.file_detail.setObjectName("muted")
        self.file_detail.setWordWrap(True)
        player_layout.addWidget(self.file_detail)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.player.errorOccurred.connect(self._playback_error)

        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderMoved.connect(self.player.setPosition)
        player_layout.addWidget(self.timeline)

        time_row = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.position_label.setObjectName("muted")
        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("muted")
        time_row.addWidget(self.position_label)
        time_row.addStretch(1)
        time_row.addWidget(self.duration_label)
        player_layout.addLayout(time_row)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶  Play")
        self.play_button.setObjectName("primary")
        self.play_button.clicked.connect(self.play_selected)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_resume)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.clicked.connect(self.stop_playback)
        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        player_layout.addLayout(controls)

        volume_row = QHBoxLayout()
        volume_label = QLabel("Volume")
        volume_label.setObjectName("muted")
        volume_row.addWidget(volume_label)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.valueChanged.connect(lambda value: self.audio_output.setVolume(value / 100.0))
        volume_row.addWidget(self.volume, 1)
        player_layout.addLayout(volume_row)

        self.open_output_button = QPushButton("Open Output Folder")
        self.open_output_button.clicked.connect(self._open_output_folder)
        player_layout.addWidget(self.open_output_button)
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        player_layout.addWidget(self.status)
        player_layout.addStretch(1)
        body.addWidget(player_box, 4)

        root.addLayout(body, 1)
        self.refresh()

    def _selected_item(self) -> QListWidgetItem | None:
        return self.items.currentItem()

    def _selected_path(self) -> Path | None:
        item = self._selected_item()
        if item is None:
            return None
        raw = str(item.data(Qt.ItemDataRole.UserRole) or "")
        path = Path(raw) if raw else None
        return path if path and path.is_file() else None

    def _selection_changed(self, current, _previous=None) -> None:
        path = self._selected_path()
        item = self._selected_item()
        if not path or item is None:
            self.now_playing.setText("Select a finished audiobook to begin.")
            self.file_detail.setText("No verified output file is selected.")
            return
        self.now_playing.setText(str(item.data(Qt.ItemDataRole.UserRole + 2) or item.text().splitlines()[0]))
        self.file_detail.setText(f"{path.name}\n{path.parent}\n{path.stat().st_size / (1024 * 1024):.1f} MB")
        self.status.setText("Selected. Press Play to listen inside Ryu's Audiobook.")
        folder = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
        self.open_project_button.setEnabled(folder in self._projects_by_folder)
        self.open_output_button.setEnabled(True)

    def refresh(self) -> None:
        selected = str(self._active_path or "")
        self.items.clear()
        self._projects_by_folder = {}
        found = 0
        projects = list_projects()
        for project in projects:
            self._projects_by_folder[str(project.folder)] = project
            state = load_state(project.folder)
            path = _stored_output(project, state)
            if path is None:
                continue
            item = QListWidgetItem(f"{project.title}\n{path.name}  ·  {path.stat().st_size / (1024 * 1024):.1f} MB")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setData(Qt.ItemDataRole.UserRole + 1, str(project.folder))
            item.setData(Qt.ItemDataRole.UserRole + 2, project.title)
            item.setToolTip(str(path))
            self.items.addItem(item)
            found += 1
            if str(path) == selected:
                self.items.setCurrentItem(item)
        self.summary.setText(
            f"{found} local audiobook output{'s' if found != 1 else ''} found · "
            f"{len(projects)} local project{'s' if len(projects) != 1 else ''} scanned"
        )
        if found == 0:
            self.now_playing.setText("No finished audiobook outputs found yet.")
            self.file_detail.setText("When a valid audio output is created, it will appear here. Open Production Studio to generate a book.")
            self.status.setText("This list is based on files that actually exist on disk; it does not invent completed projects.")
            self.open_project_button.setEnabled(False)
            self.open_output_button.setEnabled(False)
        else:
            self.items.setCurrentRow(self.items.currentRow() if self.items.currentRow() >= 0 else 0)

    def play_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            self.status.setText("Select an existing audiobook output first.")
            return
        try:
            if self.player.source().toLocalFile() != str(path):
                self.player.setSource(QUrl.fromLocalFile(str(path)))
            self._active_path = path
            self.player.play()
            self.status.setText(f"Opening local audio: {path.name}")
        except Exception as exc:
            self.status.setText(f"Could not play {path.name}: {type(exc).__name__}: {exc}")

    def pause_resume(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.status.setText("Playback paused.")
            return
        if self.player.source().isEmpty():
            self.play_selected()
        else:
            self.player.play()
            self.status.setText("Playback resumed.")

    def stop_playback(self) -> None:
        self.player.stop()
        self.player.setPosition(0)
        self.status.setText("Playback stopped.")

    def _playback_state_changed(self, state) -> None:
        self.pause_button.setText(
            "Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Resume"
        )

    def _position_changed(self, position: int) -> None:
        self.timeline.blockSignals(True)
        self.timeline.setValue(position)
        self.timeline.blockSignals(False)
        self.position_label.setText(_time_text(position))

    def _duration_changed(self, duration: int) -> None:
        self.timeline.setRange(0, max(0, duration))
        self.duration_label.setText(_time_text(duration))

    def _playback_error(self, _error, error_text: str) -> None:
        if error_text:
            self.status.setText(
                "The local media backend could not play this file. "
                "Try a Windows-supported audio format. Details: " + str(error_text)
            )

    def _open_project(self) -> None:
        item = self._selected_item()
        if item is None or self.on_open_project is None:
            return
        folder = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
        project = self._projects_by_folder.get(folder)
        if project is not None:
            self.on_open_project(project)

    def _open_output_folder(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
