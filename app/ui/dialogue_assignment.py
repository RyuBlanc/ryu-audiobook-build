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
    """Human-in-the-loop dialogue assignment for the chapter editor."""

    def __init__(self, chapter: Chapter, start: int = 0, end: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dialogue & Character Assignment")
        self.resize(760, 560)
        self.chapter = chapter
        self.start = start
        self.end = end
        self.segments = dialogue_segments(chapter)
        self.characters = self._character_names()
        self.selected_segment: DialogueSegment | None = self._best_segment()
        self.assigned = False

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>Assign Dialogue Speaker</h2>"))
        root.addWidget(QLabel(
            "Select a dialogue passage in the chapter, review the suggested speaker, "
            "then confirm or create a character. Your correction is saved with the chapter."
        ))

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)

        root.addWidget(QLabel("Suggested character"))
        self.combo = QComboBox()
        self.combo.addItems(self.characters)
        self.combo.addItem("+ Create new character…")
        root.addWidget(self.combo)

        self.confidence = QLabel()
        root.addWidget(self.confidence)

        root.addWidget(QLabel("Detected dialogue in this chapter"))
        self.dialogue_list = QListWidget()
        for segment in self.segments:
            label = segment.suggested_speaker or "Unknown speaker"
            percent = int(round(segment.confidence * 100)) if segment.confidence else 0
            item = QListWidgetItem(f"{segment.index}. {label} · {percent}% · {segment.text[:100]}")
            item.setData(32, segment)
            self.dialogue_list.addItem(item)
        root.addWidget(self.dialogue_list, 1)
        self.dialogue_list.currentItemChanged.connect(self._select_list_segment)

        actions = QHBoxLayout()
        create = QPushButton("+ Create Character")
        create.clicked.connect(self.create_character)
        actions.addWidget(create)
        actions.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.assign)
        buttons.rejected.connect(self.reject)
        actions.addWidget(buttons)
        root.addLayout(actions)

        if self.selected_segment:
            self._apply_segment(self.selected_segment)
        elif self.dialogue_list.count():
            self.dialogue_list.setCurrentRow(0)
        else:
            self._set_preview("No quoted dialogue was detected in this chapter. You can still create a character and use the selected passage as a manual assignment.")

    def _character_names(self) -> list[str]:
        names = []
        for item in self.chapter.dialogue_assignments:
            name = str(item.get("speaker", "")).strip()
            if name and name not in names:
                names.append(name)
        for segment in self.segments:
            if segment.suggested_speaker and segment.suggested_speaker not in names:
                names.append(segment.suggested_speaker)
        return names

    def _best_segment(self) -> DialogueSegment | None:
        if self.end <= self.start:
            return None
        overlaps = [s for s in self.segments if s.start <= self.end and s.end >= self.start]
        if not overlaps:
            return None
        return max(overlaps, key=lambda s: min(self.end, s.end) - max(self.start, s.start))

    def _select_list_segment(self, current, _previous) -> None:
        if current is not None:
            segment = current.data(32)
            if isinstance(segment, DialogueSegment):
                self.selected_segment = segment
                self._apply_segment(segment)

    def _apply_segment(self, segment: DialogueSegment) -> None:
        self.start, self.end = segment.start, segment.end
        self._set_preview(segment.text)
        self.confidence.setText(
            f"AI suggestion: {segment.suggested_speaker or 'No confident speaker'} · "
            f"confidence {int(round(segment.confidence * 100))}%"
        )
        if segment.suggested_speaker:
            index = self.combo.findText(segment.suggested_speaker)
            if index >= 0:
                self.combo.setCurrentIndex(index)

    def _set_preview(self, text: str) -> None:
        self.preview.setText(f"<b>Selected dialogue</b><br>{text}")

    def create_character(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Character", "Character name:")
        name = name.strip()
        if not ok or not name:
            return
        if name not in self.characters:
            self.characters.append(name)
            self.combo.insertItem(self.combo.count() - 1, name)
        self.combo.setCurrentText(name)

    def assign(self) -> None:
        if self.combo.currentText() == "+ Create new character…":
            self.create_character()
            if self.combo.currentText() == "+ Create new character…":
                return
        speaker = self.combo.currentText().strip()
        if not speaker:
            QMessageBox.information(self, "Speaker Required", "Choose or create a character first.")
            return
        selected_text = self.selected_segment.text if self.selected_segment else self.chapter.text[self.start:self.end].strip()
        if not selected_text:
            QMessageBox.information(self, "Dialogue Required", "Select a dialogue passage first.")
            return

        assignment = {
            "start": int(self.start),
            "end": int(self.end),
            "text": selected_text,
            "speaker": speaker,
            "source": "manual" if not self.selected_segment or self.selected_segment.suggested_speaker != speaker else "confirmed",
        }
        self.chapter.dialogue_assignments = [
            item for item in self.chapter.dialogue_assignments
            if not (int(item.get("start", -1)) == assignment["start"] and int(item.get("end", -1)) == assignment["end"])
        ]
        self.chapter.dialogue_assignments.append(assignment)
        self.assigned = True
        self.accept()
