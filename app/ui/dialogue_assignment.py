from __future__ import annotations

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

from app.chapters.dialogue import DialogueSegment, dialogue_segments
from app.chapters.detector import Chapter


class DialogueAssignmentDialog(QDialog):
    """Assign the speaker for the exact text the user selected.

    The selection is authoritative: the dialog never replaces it with a
    random nearby dialogue segment. AI suggestions are ranked separately and
    include the evidence used to produce them.
    """

    def __init__(self, chapter: Chapter, start: int = 0, end: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign Dialogue Speaker")
        self.resize(780, 520)
        self.chapter = chapter
        self.start = max(0, min(int(start), len(chapter.text)))
        self.end = max(self.start, min(int(end), len(chapter.text)))
        self.segments = dialogue_segments(chapter)
        self.selected_segment = self._segment_for_selection()
        self.characters = self._character_names()
        self.assigned = False

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>Assign Dialogue Speaker</h2>"))
        root.addWidget(QLabel(
            "The text you selected is fixed. Ryu suggests possible speakers below, "
            "but it will never change your selection automatically."
        ))

        selected_label = QLabel("Selected dialogue")
        selected_label.setStyleSheet("font-weight: 600;")
        root.addWidget(selected_label)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(70)
        root.addWidget(self.preview)

        self.detected = QLabel()
        self.detected.setWordWrap(True)
        root.addWidget(self.detected)

        root.addWidget(QLabel("Suggested speakers"))
        self.suggestions = QListWidget()
        self.suggestions.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        root.addWidget(self.suggestions, 1)
        self.suggestions.currentItemChanged.connect(self._suggestion_selected)

        form = QHBoxLayout()
        form.addWidget(QLabel("Assign to"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(280)
        self.combo.addItem("— Choose character —", None)
        for name in self.characters:
            self.combo.addItem(name, name)
        self.combo.addItem("+ Create new character…", "__create__")
        form.addWidget(self.combo, 1)
        create = QPushButton("+ Create Character")
        create.clicked.connect(self.create_character)
        form.addWidget(create)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.assign)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate_selection()

    def _character_names(self) -> list[str]:
        names: list[str] = []
        for item in getattr(self.chapter, "dialogue_assignments", []):
            name = str(item.get("speaker", "")).strip()
            if name and name not in names:
                names.append(name)
        for segment in self.segments:
            if segment.suggested_speaker and segment.suggested_speaker not in names:
                names.append(segment.suggested_speaker)
            for candidate, _score, _evidence in segment.suggestions:
                if candidate not in names:
                    names.append(candidate)
        return names

    def _selected_text(self) -> str:
        text = self.chapter.text or ""
        return text[self.start:self.end].strip()

    def _segment_for_selection(self) -> DialogueSegment | None:
        if self.end <= self.start:
            return None
        overlaps = [
            segment
            for segment in self.segments
            if segment.start < self.end and self.start < segment.end
        ]
        if not overlaps:
            return None

        # Prefer a segment that contains most of the user's selection.
        def overlap_ratio(segment: DialogueSegment) -> float:
            overlap = max(0, min(self.end, segment.end) - max(self.start, segment.start))
            selected_len = max(1, self.end - self.start)
            segment_len = max(1, segment.end - segment.start)
            return max(
                overlap / selected_len,
                overlap / segment_len,
            )

        overlaps.sort(key=overlap_ratio, reverse=True)
        # Do not make a confident suggestion when the selection spans
        # unrelated dialogue blocks.
        if len(overlaps) > 1 and overlap_ratio(overlaps[0]) < 0.90:
            return None
        return overlaps[0]

    def _populate_selection(self) -> None:
        selected = self._selected_text()
        self._set_preview(selected or "No text selected.")
        self.suggestions.clear()

        suggestions = list(self.selected_segment.suggestions) if self.selected_segment else []
        if suggestions:
            top = suggestions[0]
            self.detected.setText(
                f"Top suggestion: <b>{top[0]}</b> · {int(round(top[1] * 100))}%<br>"
                f"<span style='color:#aaa'>{top[2]}</span>"
            )
        else:
            self.detected.setText(
                "No reliable speaker evidence was found for this selection. "
                "Choose a character manually or create one."
            )

        for name, confidence, evidence in suggestions:
            percent = int(round(confidence * 100))
            item = QListWidgetItem(f"{name}  ·  {percent}%  ·  {evidence}")
            item.setData(32, name)
            self.suggestions.addItem(item)

        if suggestions:
            self.suggestions.setCurrentRow(0)
            self._set_combo_to_name(suggestions[0][0])

    def _set_preview(self, text: str) -> None:
        self.preview.setText(f"<div style='padding:8px'>{text}</div>")

    def _set_combo_to_name(self, name: str) -> None:
        index = self.combo.findData(name)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def _suggestion_selected(self, current, _previous) -> None:
        if current is None:
            return
        name = current.data(32)
        if name:
            self._set_combo_to_name(str(name))
            self.detected.setText(
                f"Selected suggestion: <b>{name}</b>. Review it, then press Assign."
            )

    def create_character(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Character", "Character name:")
        name = name.strip()
        if not ok or not name:
            return
        if name not in self.characters:
            self.characters.append(name)
            self.combo.insertItem(self.combo.count() - 1, name, name)
        self._set_combo_to_name(name)

    def assign(self) -> None:
        selected_text = self._selected_text()
        if not selected_text:
            QMessageBox.information(
                self,
                "Dialogue Required",
                "Select the dialogue text in the Chapter Text first.",
            )
            return

        if self.combo.currentData() == "__create__":
            self.create_character()
            if self.combo.currentData() == "__create__":
                return

        speaker = str(self.combo.currentData() or "").strip()
        if not speaker:
            QMessageBox.information(
                self,
                "Speaker Required",
                "Choose or create a character first.",
            )
            return

        assignment = {
            "start": int(self.start),
            "end": int(self.end),
            "text": selected_text,
            "speaker": speaker,
            "source": "manual",
        }

        # Replace only the exact same selection. Never delete an unrelated
        # nearby assignment.
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

