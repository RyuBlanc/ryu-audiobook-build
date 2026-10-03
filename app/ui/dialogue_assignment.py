from __future__ import annotations

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QInputDialog,
)

from app.chapters.dialogue import DialogueSegment, dialogue_segment_for_selection
from app.chapters.detector import Chapter
from app.chapters.assignment_utils import (
    build_book_character_registry,
    format_character_registry_entry,
    normalize_assignment,
)


class DialogueAssignmentDialog(QDialog):
    """Fast, book-wide speaker assignment for one selected dialogue.

    The classic Assign Selected Dialogue action remains available, but the
    chooser now understands the whole book's saved character list and supports
    multiple speakers on the same dialogue span.
    """

    def __init__(
        self,
        chapter: Chapter,
        start: int = 0,
        end: int = 0,
        book_chapters: list[Chapter] | None = None,
        project_folder=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Assign Dialogue Speaker")
        self.resize(860, 620)
        self.chapter = chapter
        self.start = max(0, min(int(start), len(chapter.text)))
        self.end = max(self.start, min(int(end), len(chapter.text)))
        self.book_chapters = list(book_chapters or [chapter])
        self.project_folder = project_folder
        self.selected_segment = dialogue_segment_for_selection(chapter, self.start, self.end)
        self.registry = build_book_character_registry(self.book_chapters, project_folder)
        self.characters: list[str] = [entry["name"] for entry in self.registry.values()]
        self.assigned = False

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>Assign Dialogue Speaker</h2>"))
        root.addWidget(QLabel(
            "Select one or more saved book characters for this exact dialogue. "
            "Use + Add Character only when the speaker is genuinely new."
        ))

        root.addWidget(QLabel("<b>Selected dialogue</b>"))
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(70)
        self.preview.setStyleSheet("padding:8px;")
        root.addWidget(self.preview)

        self.detected = QLabel()
        self.detected.setWordWrap(True)
        root.addWidget(self.detected)

        root.addWidget(QLabel("<b>Suggested / saved book characters</b>"))
        self.suggestions = QListWidget()
        self.suggestions.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.suggestions.itemDoubleClicked.connect(self._quick_assign_item)
        root.addWidget(self.suggestions, 1)

        form = QHBoxLayout()
        form.addWidget(QLabel("Multi-speaker mode"))
        self.mode = QComboBox()
        self.mode.addItem("Simultaneous / voice blend", "chorus")
        self.mode.addItem("Sequential / repeat line", "sequential")
        form.addWidget(self.mode)
        form.addStretch(1)
        root.addLayout(form)

        actions = QHBoxLayout()
        add = QPushButton("＋ Add Character")
        add.setObjectName("primary")
        add.clicked.connect(self.create_character)
        actions.addWidget(add)

        clear = QPushButton("Clear Selection")
        clear.clicked.connect(self._clear_checks)
        actions.addWidget(clear)

        actions.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        assign = buttons.addButton("Assign Checked Speaker(s)", QDialogButtonBox.ButtonRole.AcceptRole)
        assign.clicked.connect(self.assign)
        buttons.rejected.connect(self.reject)
        actions.addWidget(buttons)
        root.addLayout(actions)

        self._populate_selection()

    def _selected_text(self) -> str:
        text = self.chapter.text or ""
        return text[self.start:self.end].strip()

    def _entry_item(self, name: str, display: str, checked: bool = False) -> QListWidgetItem:
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        return item

    def _populate_selection(self) -> None:
        selected = self._selected_text()
        self.preview.setText(selected or "No text selected.")
        self.suggestions.clear()

        suggestions = list(self.selected_segment.suggestions) if self.selected_segment else []
        top_name = suggestions[0][0] if suggestions else (
            self.selected_segment.suggested_speaker if self.selected_segment else None
        )

        if top_name:
            confidence = (
                suggestions[0][1]
                if suggestions
                else float(self.selected_segment.confidence or 0.0)
            )
            self.detected.setText(
                f"Quick suggestion: <b>{top_name}</b> · {confidence:.0%}. "
                "Double-click a character for a one-click assignment, or check multiple characters and assign them together."
            )
        else:
            self.detected.setText(
                "No high-confidence speaker was found locally. "
                "The list below contains characters already saved anywhere in this book."
            )

        added: set[str] = set()
        if suggestions:
            self.suggestions.addItem(QListWidgetItem("── Suggested from this dialogue ──"))
            for name, confidence, evidence in suggestions:
                entry = self.registry.get(name.casefold())
                location = format_character_registry_entry(entry) if entry else name
                display = f"{name}  ·  {confidence:.0%}  ·  {evidence}"
                if entry and location:
                    display += f"  ·  {location.split('  ·  ', 1)[1]}"
                self.suggestions.addItem(self._entry_item(name, display, False))
                added.add(name.casefold())

        self.suggestions.addItem(QListWidgetItem("── Saved characters in this book ──"))
        for key, entry in self.registry.items():
            if key in added:
                continue
            self.suggestions.addItem(
                self._entry_item(
                    entry["name"],
                    format_character_registry_entry(entry),
                    False,
                )
            )

        existing_speakers = []
        for item in getattr(self.chapter, "dialogue_assignments", []):
            if int(item.get("start", -1)) == self.start and int(item.get("end", -1)) == self.end:
                raw = item.get("speakers")
                if isinstance(raw, list) and raw:
                    existing_speakers = [str(v).strip() for v in raw if str(v).strip()]
                elif item.get("speaker"):
                    existing_speakers = [str(item["speaker"]).strip()]
                break

        selected = {name.casefold() for name in existing_speakers}
        if existing_speakers:
            self.detected.setText(
                f"Existing assignment: <b>{', '.join(existing_speakers)}</b>. "
                "Change the checked speakers and assign again to update it."
            )

        for row in range(self.suggestions.count()):
            item = self.suggestions.item(row)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name and str(name).casefold() in selected:
                item.setCheckState(Qt.CheckState.Checked)

    def _checked_speakers(self) -> list[str]:
        result = []
        for row in range(self.suggestions.count()):
            item = self.suggestions.item(row)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name and item.checkState() == Qt.CheckState.Checked:
                clean = str(name).strip()
                if clean and clean.casefold() not in {v.casefold() for v in result}:
                    result.append(clean)
        return result

    def _clear_checks(self) -> None:
        for row in range(self.suggestions.count()):
            item = self.suggestions.item(row)
            if item.data(Qt.ItemDataRole.UserRole):
                item.setCheckState(Qt.CheckState.Unchecked)

    def _quick_assign_item(self, item: QListWidgetItem) -> None:
        name = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not name:
            return
        self._clear_checks()
        item.setCheckState(Qt.CheckState.Checked)
        self.assign()

    def _existing_character_choice(self) -> str | None:
        options = ["＋ Create brand-new character…"] + self.characters
        if not self.characters:
            return None
        choice, ok = QInputDialog.getItem(
            self,
            "Add Character",
            "A character with this name may already exist elsewhere in the book. Select one to reuse it:",
            options,
            0,
            False,
        )
        if not ok:
            return None
        if choice == options[0]:
            return ""
        return choice

    def create_character(self) -> None:
        existing = self._existing_character_choice()
        if existing is not None and existing != "":
            self._check_or_add_character(existing)
            return

        name, ok = QInputDialog.getText(
            self,
            "Create Character",
            "New character name:",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return

        known = self.registry.get(name.casefold())
        if known:
            answer = QMessageBox.question(
                self,
                "Character Already Exists",
                f"“{name}” is already saved in this book "
                f"({format_character_registry_entry(known)}).\n\nUse that existing character?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._check_or_add_character(known["name"])
            return

        # New character becomes book-visible immediately and can be assigned
        # without reopening the dialog.
        self.registry[name.casefold()] = {
            "name": name,
            "chapters": {int(self.chapter.number)},
            "sources": {"manual assignment"},
        }
        self.characters.append(name)
        self._check_or_add_character(name)

    def _check_or_add_character(self, name: str) -> None:
        target_key = str(name).casefold()
        for row in range(self.suggestions.count()):
            item = self.suggestions.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "").casefold() == target_key:
                item.setCheckState(Qt.CheckState.Checked)
                self.suggestions.scrollToItem(item)
                return

        # New/external character not displayed yet.
        self.suggestions.addItem(
            self._entry_item(name, f"{name}  ·  selected for this dialogue", True)
        )

    def assign(self) -> None:
        selected_text = self._selected_text()
        if not selected_text:
            QMessageBox.information(self, "Dialogue Required", "Select dialogue text first.")
            return

        speakers = self._checked_speakers()
        if not speakers:
            QMessageBox.information(
                self,
                "Speaker Required",
                "Check at least one character. Use + Add Character when needed.",
            )
            return

        assignment = normalize_assignment(
            {
                "start": int(self.start),
                "end": int(self.end),
                "text": selected_text,
                "source": "manual",
            },
            speakers,
            mode=self.mode.currentData() or "chorus",
        )

        # Replace only the exact same selected dialogue span.
        self.chapter.dialogue_assignments = [
            item
            for item in getattr(self.chapter, "dialogue_assignments", [])
            if not (
                int(item.get("start", -1)) == assignment["start"]
                and int(item.get("end", -1)) == assignment["end"]
            )
        ]
        self.chapter.dialogue_assignments.append(assignment)
        self.assigned = True
        self.accept()
