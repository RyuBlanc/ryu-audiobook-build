from __future__ import annotations

import re
from typing import Any

from .brain import AudiobookBrain, _numeric_score
from app.chapters.characters import _is_plausible_name
from app.tts.pronunciation_suggester import (
    is_likely_character_name_candidate,
    suggest_pronunciation,
)


def _safe_list(value: Any, limit: int = 12) -> list:
    return value[:limit] if isinstance(value, list) else []


def _safe_merge(self, out: dict, data: Any, seen: set[str], source_text: str = "", source_offset: int = 0) -> None:
    if not isinstance(data, dict):
        return

    for raw in _safe_list(data.get("characters")):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        # The model can label discourse words ("Having", "Right", "Already")
        # as speakers. Run the same source-grounded name gate used by the
        # local analyzer before these records become the book's character bible.
        if not name or not _is_plausible_name(name):
            continue
        item = dict(raw)
        item["confidence"] = _numeric_score(item.get("confidence", 0.0))
        if not isinstance(item.get("voice_direction"), dict):
            item["voice_direction"] = {}
        existing = next(
            (x for x in out.setdefault("characters", [])
             if isinstance(x, dict) and str(x.get("name") or "").casefold() == name.casefold()),
            None,
        )
        if existing is None:
            out["characters"].append(item)
        elif item["confidence"] > _numeric_score(existing.get("confidence", 0.0)):
            existing.update(item)

    def evidence_for(raw: dict) -> dict[str, Any] | None:
        quote = str(raw.get("evidence_quote") or "").strip()
        if not quote:
            return None
        positions: list[int] = []
        cursor = 0
        while len(positions) < 20:
            found = source_text.find(quote, cursor)
            if found < 0:
                break
            positions.append(found)
            cursor = found + 1
        if not positions:
            return None
        absolute_start = int(source_offset) + positions[0]
        return {
            "quote": quote,
            "start": absolute_start,
            "end": absolute_start + len(quote),
            "match_count_in_excerpt": len(positions),
        }

    summary = str(data.get("chapter_summary") or "").strip()
    if summary:
        segments = out.setdefault("chapter_summary_segments", [])
        if summary not in segments and len(segments) < 12:
            segments.append(summary[:700])

    purpose = str(data.get("chapter_purpose") or "").strip()
    purpose_evidence = evidence_for({"evidence_quote": data.get("chapter_purpose_evidence")})
    if purpose and purpose_evidence:
        out.setdefault("chapter_purpose_observations", []).append({
            "purpose": purpose[:500],
            "confidence": _numeric_score(data.get("chapter_purpose_confidence", 0.7)),
            "evidence": purpose_evidence,
        })

    def merge_evidence_rows(field: str, limit: int, minimum: float) -> None:
        target = out.setdefault(field, [])
        for raw_item in _safe_list(data.get(field), limit):
            if not isinstance(raw_item, dict):
                continue
            evidence = evidence_for(raw_item)
            if evidence is None:
                continue
            confidence = _numeric_score(raw_item.get("confidence", 0.0))
            if confidence < minimum:
                continue
            item: dict[str, Any] = {
                "confidence": confidence,
                "evidence": evidence,
            }
            if field == "themes":
                name = str(raw_item.get("name") or "").strip()[:120]
                if not name:
                    continue
                item.update({
                    "name": name,
                    "interpretation": str(raw_item.get("interpretation") or "").strip()[:500],
                })
                identity = (name.casefold(), evidence["start"])
                match = lambda row: (str(row.get("name") or "").casefold(), row.get("evidence", {}).get("start"))
            elif field == "emotional_beats":
                emotion = str(raw_item.get("emotion") or "").strip()[:80]
                if not emotion:
                    continue
                item.update({
                    "emotion": emotion,
                    "intensity": _numeric_score(raw_item.get("intensity", 0.5)),
                    "note": str(raw_item.get("note") or "").strip()[:300],
                })
                identity = (emotion.casefold(), evidence["start"])
                match = lambda row: (str(row.get("emotion") or "").casefold(), row.get("evidence", {}).get("start"))
            elif field == "key_events":
                event = str(raw_item.get("event") or "").strip()[:320]
                if not event:
                    continue
                item.update({
                    "event": event,
                    "event_type": str(raw_item.get("event_type") or "event").strip()[:80],
                })
                identity = (event.casefold(), evidence["start"])
                match = lambda row: (str(row.get("event") or "").casefold(), row.get("evidence", {}).get("start"))
            elif field == "character_observations":
                character = str(raw_item.get("character") or "").strip()[:120]
                if not character:
                    continue
                known = {
                    str(row.get("name") or "").casefold()
                    for row in out.get("characters", []) if isinstance(row, dict)
                }
                if character.casefold() not in source_text.casefold() and character.casefold() not in known:
                    continue
                item.update({
                    "character": character,
                    "motivation": str(raw_item.get("motivation") or "").strip()[:300],
                    "goal": str(raw_item.get("goal") or "").strip()[:300],
                    "change": str(raw_item.get("change") or "").strip()[:300],
                })
                identity = (character.casefold(), evidence["start"])
                match = lambda row: (str(row.get("character") or "").casefold(), row.get("evidence", {}).get("start"))
            else:
                name_a = str(raw_item.get("character_a") or "").strip()[:120]
                name_b = str(raw_item.get("character_b") or "").strip()[:120]
                if not name_a or not name_b or name_a.casefold() == name_b.casefold():
                    continue
                known = {
                    str(row.get("name") or "").casefold()
                    for row in out.get("characters", []) if isinstance(row, dict)
                }
                visible = source_text.casefold()
                if not all(name.casefold() in visible or name.casefold() in known for name in (name_a, name_b)):
                    continue
                item.update({
                    "character_a": name_a,
                    "character_b": name_b,
                    "dynamic": str(raw_item.get("dynamic") or "").strip()[:360],
                })
                identity = (
                    min(name_a.casefold(), name_b.casefold()),
                    max(name_a.casefold(), name_b.casefold()),
                    evidence["start"],
                )
                match = lambda row: (
                    min(str(row.get("character_a") or "").casefold(), str(row.get("character_b") or "").casefold()),
                    max(str(row.get("character_a") or "").casefold(), str(row.get("character_b") or "").casefold()),
                    row.get("evidence", {}).get("start"),
                )
            if not any(match(existing) == identity for existing in target if isinstance(existing, dict)):
                if len(target) < 100:
                    target.append(item)

    merge_evidence_rows("themes", 4, 0.60)
    merge_evidence_rows("emotional_beats", 5, 0.55)
    merge_evidence_rows("key_events", 6, 0.60)
    merge_evidence_rows("character_observations", 8, 0.60)
    merge_evidence_rows("relationships", 4, 0.60)

    for raw in _safe_list(data.get("dialogue"), 24):
        if not isinstance(raw, dict):
            continue
        quote = str(raw.get("quote") or "").strip()
        if not quote or quote.casefold() in seen:
            continue
        item = dict(raw)
        item["confidence"] = _numeric_score(item.get("confidence", 0.0))
        out.setdefault("dialogue", []).append(item)
        seen.add(quote.casefold())

    existing_pron = {
        str(item.get("written") or "").casefold()
        for item in out.setdefault("pronunciation", [])
        if isinstance(item, dict)
    }
    for raw in _safe_list(data.get("pronunciation"), 16):
        if not isinstance(raw, dict):
            continue
        written = str(raw.get("written") or raw.get("text") or "").strip()
        spoken = str(raw.get("spoken") or raw.get("pronunciation") or "").strip()
        if not written or not spoken or written.casefold() not in source_text.casefold():
            continue
        if spoken.casefold() == written.casefold() and not raw.get("ipa"):
            continue
        confidence = _numeric_score(raw.get("confidence", 0.0))
        if confidence < 0.80 or written.casefold() in existing_pron:
            continue
        known_names = set()
        for character in out.get("characters", []):
            if not isinstance(character, dict):
                continue
            primary = str(character.get("name") or "").strip()
            if primary:
                known_names.add(primary)
            aliases = character.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(aliases, (list, tuple)):
                known_names.update(str(alias).strip() for alias in aliases if str(alias or "").strip())
        language = str(raw.get("source_language") or "unknown").strip()
        script = str(raw.get("script") or "Latin").strip()
        # Do not trust the model's language label on its own. A common English
        # word does not become a pronunciation target just because it is tagged
        # Japanese/Korean. Keep verified cast names and genuine native-script
        # terms; require unrecognized Latin terms to look like plausible names.
        if not is_likely_character_name_candidate(
            written, known_names=known_names, script=script
        ):
            continue
        item = dict(raw)
        item.update({
            "written": written,
            "spoken": spoken,
            "confidence": confidence,
            "ipa": raw.get("ipa") or None,
            "source_language": raw.get("source_language") or None,
            "script": raw.get("script") or "Latin",
            "alternatives": raw.get("alternatives") if isinstance(raw.get("alternatives"), list) else [],
        })
        out["pronunciation"].append(item)
        existing_pron.add(written.casefold())

    for raw in _safe_list(data.get("scenes"), 8):
        if not isinstance(raw, dict):
            continue
        direction = raw.get("narrator_direction") if isinstance(raw.get("narrator_direction"), dict) else {}
        out.setdefault("scenes", []).append({
            "summary": str(raw.get("summary") or "").strip(),
            "location": str(raw.get("location") or "").strip(),
            "time": str(raw.get("time") or "").strip(),
            "mood": str(raw.get("mood") or "neutral").strip() or "neutral",
            "narrator_direction": {
                "pace": str(raw.get("pace") or direction.get("pace") or "natural").strip() or "natural",
                "energy": str(raw.get("energy") or direction.get("energy") or "medium").strip() or "medium",
                "delivery": str(raw.get("delivery") or direction.get("delivery") or "").strip(),
            },
            "ambience": [str(x).strip() for x in _safe_list(raw.get("ambience"), 3) if str(x).strip()],
            "music": {"style": str(raw.get("music_style") or "").strip() or None, "intensity": _numeric_score(raw.get("music_intensity", 0.0))},
            "sfx": [str(x).strip() for x in _safe_list(raw.get("sfx"), 4) if str(x).strip()],
            "confidence": _numeric_score(raw.get("confidence", 0.0)),
        })

    for raw in _safe_list(data.get("continuity_notes"), 16):
        if isinstance(raw, (str, int, float)):
            note = str(raw).strip()
            if note and note not in out.setdefault("continuity_notes", []):
                out["continuity_notes"].append(note)


def _safe_merge_scenes(self, out: dict, data: Any) -> None:
    if not isinstance(data, dict):
        return
    for raw in _safe_list(data.get("scenes"), 8):
        if not isinstance(raw, dict):
            continue
        direction = raw.get("narrator_direction")
        direction = direction if isinstance(direction, dict) else {}
        nested_music = raw.get("music")
        nested_music = nested_music if isinstance(nested_music, dict) else {}

        pace = direction.get("pace") or raw.get("pace") or "natural"
        energy = direction.get("energy") or raw.get("energy") or "medium"
        delivery = direction.get("delivery") or raw.get("delivery") or ""
        music_style = nested_music.get("style") or raw.get("music_style") or ""
        music_intensity = (
            nested_music.get("intensity")
            if nested_music.get("intensity") is not None
            else raw.get("music_intensity", 0.0)
        )
        ambience = [
            str(value).strip()
            for value in _safe_list(raw.get("ambience"), 3)
            if str(value).strip()
        ]
        sfx = [
            str(value).strip()
            for value in _safe_list(raw.get("sfx"), 4)
            if str(value).strip()
        ]
        out.setdefault("scenes", []).append({
            "summary": str(raw.get("summary") or "").strip(),
            "location": str(raw.get("location") or "").strip(),
            "time": str(raw.get("time") or "").strip(),
            "mood": str(raw.get("mood") or "neutral").strip() or "neutral",
            "narrator_direction": {
                "pace": str(pace).strip() or "natural",
                "energy": str(energy).strip() or "medium",
                "delivery": str(delivery).strip(),
            },
            "ambience": ambience,
            "music": {
                "style": str(music_style).strip() or None,
                "intensity": _numeric_score(music_intensity),
            },
            "sfx": sfx,
            "confidence": _numeric_score(raw.get("confidence", 0.0)),
        })


_original_analyze_chapter = AudiobookBrain.analyze_chapter


def _fallback_pronunciations(text: str, result: dict) -> None:
    """Add conservative readings only for names already found by character analysis."""
    existing = {
        str(item.get("written") or "").casefold()
        for item in result.get("pronunciation", [])
        if isinstance(item, dict)
    }
    character_names = []
    for row in result.get("characters", []) or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            character_names.append(name)

    for name in dict.fromkeys(character_names):
        key = name.casefold()
        if key in existing or key not in text.casefold():
            continue
        if not is_likely_character_name_candidate(name, known_names=character_names):
            continue
        # Prevent a misspelled/fabricated model label from creating a rule even
        # when it happened to be emitted in the character list.
        if not _is_plausible_name(name):
            continue
        spoken = suggest_pronunciation(name)
        if not spoken or spoken.casefold() == key:
            continue
        result.setdefault("pronunciation", []).append({
            "written": name,
            "spoken": spoken,
            "ipa": None,
            "source_language": "heuristic",
            "script": "Latin",
            "reason": "Pronunciation draft for a detected character; review before saving.",
            "confidence": 0.86,
            "alternatives": [],
        })
        existing.add(key)
        if len(existing) >= 24:
            break


def _safe_analyze_chapter(self, chapter, book_context=None, progress=None):
    text = (getattr(chapter, "text", "") or "").strip()
    if not text:
        result = {
            "chapter": chapter.number,
            "title": chapter.title,
            "characters": [], "dialogue": [], "scenes": [], "pronunciation": [], "continuity_notes": [],
            "warnings": [f"Chapter {chapter.number} has no body text; AI analysis skipped."],
        }
        self._save_chapter(result)
        return result
    try:
        result = _original_analyze_chapter(self, chapter, book_context, progress)
    except Exception as exc:
        result = self._fallback_core(chapter)
        result.update({
            "chapter": chapter.number,
            "title": chapter.title,
            "scenes": [], "pronunciation": [], "continuity_notes": [],
            "warnings": [f"AI analysis recovered with deterministic fallback: {exc}"],
        })
    _fallback_pronunciations(text, result)
    segments = result.pop("chapter_summary_segments", [])
    if segments and not result.get("chapter_summary"):
        result["chapter_summary"] = " ".join(dict.fromkeys(
            str(value).strip() for value in segments if str(value).strip()
        ))[:2400]
    purpose_rows = result.pop("chapter_purpose_observations", [])
    if purpose_rows:
        best = max(purpose_rows, key=lambda row: float(row.get("confidence") or 0.0))
        result["chapter_purpose"] = str(best.get("purpose") or "")
        result["chapter_purpose_evidence"] = best.get("evidence")
    self._save_chapter(result)
    return result


AudiobookBrain._merge = _safe_merge
AudiobookBrain._merge_scenes = _safe_merge_scenes
AudiobookBrain.analyze_chapter = _safe_analyze_chapter
