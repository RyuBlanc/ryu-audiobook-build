from __future__ import annotations

from collections import OrderedDict
import json
from pathlib import Path

from app.core.state import load_state


def assignment_speakers(item: dict | None) -> list[str]:
    """Return all speakers recorded for an assignment, preserving old data."""
    if not isinstance(item, dict):
        return []
    raw = item.get("speakers")
    if isinstance(raw, (list, tuple)):
        names = [str(value).strip() for value in raw if str(value).strip()]
        if names:
            return list(dict.fromkeys(names))
    speaker = str(item.get("speaker") or "").strip()
    return [speaker] if speaker else []


def normalize_assignment(item: dict, speakers: list[str], mode: str = "chorus") -> dict:
    """Store a multi-speaker assignment while keeping old 'speaker' compatible."""
    names = list(dict.fromkeys(str(value).strip() for value in speakers if str(value).strip()))
    item = dict(item)
    if not names:
        item.pop("speakers", None)
        item.pop("speaker", None)
        item.pop("multi_speaker_mode", None)
        return item
    item["speaker"] = names[0]
    item["speakers"] = names
    if len(names) > 1:
        item["multi_speaker_mode"] = mode or "chorus"
    else:
        item.pop("multi_speaker_mode", None)
    return item


def _load_ai_character_names(project_folder: Path | None) -> list[str]:
    if not project_folder:
        return []
    analysis_dir = Path(project_folder) / "analysis"
    aggregate = analysis_dir / "audiobook_brain.json"
    payloads: list[dict] = []
    if aggregate.exists():
        try:
            data = json.loads(aggregate.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                payloads.append(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    if not payloads:
        for path in sorted(analysis_dir.glob("chapter_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                payloads.append(data)

    names: list[str] = []
    for payload in payloads:
        bible = payload.get("book_bible", {}) or {}
        if isinstance(bible, dict):
            for name, value in bible.items():
                name = str(name).strip()
                if name:
                    names.append(name)
                if isinstance(value, dict):
                    names.extend(
                        str(alias).strip()
                        for alias in (value.get("aliases") or [])
                        if str(alias).strip()
                    )
        for character in payload.get("characters", []) or []:
            if isinstance(character, dict):
                name = str(character.get("name") or "").strip()
                if name:
                    names.append(name)
    return names


def build_book_character_registry(chapters, project_folder: Path | None = None) -> OrderedDict[str, dict]:
    """Collect saved character names across the whole book.

    Sources are manual assignments, saved Voice Cast names and completed/partial
    Audiobook AI character analysis. Chapter numbers are retained so the UI can
    explain why an apparently new name may already be the same character.
    """
    registry: OrderedDict[str, dict] = OrderedDict()

    def add(name: str, chapter_number: int | None = None, source: str = "") -> None:
        clean = str(name or "").strip()
        if not clean:
            return
        key = clean.casefold()
        entry = registry.setdefault(
            key,
            {"name": clean, "chapters": set(), "sources": set()},
        )
        if chapter_number is not None:
            entry["chapters"].add(int(chapter_number))
        if source:
            entry["sources"].add(source)

    for chapter in chapters or []:
        number = getattr(chapter, "number", None)
        for item in getattr(chapter, "dialogue_assignments", []) or []:
            for speaker in assignment_speakers(item):
                add(speaker, number, "dialogue assignment")

    if project_folder:
        state = load_state(project_folder)
        cast = state.get("voice_cast", {}) if isinstance(state, dict) else {}
        if isinstance(cast, dict):
            for name in cast:
                add(name, None, "saved voice cast")

    for name in _load_ai_character_names(project_folder):
        add(name, None, "Audiobook AI")

    # Stable, human-friendly ordering.
    return OrderedDict(
        (key, value)
        for key, value in sorted(
            registry.items(),
            key=lambda pair: pair[1]["name"].casefold(),
        )
    )


def format_character_registry_entry(entry: dict) -> str:
    chapters = sorted(entry.get("chapters") or [])
    source = ", ".join(sorted(entry.get("sources") or []))
    if chapters:
        location = "Chapter" + ("s" if len(chapters) != 1 else "") + " " + ", ".join(map(str, chapters))
    else:
        location = source or "saved book character"
    if source and chapters:
        return f"{entry['name']}  ·  {location}  ·  {source}"
    return f"{entry['name']}  ·  {location}"
