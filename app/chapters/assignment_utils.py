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
            {"name": clean, "chapters": set(), "sources": set(), "voice": None},
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
            for name, voice in cast.items():
                add(name, None, "saved voice cast")
                entry = registry.get(str(name).casefold())
                if entry:
                    entry["voice"] = str(voice).strip() or None

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
    voice = str(entry.get("voice") or "").strip()
    voice_note = f"Voice: {voice}" if voice else "Voice: not assigned"
    if source and chapters:
        return f"{entry['name']}  ·  {location}  ·  {voice_note}  ·  {source}"
    return f"{entry['name']}  ·  {location}  ·  {voice_note}"



def assign_dialogue_to_chapters(chapters, dialogue_text: str, speakers: list[str],
                                chapter_number: int | None = None, mode: str = "single") -> dict:
    """Persist an explicit speaker choice against one uniquely matched source span."""
    import re
    requested = str(dialogue_text or "").strip()
    names = list(dict.fromkeys(str(value).strip() for value in (speakers or []) if str(value).strip()))
    if not requested:
        raise ValueError("Select a dialogue passage before assigning a speaker.")
    if not names:
        raise ValueError("Select at least one saved character.")
    if len(requested) > 5000:
        raise ValueError("The selected dialogue passage is too long to assign safely.")
    candidates = []
    for chapter in chapters or []:
        if chapter_number is not None and int(getattr(chapter, "number", 0)) != int(chapter_number):
            continue
        source = str(getattr(chapter, "text", "") or "")
        pieces = re.split(r"\s+", requested)
        pattern = r"\s+".join(re.escape(piece) for piece in pieces if piece)
        if pattern:
            for match in re.finditer(pattern, source):
                candidates.append((chapter, match.start(), match.end(), source[match.start():match.end()]))
    if not candidates:
        raise ValueError("The selected dialogue text was not found in the saved chapter text. Refresh the chapter and select a passage from the imported book; no assignment was saved.")
    if len(candidates) != 1:
        raise ValueError("That dialogue passage appears more than once. Select its specific chapter or a longer unique passage; no assignment was saved.")
    chapter, start, end, exact_text = candidates[0]
    existing = list(getattr(chapter, "dialogue_assignments", []) or [])
    overlapping = [item for item in existing if isinstance(item, dict)
        and isinstance(item.get("start"), int) and isinstance(item.get("end"), int)
        and item["start"] < end and item["end"] > start
        and not (item["start"] == start and item["end"] == end)]
    if overlapping:
        raise ValueError("The selected passage overlaps another saved speaker assignment. Edit or remove the existing assignment first.")
    base = next((dict(item) for item in existing if isinstance(item, dict)
                 and item.get("start") == start and item.get("end") == end),
                {"start": start, "end": end, "text": exact_text, "source": "manual"})
    base.update({"start": start, "end": end, "text": exact_text, "source": "manual"})
    normalized = normalize_assignment(base, names, mode)
    normalized["source"] = "manual"
    normalized["confidence"] = 1.0
    existing = [item for item in existing if not (isinstance(item, dict)
                and item.get("start") == start and item.get("end") == end)]
    existing.append(normalized)
    existing.sort(key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0))))
    chapter.dialogue_assignments = existing
    return {"chapter_number": chapter.number, "start": start, "end": end, "text": exact_text,
            "speakers": names, "source": "manual", "confidence": 1.0, "saved": True}
