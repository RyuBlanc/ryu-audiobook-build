"""Data-driven, offline AI analysis report window for Ryu Audiobook.

The presentation is built from the saved report schema at runtime. Missing data
removes its section rather than displaying fabricated placeholder content.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(filter(None, (_text(item).strip() for item in value)))
    return str(value).strip()


def _score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0.0, min(1.0, number))


def _evidence_line(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    quote = _text(value.get("quote"))
    if not quote:
        return ""
    start, end = value.get("start"), value.get("end")
    location = ""
    if isinstance(start, int) and isinstance(end, int):
        location = f"  [source characters {start}–{end}]"
    return f"Evidence: “{quote}”{location}"


def build_ai_analysis_report_model(report: dict[str, Any]) -> dict[str, Any]:
    """Convert saved report JSON into display-ready sections without inventing data."""
    report = report if isinstance(report, dict) else {}
    sections: list[dict[str, Any]] = []

    def add_section(key: str, title: str, items: list[dict[str, Any]]) -> None:
        valid = [item for item in items if isinstance(item, dict) and item.get("title")]
        if valid:
            sections.append({"key": key, "title": title, "items": valid})

    chapters = report.get("chapter_summaries")
    if not isinstance(chapters, list) or not chapters:
        chapters = report.get("chapters") if isinstance(report.get("chapters"), list) else []
    chapter_items: list[dict[str, Any]] = []
    for row in chapters:
        if not isinstance(row, dict):
            continue
        number = row.get("chapter", "?")
        chapter_title = _text(row.get("chapter_title") or row.get("title"))
        title = f"Chapter {number}" + (f" — {chapter_title}" if chapter_title else "")
        details = []
        summary = _text(row.get("summary") or row.get("chapter_summary"))
        purpose = _text(row.get("purpose") or row.get("chapter_purpose"))
        if summary:
            details.append(f"Summary: {summary}")
        if purpose:
            details.append(f"Purpose: {purpose}")
        if details:
            chapter_items.append({"title": title, "details": details})
    add_section("chapters", "Chapters", chapter_items)

    theme_items: list[dict[str, Any]] = []
    for theme in report.get("book_themes") or []:
        if not isinstance(theme, dict):
            continue
        details = []
        for observation in theme.get("observations") or []:
            if not isinstance(observation, dict):
                continue
            chapter = observation.get("chapter", "?")
            interpretation = _text(observation.get("interpretation"))
            line = f"Chapter {chapter}"
            if interpretation:
                line += f": {interpretation}"
            evidence = _evidence_line(observation.get("evidence"))
            if evidence:
                line += f"\n{evidence}"
            if line:
                details.append(line)
        confidence_values = [
            score for score in (_score(row.get("confidence")) for row in theme.get("observations") or [] if isinstance(row, dict))
            if score is not None
        ]
        theme_items.append({
            "title": _text(theme.get("name")) or "Untitled theme",
            "details": details,
            "confidence": max(confidence_values) if confidence_values else None,
        })
    add_section("themes", "Themes", theme_items)

    emotion_items: list[dict[str, Any]] = []
    for beat in report.get("emotional_arc") or []:
        if not isinstance(beat, dict):
            continue
        emotion = _text(beat.get("emotion")) or "Emotional beat"
        chapter = beat.get("chapter", "?")
        chapter_title = _text(beat.get("chapter_title"))
        title = f"Chapter {chapter}" + (f" — {chapter_title}" if chapter_title else "") + f" • {emotion}"
        details = [_text(beat.get("note"))]
        evidence = _evidence_line(beat.get("evidence"))
        if evidence:
            details.append(evidence)
        emotion_items.append({
            "title": title,
            "details": [line for line in details if line],
            "intensity": _score(beat.get("intensity")),
            "confidence": _score(beat.get("confidence")),
        })
    add_section("emotional_arc", "Emotional journey", emotion_items)

    character_items: list[dict[str, Any]] = []
    arcs = report.get("character_arcs") or {}
    if isinstance(arcs, dict):
        arc_rows = arcs.items()
    elif isinstance(arcs, list):
        arc_rows = ((_text(row.get("character") or row.get("name")), row) for row in arcs if isinstance(row, dict))
    else:
        arc_rows = []
    for name, arc in arc_rows:
        if not isinstance(arc, dict):
            continue
        details = []
        for observation in arc.get("observations") or []:
            if not isinstance(observation, dict):
                continue
            chapter = observation.get("chapter", "?")
            chapter_title = _text(observation.get("chapter_title"))
            lead = f"Chapter {chapter}" + (f" — {chapter_title}" if chapter_title else "")
            facts = []
            for label, field in (("Motivation", "motivation"), ("Goal", "goal"), ("Change", "change")):
                value = _text(observation.get(field))
                if value:
                    facts.append(f"{label}: {value}")
            evidence = _evidence_line(observation.get("evidence"))
            detail = lead + (f"\n{' • '.join(facts)}" if facts else "")
            if evidence:
                detail += f"\n{evidence}"
            details.append(detail)
        if name or details:
            character_items.append({"title": _text(name) or "Character", "details": details})
    add_section("character_arcs", "Character development", character_items)

    relationship_items: list[dict[str, Any]] = []
    for row in report.get("relationships") or []:
        if not isinstance(row, dict):
            continue
        names = " ↔ ".join(filter(None, (_text(row.get("character_a")), _text(row.get("character_b")))))
        title = names or "Relationship"
        chapter = row.get("chapter")
        details = []
        if chapter is not None:
            details.append(f"Chapter {chapter}" + (f" — {_text(row.get('chapter_title'))}" if _text(row.get("chapter_title")) else ""))
        dynamic = _text(row.get("dynamic"))
        if dynamic:
            details.append(dynamic)
        evidence = _evidence_line(row.get("evidence"))
        if evidence:
            details.append(evidence)
        relationship_items.append({"title": title, "details": details, "confidence": _score(row.get("confidence"))})
    add_section("relationships", "Relationships", relationship_items)

    event_items: list[dict[str, Any]] = []
    for row in report.get("key_events") or []:
        if not isinstance(row, dict):
            continue
        event = _text(row.get("event"))
        if not event:
            continue
        chapter = row.get("chapter", "?")
        details = [_text(row.get("event_type"))]
        evidence = _evidence_line(row.get("evidence"))
        if evidence:
            details.append(evidence)
        event_items.append({
            "title": f"Chapter {chapter} — {event}",
            "details": [item for item in details if item],
            "confidence": _score(row.get("confidence")),
        })
    add_section("key_events", "Key events", event_items)

    pronunciation_items: list[dict[str, Any]] = []
    for row in report.get("pronunciation") or []:
        if not isinstance(row, dict):
            continue
        written = _text(row.get("written"))
        spoken = _text(row.get("spoken"))
        if not written and not spoken:
            continue
        title = f"{written} → {spoken}".strip(" →")
        details = []
        for label, field in (
            ("IPA", "ipa"), ("Language", "source_language"),
            ("Script", "script"), ("Reason", "reason"),
        ):
            value = _text(row.get(field))
            if value:
                details.append(f"{label}: {value}")
        alternatives = _text(row.get("alternatives"))
        if alternatives:
            details.append(f"Alternative readings: {alternatives}")
        occurrences = row.get("occurrences") or []
        occurrence_labels = []
        for occurrence in occurrences:
            if isinstance(occurrence, dict):
                label = f"Chapter {occurrence.get('chapter', '?')}"
                if _text(occurrence.get("chapter_title")):
                    label += f" — {_text(occurrence.get('chapter_title'))}"
                occurrence_labels.append(label)
        if occurrence_labels:
            details.append("Occurrences: " + "; ".join(occurrence_labels))
        if row.get("ambiguous_across_chapters"):
            details.append("Review required: different readings were detected across chapters.")
        pronunciation_items.append({
            "title": title or "Pronunciation",
            "details": details,
            "confidence": _score(row.get("confidence")),
        })
    add_section("pronunciation", "Pronunciation", pronunciation_items)

    continuity_items = [
        {"title": f"Note {index + 1}", "details": [_text(note)]}
        for index, note in enumerate(report.get("continuity_notes") or [])
        if _text(note)
    ]
    add_section("continuity", "Continuity", continuity_items)

    chapter_count = len(report.get("chapters") or []) if isinstance(report.get("chapters"), list) else 0
    if not chapter_count:
        chapter_count = len(chapter_items)
    counts = {
        "chapters": chapter_count,
        "themes": len(theme_items),
        "emotional_beats": len(emotion_items),
        "characters": len(character_items),
        "pronunciation_terms": len(pronunciation_items),
        "key_events": len(event_items),
    }
    return {
        "schema_version": report.get("analysis_schema_version", report.get("version", 1)),
        "learning_scope": _text(report.get("learning_scope")) or "Book local",
        "counts": counts,
        "sections": sections,
        "has_content": bool(sections),
    }


class AIAnalysisReportWindow(QWidget):
    """Refreshable report window whose tabs and cards follow saved analysis data."""

    def __init__(self, report_path: str | Path, parent: QWidget | None = None):
        super().__init__(parent, Qt.Window)
        self.report_path = Path(report_path)
        self.setWindowTitle("Ryu Audiobook — Offline AI Analysis")
        self.resize(1080, 760)

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Offline AI Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title, 1)
        refresh_button = QPushButton("Refresh saved analysis")
        refresh_button.clicked.connect(self.reload)
        header.addWidget(refresh_button)
        root.addLayout(header)

        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        root.addWidget(self.meta_label)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)

        # Populate from this project's saved analysis immediately on first open.
        # The Refresh action remains available after subsequent analysis runs.
        self.reload()

    def reload(self) -> None:
        try:
            raw = json.loads(self.report_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("The saved report root must be a JSON object.")
            model = build_ai_analysis_report_model(raw)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            model = build_ai_analysis_report_model({})
            self.meta_label.setText(f"Unable to load saved analysis: {exc}")
        else:
            counts = model["counts"]
            self.meta_label.setText(
                f"Schema {model['schema_version']} • Learning scope: {model['learning_scope']} • "
                f"{counts['chapters']} chapters • {counts['themes']} themes • "
                f"{counts['emotional_beats']} emotional beats • {counts['characters']} character arcs • "
                f"{counts['pronunciation_terms']} pronunciation terms"
            )

        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()

        if not model["sections"]:
            empty = QLabel("No report sections contain saved analysis yet. Run Analyze Book with AI and refresh this view.")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            self.tabs.addTab(empty, "Overview")
            return

        for section in model["sections"]:
            self.tabs.addTab(self._section_view(section), section["title"])

    def _section_view(self, section: dict[str, Any]) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        for item in section["items"]:
            card = QGroupBox(item["title"], content)
            card_layout = QVBoxLayout(card)
            for detail in item.get("details") or []:
                label = QLabel(detail)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(label)

            for field, caption in (("intensity", "Intensity"), ("confidence", "Confidence")):
                value = item.get(field)
                if value is None:
                    continue
                bar = QProgressBar(card)
                bar.setRange(0, 100)
                bar.setValue(round(value * 100))
                bar.setFormat(f"{caption}: %p%")
                card_layout.addWidget(bar)

            if not item.get("details") and item.get("confidence") is None and item.get("intensity") is None:
                placeholder = QLabel("No additional detail was saved for this entry.")
                placeholder.setWordWrap(True)
                card_layout.addWidget(placeholder)
            layout.addWidget(card)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll
