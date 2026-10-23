from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QTextEdit, QVBoxLayout, QWidget, QStackedWidget, QGroupBox,
)

from app.core.character_library import (
    load_character_library, save_character_library, update_character,
    soft_delete_character, restore_character, upsert_characters_from_studio,
)
from app.tts.voice_profile import load_profiles


class CharacterEditDialog(QDialog):
    def __init__(self, row: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Character")
        self.resize(700, 420)
        self.row = row
        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)
        self.series = QLineEdit(row.get("series", ""))
        self.primary = QLineEdit(row.get("primary_name", ""))
        form.addRow("Series / Novel", self.series)
        form.addRow("Primary name", self.primary)
        self.aliases = [QLineEdit() for _ in range(5)]
        for i, control in enumerate(self.aliases, 1):
            control.setPlaceholderText(f"Optional alias / nickname / title {i}")
            aliases = row.get("aliases", [])
            if len(aliases) >= i:
                control.setText(str(aliases[i - 1]))
            form.addRow(f"Name {i}", control)
        self.sample = QTextEdit()
        self.sample.setPlainText(row.get("dialogue_sample", ""))
        self.sample.setPlaceholderText("Short dialogue/sample text for a real assigned-voice preview")
        form.addRow("Dialogue sample", self.sample)
        hint = QLabel(
            "Assigned voice is managed in Character Studio after selecting this series. "
            "This editor changes names and sample text only."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self):
        return {
            "series": self.series.text().strip(),
            "primary_name": self.primary.text().strip(),
            "aliases": [item.text().strip() for item in self.aliases if item.text().strip()][:5],
            "dialogue_sample": self.sample.toPlainText().strip(),
        }


class CharacterLibraryPage(QWidget):
    """Persistent cross-volume cast library. Only stored app data is displayed."""

    def __init__(self, open_character_studio=None, parent=None):
        super().__init__(parent)
        self.open_character_studio = open_character_studio
        self.rows: list[dict] = []
        self.profiles = load_profiles()

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(self._playback_error)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        root.addWidget(QLabel("<h1>Character Library</h1>"))
        intro = QLabel(
            "Reusable characters grouped by series. Entries come from saved Character Studio "
            "analysis or manual cast records; this library does not invent sample characters."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search character, alias, series or voice…")
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1)
        self.series_filter = QComboBox()
        self.series_filter.addItem("All series", "")
        self.series_filter.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.series_filter)
        self.view_mode = QComboBox()
        self.view_mode.addItems(["Cards", "List"])
        self.view_mode.currentIndexChanged.connect(self._set_view)
        top.addWidget(self.view_mode)
        self.studio_button = QPushButton("Open Character Studio")
        self.studio_button.setObjectName("primary")
        self.studio_button.clicked.connect(self._open_studio)
        top.addWidget(self.studio_button)
        root.addLayout(top)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.cards_page = QWidget()
        cards_layout = QVBoxLayout(self.cards_page)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.cards_body = QWidget()
        self.cards_grid = QVBoxLayout(self.cards_body)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(8)
        self.cards_scroll.setWidget(self.cards_body)
        cards_layout.addWidget(self.cards_scroll)
        self.stack.addWidget(self.cards_page)

        self.list_page = QWidget()
        list_layout = QVBoxLayout(self.list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.currentRowChanged.connect(self._show_selected_details)
        list_layout.addWidget(self.list, 1)
        self.details_box = QGroupBox("Selected character")
        detail_layout = QVBoxLayout(self.details_box)
        self.details = QLabel("Select a character to inspect details.")
        self.details.setWordWrap(True)
        detail_layout.addWidget(self.details)
        self.detail_sample = QTextEdit()
        self.detail_sample.setReadOnly(True)
        self.detail_sample.setMaximumHeight(90)
        detail_layout.addWidget(self.detail_sample)
        list_layout.addWidget(self.details_box)
        list_actions = QHBoxLayout()
        self.preview_button = QPushButton("▶ Preview Assigned Voice")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        self.restore_button = QPushButton("Restore")
        list_actions.addWidget(self.preview_button)
        list_actions.addWidget(self.edit_button)
        list_actions.addWidget(self.delete_button)
        list_actions.addWidget(self.restore_button)
        list_actions.addStretch(1)
        list_layout.addLayout(list_actions)
        self.stack.addWidget(self.list_page)
        self.preview_button.clicked.connect(self.preview_selected)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.refresh()

    def refresh(self):
        previous_id = self._selected_row_id() if hasattr(self, "list") else None
        self.rows = load_character_library()
        query = self.search.text().strip().casefold() if hasattr(self, "search") else ""
        selected_series = self.series_filter.currentData() if hasattr(self, "series_filter") else ""
        series_values = sorted({str(row.get("series") or "") for row in self.rows if not row.get("deleted") and row.get("series")}, key=str.casefold)
        current_series = selected_series
        self.series_filter.blockSignals(True)
        self.series_filter.clear()
        self.series_filter.addItem("All series", "")
        for series in series_values:
            self.series_filter.addItem(series, series)
        idx = self.series_filter.findData(current_series)
        self.series_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.series_filter.blockSignals(False)
        selected_series = self.series_filter.currentData() or ""

        self.visible_rows = [
            row for row in self.rows
            if (query in " ".join([
                str(row.get("primary_name", "")),
                " ".join(row.get("aliases", [])),
                str(row.get("series", "")),
                str(row.get("voice_name", "")),
            ]).casefold())
            and (not selected_series or row.get("series") == selected_series)
        ]
        self._render_cards()
        self._render_list(previous_id)
        live_count = sum(not row.get("deleted") for row in self.rows)
        deleted_count = sum(bool(row.get("deleted")) for row in self.rows)
        self.status.setText(
            f"{live_count} saved character(s) • {deleted_count} deleted/recoverable • "
            "Voice assignment is managed in Character Studio."
        )

    def _set_view(self, index):
        self.stack.setCurrentIndex(1 if self.view_mode.currentText() == "List" else 0)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_cards(self):
        self._clear_layout(self.cards_grid)
        visible = [row for row in self.visible_rows if not row.get("deleted")]
        if not visible:
            empty = QLabel("No saved characters found. Analyze a book or add a character in Character Studio.")
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            self.cards_grid.addWidget(empty)
            return
        for row in visible:
            card = QGroupBox()
            line = QHBoxLayout(card)
            names = QLabel(
                f"<b>{row.get('primary_name', '')}</b><br>"
                f"Voice: {row.get('voice_name') or 'Not assigned'}<br>"
                f"Series: {row.get('series') or 'Unassigned series'}"
            )
            names.setWordWrap(True)
            line.addWidget(names, 1)
            open_button = QPushButton("Open Series in Studio")
            open_button.clicked.connect(
                lambda checked=False, series=row.get("series", ""): self._open_studio(series)
            )
            line.addWidget(open_button)
            self.cards_grid.addWidget(card)
        self.cards_grid.addStretch(1)

    def _render_list(self, previous_id=None):
        self.list.blockSignals(True)
        self.list.clear()
        for row in self.visible_rows:
            aliases = row.get("aliases", [])
            list_item = QListWidgetItem(
                f"{row.get('series') or 'Unassigned series'}  →  "
                f"{row.get('primary_name', '')}"
                + (f"  ({' · '.join(aliases)})" if aliases else "")
                + f"  →  {row.get('voice_name') or 'Not assigned'}"
                + ("  ·  Deleted" if row.get("deleted") else "")
            )
            list_item.setData(32, row.get("id"))
            self.list.addItem(list_item)
        self.list.blockSignals(False)
        target = next((i for i, row in enumerate(self.visible_rows) if row.get("id") == previous_id), 0 if self.visible_rows else -1)
        if target >= 0:
            self.list.setCurrentRow(target)
        else:
            self._show_selected_details(-1)

    def _selected_row_id(self):
        row = getattr(self, "visible_rows", [])
        index = self.list.currentRow() if hasattr(self, "list") else -1
        return row[index].get("id") if 0 <= index < len(row) else None

    def _selected(self):
        index = self.list.currentRow()
        return self.visible_rows[index] if 0 <= index < len(self.visible_rows) else None

    def _show_selected_details(self, index):
        row = self._selected()
        if not row:
            self.details.setText("Select a character to inspect details.")
            self.detail_sample.clear()
            self.preview_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.restore_button.setEnabled(False)
            return
        aliases = row.get("aliases", [])
        self.details.setText(
            f"<b>Series:</b> {row.get('series') or 'Unassigned series'}<br>"
            f"<b>Primary:</b> {row.get('primary_name', '')}<br>"
            f"<b>Aliases:</b> {' · '.join(aliases) if aliases else 'None'}<br>"
            f"<b>Assigned voice:</b> {row.get('voice_name') or 'Not assigned'}<br>"
            f"<b>Status:</b> {'Deleted / recoverable' if row.get('deleted') else 'Active'}"
        )
        self.detail_sample.setPlainText(row.get("dialogue_sample", ""))
        self.preview_button.setEnabled(bool(row.get("voice_name") and row.get("dialogue_sample") and not row.get("deleted")))
        self.edit_button.setEnabled(not row.get("deleted"))
        self.delete_button.setEnabled(not row.get("deleted"))
        self.restore_button.setEnabled(bool(row.get("deleted")))

    def edit_selected(self):
        row = self._selected()
        if not row or row.get("deleted"):
            return
        dialog = CharacterEditDialog(row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updates = dialog.values()
        try:
            update_character(str(row["id"]), updates)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Edit Character Failed", str(exc))

    def delete_selected(self):
        row = self._selected()
        if not row or row.get("deleted"):
            return
        answer = QMessageBox.question(
            self, "Delete Character",
            f"Move '{row.get('primary_name')}' to recoverable deleted characters?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            soft_delete_character(str(row["id"]))
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Delete Character Failed", str(exc))

    def restore_selected(self):
        row = self._selected()
        if not row or not row.get("deleted"):
            return
        try:
            restore_character(str(row["id"]))
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Restore Character Failed", str(exc))

    def preview_selected(self):
        row = self._selected()
        if not row or not row.get("voice_name") or not row.get("dialogue_sample"):
            return
        profiles = {p.name: p for p in load_profiles()}
        profile = profiles.get(row["voice_name"])
        if not profile:
            QMessageBox.warning(
                self, "Voice Not Available",
                "The assigned profile is not currently available. Open Character Studio for this series and assign an installed voice profile.",
            )
            return
        try:
            from tempfile import gettempdir
            from uuid import uuid4
            from app.tts.profile_provider import provider_from_profile
            from app.tts.preview import build_voice_preview
            from threading import Thread

            output = Path(gettempdir()) / f"ryu-character-preview-{uuid4().hex}.wav"
            self.preview_button.setEnabled(False)

            def worker():
                provider = None
                try:
                    provider, voice = provider_from_profile(profile)
                    build_voice_preview(
                        row["dialogue_sample"],
                        provider,
                        voice,
                        output,
                        narration_speed=0.90,
                        pacing_profile="natural",
                        max_chars=max(1000, len(row["dialogue_sample"]) + 1),
                        target_seconds=10,
                    )
                    if output.exists():
                        self.player.setSource(QUrl.fromLocalFile(str(output)))
                        self.player.play()
                except Exception as exc:
                    self.status.setText(f"Voice preview failed: {exc}")
                finally:
                    close = getattr(provider, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
                    self.preview_button.setEnabled(True)

            Thread(target=worker, daemon=True).start()
        except Exception as exc:
            QMessageBox.critical(self, "Voice Preview Failed", str(exc))

    def _playback_error(self, *args):
        self.status.setText(f"Audio playback error: {self.player.errorString()}")

    def _open_studio(self, series=None):
        if self.open_character_studio:
            self.open_character_studio(str(series or ""))
            return
        QMessageBox.information(self, "Character Studio", "Open a book in the Library, then open Voice Cast / Character Studio to analyze or assign characters.")

