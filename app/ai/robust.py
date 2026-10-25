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


def _safe_merge(self, out: dict, data: Any, seen: set[str], source_text: str = "") -> None:
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
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, (list, tuple)):
            character_names.extend(str(alias).strip() for alias in aliases if str(alias or "").strip())

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
    self._save_chapter(result)
    return result


AudiobookBrain._merge = _safe_merge
AudiobookBrain._merge_scenes = _safe_merge_scenes
AudiobookBrain.analyze_chapter = _safe_analyze_chapter
