"""Project-scoped, source-backed Character Studio assignment inspector data."""

from __future__ import annotations

from app.chapters.assignment_utils import assignment_speakers


_AI_SOURCES = {"ai", "ai-analyzed", "ai_analyzed"}
_MANUAL_SOURCES = {"manual"}


def _source_class(value: object) -> tuple[str, str]:
    source = str(value or "").strip().casefold().replace("_", "-")
    if source in _AI_SOURCES:
        return "ai", "AI-analyzed assignment"
    if source in _MANUAL_SOURCES:
        return "manual", "Manual assignment"
    return "unknown", "Source not recorded"


def build_character_assignment_inspector(
    chapters,
    character: dict,
    story_name: str,
    offset: int = 0,
    limit: int = 30,
) -> dict:
    """Build real assignment stats and one page of dialogue for a saved character.

    Dialogue rows are included only when their persisted offsets still identify
    the exact saved source text. Legacy assignments without provenance remain
    visible, but are never guessed to be AI- or manually assigned.
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Dialogue pagination offset must be a non-negative integer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Dialogue page size must be between 1 and 100.")

    name = str(character.get("name") or "").strip()
    aliases = character.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    matching_names = {
        value.casefold()
        for value in [name, *(str(alias).strip() for alias in aliases)]
        if value
    }
    voice = str(character.get("voice_profile") or character.get("voice") or "").strip()
    story = str(story_name or "").strip()

    all_rows: list[dict] = []
    seen_ids: set[str] = set()
    for chapter in chapters or []:
        chapter_number = getattr(chapter, "number", None)
        chapter_title = str(getattr(chapter, "title", "") or "")
        source_text = str(getattr(chapter, "text", "") or "")
        assignments = getattr(chapter, "dialogue_assignments", []) or []
        chapter_rows: list[dict] = []
        for item in assignments:
            if not isinstance(item, dict):
                continue
            speakers = assignment_speakers(item)
            if not any(speaker.casefold() in matching_names for speaker in speakers):
                continue
            start, end = item.get("start"), item.get("end")
            if (
                isinstance(start, bool) or not isinstance(start, int)
                or isinstance(end, bool) or not isinstance(end, int)
                or start < 0 or end <= start or end > len(source_text)
            ):
                continue
            text = source_text[start:end]
            saved_text = item.get("text")
            if not text.strip() or (saved_text is not None and str(saved_text) != text):
                continue
            row_id = f"{chapter_number}:{start}:{end}"
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            source_class, source_label = _source_class(item.get("source"))
            chapter_rows.append({
                "id": row_id,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title or f"Chapter {chapter_number}",
                "start": start,
                "end": end,
                "text": text,
                "speakers": speakers,
                "source": str(item.get("source") or ""),
                "source_class": source_class,
                "source_label": source_label,
            })
        chapter_rows.sort(key=lambda row: (row["start"], row["end"]))
        all_rows.extend(chapter_rows)

    total = len(all_rows)
    ai_count = sum(row["source_class"] == "ai" for row in all_rows)
    manual_count = sum(row["source_class"] == "manual" for row in all_rows)
    unknown_count = total - ai_count - manual_count
    chapter_count = len({row["chapter_number"] for row in all_rows})
    ai_percent = (ai_count / total * 100) if total else 0

    return {
        "character_name": name,
        "story_name": story,
        "stats": {
            "assigned_voice": voice or "Unassigned",
            "dialogue_lines": total,
            "chapters": chapter_count,
            "ai_assigned_percent": ai_percent,
            "ai_assigned_lines": ai_count,
            "manual_assigned_lines": manual_count,
            "source_unavailable_lines": unknown_count,
        },
        "rows": all_rows[offset:offset + limit],
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + limit < total,
    }
