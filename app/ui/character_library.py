from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)
from PySide6.QtCore import QSettings

from app.core.character_library import (
    list_characters, list_deleted_characters, restore_character, soft_delete_character, update_character,
)
from app.tts.voice_profile import load_profiles
from app.ui.voice_page import VoicePreviewWorker


class CharacterLibraryPage(QWidget):
    """Live, locally persisted character identities grouped by shared story series."""

    _NAME_FIELDS = 6

    def __init__(self, on_open_in_studio=None, parent=None):
        super().__init__(parent)
        self.on_open_in_studio = on_open_in_studio
        self._show_recovery = False
        self._records: list[dict] = []
        self._row_inputs: dict[str, dict] = {}
        self._preview_worker: VoicePreviewWorker | None = None
        self._preview_profile_id = ""
        self._profiles = []
        self._pronunciation_map: dict[str, str] = {}

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.78)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(10)

        title = QLabel("Character Library")
        title.setObjectName("pageHeading")
        root.addWidget(title)
        subtitle = QLabel(
            "Reusable characters shared by series and volumes. Character Studio is the source "
            "for analyzed cast members and assigned voices; this view stores aliases, dialogue "
            "samples, and local recovery records."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search series, primary name, aliases, or voice…")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda *_args: self._search_timer.start())
        toolbar.addWidget(self.search, 1)

        self.list_button = QPushButton("List")
        self.list_button.setCheckable(True)
        self.list_button.setChecked(True)
        self.list_button.clicked.connect(lambda: self._set_view("list"))
        toolbar.addWidget(self.list_button)
        self.cards_button = QPushButton("Cards")
        self.cards_button.setCheckable(True)
        self.cards_button.clicked.connect(lambda: self._set_view("cards"))
        toolbar.addWidget(self.cards_button)
        self.recovery_button = QPushButton("Recovery Bin")
        self.recovery_button.setCheckable(True)
        self.recovery_button.clicked.connect(self._toggle_recovery)
        toolbar.addWidget(self.recovery_button)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)
        root.addLayout(toolbar)

        self.status = QLabel("Loading locally saved character records…")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.view_stack = QStackedWidget()
        root.addWidget(self.view_stack, 1)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName("characterLibraryTable")
        self.table.setHorizontalHeaderLabels([
            "Series", "Character names (primary + up to 5 aliases)", "Assigned voice",
            "Dialogue sample", "Pronunciation", "Voice preview", "Edit", "Delete / Recover",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 155)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 625)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 180)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 260)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 180)
        for column in (5, 6, 7):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.view_stack.addWidget(self.table)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_content = QWidget()
        self.cards_layout = QGridLayout(self.cards_content)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_scroll.setWidget(self.cards_content)
        self.view_stack.addWidget(self.cards_scroll)
        self.status.setText("Saved character records load when this screen opens.")

    def _set_view(self, mode: str) -> None:
        cards = mode == "cards"
        self.list_button.setChecked(not cards)
        self.cards_button.setChecked(cards)
        self.view_stack.setCurrentWidget(self.cards_scroll if cards else self.table)
        self.refresh()

    def _toggle_recovery(self, checked: bool) -> None:
        self._show_recovery = bool(checked)
        self.recovery_button.setText("Active Characters" if checked else "Recovery Bin")
        self.refresh()

    def _load_pronunciation_map(self) -> dict[str, str]:
        raw = QSettings("RyuBlanc", "Ryu's Audiobook").value("pronunciation/global_dictionary", "[]")
        try:
            entries = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            entries = []
        result = {}
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                written = str(item.get("written") or "").strip()
                spoken = str(item.get("spoken") or "").strip()
                if written and spoken and item.get("enabled", True) is not False:
                    result[written.casefold()] = spoken
        return result

    def _matches(self, record: dict) -> bool:
        query = self.search.text().strip().casefold()
        if not query:
            return True
        searchable = " ".join([
            str(record.get("series") or ""),
            str(record.get("primary_name") or ""),
            " ".join(str(value) for value in (record.get("aliases") or [])),
            str(record.get("voice_name") or ""),
            str(record.get("dialogue_sample") or ""),
            str(record.get("pronunciation") or ""),
        ]).casefold()
        return query in searchable

    def refresh(self, *_args) -> None:
        self._pronunciation_map = self._load_pronunciation_map()
        all_rows = list_characters(include_deleted=self._show_recovery)
        if self._show_recovery:
            all_rows = list_deleted_characters()
        self._records = [row for row in all_rows if self._matches(row)]
        self._row_inputs.clear()
        self.table.setRowCount(0)
        self._clear_cards()
        if self._records:
            for record in self._records:
                self._add_table_row(record)
                self._add_card(record)
            self.status.setText(
                f"{len(self._records)} {'deleted character record(s) ready to recover' if self._show_recovery else 'live character record(s)'} • stored on this PC."
            )
        else:
            self.status.setText(
                "No deleted character records to recover."
                if self._show_recovery
                else "No live character records yet. Analyze a book or add a character in Character Studio; the live cast will appear here."
            )
            if not self._show_recovery:
                self._add_empty_card()
        self.view_stack.setCurrentWidget(self.cards_scroll if self.cards_button.isChecked() else self.table)

    def _names_widget(self, record: dict, disabled: bool) -> tuple[QWidget, list[QLineEdit]]:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(4)
        aliases = list(record.get("aliases") or [])[:5]
        values = [str(record.get("primary_name") or ""), *aliases]
        values += [""] * (self._NAME_FIELDS - len(values))
        fields = []
        placeholders = ["Primary", "Alias 1", "Alias 2", "Alias 3", "Alias 4", "Alias 5"]
        for index, (value, placeholder) in enumerate(zip(values, placeholders)):
            field = QLineEdit(value)
            field.setPlaceholderText(placeholder)
            field.setMinimumWidth(90)
            field.setMaximumWidth(108)
            field.setClearButtonEnabled(index > 0)
            field.setEnabled(not disabled)
            if index == 0:
                field.setToolTip("Primary character name")
            else:
                field.setToolTip(f"Optional alias / nickname {index} (maximum five aliases)")
            row.addWidget(field)
            fields.append(field)
        row.addStretch(1)
        return host, fields

    def _add_table_row(self, record: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        deleted = self._show_recovery
        record_id = str(record.get("id") or "")
        series = QLineEdit(str(record.get("series") or ""))
        series.setPlaceholderText("Series / novel name")
        series.setMinimumWidth(130)
        series.setEnabled(not deleted)

        names_host, name_fields = self._names_widget(record, deleted)
        voice = QWidget()
        voice_layout = QVBoxLayout(voice)
        voice_layout.setContentsMargins(2, 2, 2, 2)
        voice_layout.setSpacing(3)
        voice_label = QLabel(str(record.get("voice_name") or "Not assigned"))
        voice_label.setWordWrap(True)
        voice_layout.addWidget(voice_label)
        studio_button = QPushButton("Change in Character Studio")
        studio_button.setToolTip("Open the matching series in Character Studio to change the assigned voice.")
        studio_button.setEnabled(not deleted)
        studio_button.clicked.connect(lambda _checked=False, item=dict(record): self.open_in_character_studio(item))
        voice_layout.addWidget(studio_button)
        sample = QLineEdit(str(record.get("dialogue_sample") or ""))
        sample.setPlaceholderText("A short character dialogue sample…")
        sample.setMinimumWidth(220)
        sample.setEnabled(not deleted)
        pronunciation = QLineEdit(
            str(record.get("pronunciation") or self._pronunciation_map.get(str(record.get("primary_name") or "").casefold(), ""))
        )
        pronunciation.setPlaceholderText("Optional spoken form")
        pronunciation.setEnabled(not deleted)

        preview = QPushButton("Preview")
        preview.setEnabled(not deleted and bool(record.get("voice_name")))
        preview.clicked.connect(lambda _checked=False, item=dict(record), s=sample: self.preview_voice(item, s.text()))
        save = QPushButton("Save")
        save.setEnabled(not deleted)
        save.clicked.connect(
            lambda _checked=False, rid=record_id, se=series, nf=name_fields, sm=sample, pr=pronunciation:
            self._save_row(rid, se.text(), [field.text() for field in nf], sm.text(), pr.text())
        )
        action = QPushButton("Recover" if deleted else "Delete")
        action.clicked.connect(
            lambda _checked=False, rid=record_id: self.recover_character(rid)
            if self._show_recovery else self.delete_character(rid)
        )

        widgets = [series, names_host, voice, sample, pronunciation, preview, save, action]
        for column, widget in enumerate(widgets):
            self.table.setCellWidget(row, column, widget)
        self.table.setRowHeight(row, 78)
        self._row_inputs[record_id] = {
            "series": series, "names": name_fields, "sample": sample,
            "pronunciation": pronunciation,
        }

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_card(self, record: dict) -> None:
        index = self.cards_layout.count()
        card = QFrame()
        card.setObjectName("characterLibraryCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setMinimumWidth(230)
        card.setMaximumWidth(360)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        primary = QLabel(str(record.get("primary_name") or "Unnamed character"))
        primary.setObjectName("sectionTitle")
        primary.setWordWrap(True)
        layout.addWidget(primary)
        voice = QLabel("Voice: " + str(record.get("voice_name") or "Not assigned"))
        voice.setWordWrap(True)
        layout.addWidget(voice)
        series = QLabel("Series: " + str(record.get("series") or "Unassigned series"))
        series.setWordWrap(True)
        layout.addWidget(series)
        pronunciation = str(record.get("pronunciation") or self._pronunciation_map.get(str(record.get("primary_name") or "").casefold(), ""))
        if pronunciation:
            pronounce = QLabel("Pronunciation: " + pronunciation)
            pronounce.setWordWrap(True)
            layout.addWidget(pronounce)
        if self._show_recovery:
            action = QPushButton("Recover")
            action.clicked.connect(lambda _checked=False, rid=str(record.get("id") or ""): self.recover_character(rid))
            layout.addWidget(action)
        else:
            actions = QHBoxLayout()
            preview = QPushButton("Preview voice")
            preview.setEnabled(bool(record.get("voice_name")))
            preview.clicked.connect(lambda _checked=False, item=dict(record): self.preview_voice(item, str(item.get("dialogue_sample") or "")))
            studio = QPushButton("Character Studio")
            studio.clicked.connect(lambda _checked=False, item=dict(record): self.open_in_character_studio(item))
            edit = QPushButton("Edit in List")
            edit.clicked.connect(lambda: self._set_view("list"))
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda _checked=False, rid=str(record.get("id") or ""): self.delete_character(rid))
            actions.addWidget(preview)
            actions.addWidget(studio)
            actions.addWidget(edit)
            actions.addWidget(delete)
            layout.addLayout(actions)
        self.cards_layout.addWidget(card, index // 3, index % 3)

    def _add_empty_card(self) -> None:
        note = QLabel("Characters appear here after they are analyzed or manually added in Character Studio.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        self.cards_layout.addWidget(note, 0, 0, 1, 3)

    def _save_row(self, record_id: str, series: str, names: list[str], sample: str, pronunciation: str) -> None:
        names = [str(value or "").strip() for value in names]
        primary = names[0] if names else ""
        aliases = []
        seen = {primary.casefold()} if primary else set()
        for value in names[1:]:
            if value and value.casefold() not in seen:
                aliases.append(value)
                seen.add(value.casefold())
            if len(aliases) >= 5:
                break
        try:
            updated = update_character(record_id, {
                "series": series,
                "primary_name": primary,
                "aliases": aliases,
                "dialogue_sample": sample,
                "pronunciation": pronunciation,
            })
            self._save_global_pronunciation(updated)
        except (KeyError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Character not saved", str(exc))
            return
        self.status.setText(f"Saved {updated['primary_name']} in the {updated['series']} series.")
        self.refresh()

    def _save_global_pronunciation(self, record: dict) -> None:
        written = str(record.get("primary_name") or "").strip()
        spoken = str(record.get("pronunciation") or "").strip()
        if not written or not spoken:
            return
        settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        raw = settings.value("pronunciation/global_dictionary", "[]")
        try:
            entries = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            entries = []
        if not isinstance(entries, list):
            entries = []
        updated = []
        found = False
        for item in entries:
            if not isinstance(item, dict):
                continue
            if str(item.get("written") or "").strip().casefold() == written.casefold():
                updated.append({**item, "written": written, "spoken": spoken, "enabled": True, "source": "character-library"})
                found = True
            else:
                updated.append(dict(item))
        if not found:
            updated.append({"written": written, "spoken": spoken, "enabled": True, "source": "character-library"})
        settings.setValue("pronunciation/global_dictionary", json.dumps(updated, ensure_ascii=False))
        settings.sync()

    def delete_character(self, record_id: str) -> None:
        answer = QMessageBox.question(
            self, "Delete Character",
            "Move this character to the recovery bin? Its aliases, voice assignment, dialogue sample, and pronunciation data will be retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            soft_delete_character(record_id)
        except (KeyError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Character not deleted", str(exc))
            return
        self.status.setText("Character moved to the recovery bin. Use Recovery Bin to restore it.")
        self.refresh()

    def recover_character(self, record_id: str) -> None:
        try:
            record = restore_character(record_id)
        except (KeyError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Character not recovered", str(exc))
            return
        self.status.setText(f"Recovered {record.get('primary_name') or 'character'}.")
        self.refresh()

    def preview_voice(self, record: dict, text: str) -> None:
        voice_name = str(record.get("voice_name") or "").strip()
        if not voice_name:
            self.status.setText("This character has no assigned voice. Assign one in Character Studio first.")
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self.status.setText("A voice preview is already being generated.")
            return
        profiles = load_profiles()
        profile = next((item for item in profiles if item.name == voice_name), None)
        if profile is None:
            self.status.setText(f"Voice profile '{voice_name}' was not found. Refresh voices in Character Studio.")
            return
        sample = str(text or record.get("dialogue_sample") or "").strip()
        if not sample:
            sample = "This is a short preview of the assigned character voice."
        output = Path(tempfile.gettempdir()) / f"ryu-character-preview-{record.get('id') or 'sample'}.wav"
        self._player.stop()
        self.status.setText(f"Generating a real voice preview with {voice_name}…")
        self._preview_worker = VoicePreviewWorker(profile, sample, output, target_seconds=10)
        self._preview_worker.status.connect(self.status.setText)
        self._preview_worker.finished_ok.connect(self._play_preview_file)
        self._preview_worker.failed.connect(lambda message: self.status.setText(f"Voice preview failed: {message}"))
        self._preview_worker.start()

    def _play_preview_file(self, output_path: str, _elapsed: float) -> None:
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(output_path))
        self._player.play()
        self.status.setText("Playing the generated voice preview.")

    def open_in_character_studio(self, record: dict) -> None:
        if self.on_open_in_studio:
            self.on_open_in_studio(dict(record))
        else:
            QMessageBox.information(
                self, "Character Studio",
                "Open a book in Character Studio and use the same series name to reuse this cast.",
            )

    def shutdown(self) -> None:
        self._player.stop()
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_worker.cancel_requested = True
            self._preview_worker.wait(1000)

