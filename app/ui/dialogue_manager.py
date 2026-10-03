from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.chapters.assignment_utils import (
    assignment_speakers,
    build_book_character_registry,
    format_character_registry_entry,
    normalize_assignment,
)
from app.chapters.dialogue import dialogue_segment_for_selection
from app.chapters.characters import _all_dialogue_spans


class DialogueAssignmentManagerDialog(QDialog):
    """Persistent book/chapter dialogue assignment workspace.

    Unlike the modal single-dialogue chooser, this page stays open while the
    user walks through every dialogue cue. Assigned rows are clearly marked,
    speakers can be selected together, and new characters can be added without
    closing the workspace.
    """

    def __init__(self, chapters, project_folder=None, on_save=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dialogue Assignment Manager")
        self.resize(1150, 720)
        self.chapters = list(chapters or [])
        self.project_folder = project_folder
        self.on_save = on_save
        self.registry = build_book_character_registry(self.chapters, project_folder)
        self.current_dialogues: list[tuple[int, int, str]] = []
        self.current_segment = None

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>Dialogue Assignment Manager</h2>"))
        header.addStretch(1)
        header.addWidget(QLabel("Select → check speaker(s) → Assign"))
        root.addLayout(header)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Chapter"))
        self.chapter_combo = QComboBox()
        for chapter in self.chapters:
            self.chapter_combo.addItem(
                f"{chapter.number}. {chapter.title}",
                int(chapter.number),
            )
        self.chapter_combo.currentIndexChanged.connect(self._load_chapter)
        controls.addWidget(self.chapter_combo, 2)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search dialogue…")
        self.search.textChanged.connect(self._filter_rows)
        controls.addWidget(self.search, 2)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        left_layout.addWidget(self.summary)

        self.dialogue_list = QListWidget()
        self.dialogue_list.currentRowChanged.connect(self._show_dialogue)
        self.dialogue_list.itemDoubleClicked.connect(self._quick_assign_selected)
        left_layout.addWidget(self.dialogue_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.preview = QLabel("Select a dialogue.")
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(100)
        self.preview.setStyleSheet("padding:10px;")
        right_layout.addWidget(self.preview)

        self.suggestion = QLabel()
        self.suggestion.setWordWrap(True)
        right_layout.addWidget(self.suggestion)

        right_layout.addWidget(QLabel("<b>Book characters</b>"))
        self.character_list = QListWidget()
        self.character_list.itemDoubleClicked.connect(self._assign_double_clicked_character)
        right_layout.addWidget(self.character_list, 1)

        char_actions = QHBoxLayout()
        add = QPushButton("＋ Add Character")
        add.setObjectName("primary")
        add.clicked.connect(self._add_character)
        char_actions.addWidget(add)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_character_checks)
        char_actions.addWidget(clear)
        right_layout.addLayout(char_actions)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Same-line multi-speaker mode"))
        self.mode = QComboBox()
        self.mode.addItem("Simultaneous / voice blend", "chorus")
        self.mode.addItem("Sequential / repeat line", "sequential")
        mode_row.addWidget(self.mode, 1)
        right_layout.addLayout(mode_row)

        action_row = QHBoxLayout()
        self.assign_button = QPushButton("Assign Checked")
        self.assign_button.setObjectName("primary")
        self.assign_button.clicked.connect(self._assign_checked)
        action_row.addWidget(self.assign_button, 1)
        self.unassign_button = QPushButton("Unassign Dialogue")
        self.unassign_button.clicked.connect(self._unassign)
        action_row.addWidget(self.unassign_button)
        right_layout.addLayout(action_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_character_list()
        if self.chapters:
            self._load_chapter(0)

    def _chapter(self):
        index = self.chapter_combo.currentIndex()
        if 0 <= index < len(self.chapters):
            return self.chapters[index]
        return None

    def _refresh_character_list(self):
        checked_before = {
            str(self.character_list.item(row).data(Qt.ItemDataRole.UserRole)).casefold()
            for row in range(self.character_list.count())
            if self.character_list.item(row).checkState() == Qt.CheckState.Checked
            and self.character_list.item(row).data(Qt.ItemDataRole.UserRole)
        }
        self.character_list.blockSignals(True)
        self.character_list.clear()
        for key, entry in self.registry.items():
            item = QListWidgetItem(format_character_registry_entry(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if key in checked_before else Qt.CheckState.Unchecked
            )
            self.character_list.addItem(item)
        self.character_list.blockSignals(False)

    def _load_chapter(self, _index=0):
        chapter = self._chapter()
        self.current_dialogues = []
        self.current_segment = None
        self.dialogue_list.clear()
        if not chapter:
            self.summary.setText("No chapter selected.")
            return

        for start, end, raw in _all_dialogue_spans(chapter.text or ""):
            self.current_dialogues.append((start, end, raw))

        self.summary.setText(
            f"Chapter {chapter.number}: {len(self.current_dialogues)} dialogue cue(s). "
            "Assigned cues are marked ✓; double-click a dialogue row to assign the top saved suggestion immediately."
        )
        self._filter_rows()
        if self.dialogue_list.count():
            self.dialogue_list.setCurrentRow(0)

    def _filter_rows(self):
        chapter = self._chapter()
        if not chapter:
            return
        query = self.search.text().strip().casefold()
        self.dialogue_list.blockSignals(True)
        self.dialogue_list.clear()

        for index, (start, end, raw) in enumerate(self.current_dialogues):
            clean = " ".join(str(raw).split())
            if query and query not in clean.casefold():
                continue

            assigned = []
            for assignment in getattr(chapter, "dialogue_assignments", []) or []:
                if int(assignment.get("start", -1)) == start and int(assignment.get("end", -1)) == end:
                    assigned = assignment_speakers(assignment)
                    break

            prefix = "✓" if assigned else "○"
            speakers = ", ".join(assigned) if assigned else "Unassigned"
            display = f"{prefix}  {index + 1}. {clean[:150]}"
            if len(clean) > 150:
                display += "…"
            display += f"   [{speakers}]"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, index)
            if assigned:
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(f"Assigned to: {speakers}")
            else:
                item.setToolTip("Not assigned yet.")
            self.dialogue_list.addItem(item)

        self.dialogue_list.blockSignals(False)

    def _selected_source_span(self):
        item = self.dialogue_list.currentItem()
        if not item:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not (0 <= index < len(self.current_dialogues)):
            return None
        return self.current_dialogues[index]

    def _show_dialogue(self, _row):
        chapter = self._chapter()
        selected = self._selected_source_span()
        if not chapter or not selected:
            self.preview.setText("Select a dialogue.")
            self.suggestion.clear()
            return

        start, end, raw = selected
        self.preview.setText(f"<b>Dialogue</b><br>{str(raw).strip()}")
        self._clear_character_checks()
        self.current_segment = dialogue_segment_for_selection(chapter, start, end)

        if self.current_segment and self.current_segment.suggestions:
            top = self.current_segment.suggestions[0]
            self.suggestion.setText(
                f"Quick suggestion: <b>{top[0]}</b> · {top[1]:.0%}<br>{top[2]}"
            )
        else:
            self.suggestion.setText(
                "No high-confidence local suggestion. Choose one or more saved book characters."
            )

        assigned = []
        for assignment in getattr(chapter, "dialogue_assignments", []) or []:
            if int(assignment.get("start", -1)) == start and int(assignment.get("end", -1)) == end:
                assigned = assignment_speakers(assignment)
                mode = str(assignment.get("multi_speaker_mode") or "chorus")
                index = self.mode.findData(mode)
                if index >= 0:
                    self.mode.setCurrentIndex(index)
                break

        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            name = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if any(name.casefold() == speaker.casefold() for speaker in assigned):
                item.setCheckState(Qt.CheckState.Checked)

    def _clear_character_checks(self):
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            item.setCheckState(Qt.CheckState.Unchecked)

    def _checked_names(self):
        names = []
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                name = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if name:
                    names.append(name)
        return list(dict.fromkeys(names))

    def _add_character(self):
        options = ["＋ Create brand-new character…"] + [
            entry["name"] for entry in self.registry.values()
        ]
        if len(options) > 1:
            choice, ok = QInputDialog.getItem(
                self,
                "Add Character",
                "Reuse a character already saved anywhere in this book, or create a new one:",
                options,
                0,
                False,
            )
            if not ok:
                return
            if choice != options[0]:
                self._check_character(choice)
                return

        name, ok = QInputDialog.getText(self, "Create Character", "New character name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        existing = self.registry.get(name.casefold())
        if existing:
            answer = QMessageBox.question(
                self,
                "Character Already Exists",
                f"“{name}” already exists in this book ({format_character_registry_entry(existing)}).\n\nReuse it?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._check_character(existing["name"])
            return

        chapter = self._chapter()
        self.registry[name.casefold()] = {
            "name": name,
            "chapters": {int(chapter.number)} if chapter else set(),
            "sources": {"manual assignment"},
        }
        self._refresh_character_list()
        self._check_character(name)

    def _check_character(self, name):
        key = str(name).casefold()
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "").casefold() == key:
                item.setCheckState(Qt.CheckState.Checked)
                self.character_list.scrollToItem(item)
                break

    def _assign_double_clicked_character(self, item):
        self._clear_character_checks()
        item.setCheckState(Qt.CheckState.Checked)
        self._assign_checked()

    def _quick_assign_selected(self, _item):
        segment = self.current_segment
        if not segment or not segment.suggestions:
            self._show_dialogue(self.dialogue_list.currentRow())
            segment = self.current_segment
        if segment and segment.suggestions:
            self._clear_character_checks()
            self._check_character(segment.suggestions[0][0])
            self._assign_checked()

    def _assign_checked(self):
        chapter = self._chapter()
        selected = self._selected_source_span()
        speakers = self._checked_names()
        if not chapter or not selected:
            return
        if not speakers:
            QMessageBox.information(self, "Speaker Required", "Check at least one book character.")
            return

        start, end, raw = selected
        assignment = normalize_assignment(
            {
                "start": start,
                "end": end,
                "text": str(raw).strip(),
                "source": "manual",
            },
            speakers,
            self.mode.currentData() or "chorus",
        )
        chapter.dialogue_assignments = [
            item for item in getattr(chapter, "dialogue_assignments", [])
            if not (
                int(item.get("start", -1)) == start
                and int(item.get("end", -1)) == end
            )
        ]
        chapter.dialogue_assignments.append(assignment)

        self.registry.setdefault(
            speakers[0].casefold(),
            {"name": speakers[0], "chapters": set(), "sources": {"manual assignment"}},
        )["chapters"].add(int(chapter.number))

        self._refresh_character_list()
        self._filter_rows()
        self._select_dialogue_by_span(start, end)
        if self.on_save:
            self.on_save(self.chapters)

    def _unassign(self):
        chapter = self._chapter()
        selected = self._selected_source_span()
        if not chapter or not selected:
            return
        start, end, _raw = selected
        chapter.dialogue_assignments = [
            item for item in getattr(chapter, "dialogue_assignments", [])
            if not (
                int(item.get("start", -1)) == start
                and int(item.get("end", -1)) == end
            )
        ]
        self._filter_rows()
        self._select_dialogue_by_span(start, end)
        if self.on_save:
            self.on_save(self.chapters)

    def _select_dialogue_by_span(self, start, end):
        for row in range(self.dialogue_list.count()):
            item = self.dialogue_list.item(row)
            index = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(index, int) and 0 <= index < len(self.current_dialogues):
                a, b, _ = self.current_dialogues[index]
                if a == start and b == end:
                    self.dialogue_list.setCurrentRow(row)
                    break
