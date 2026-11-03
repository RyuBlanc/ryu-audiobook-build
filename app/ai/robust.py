from __future__ import annotations

import re
from typing import Any

from .brain import AudiobookBrain, _numeric_score
from app.tts.pronunciation_suggester import COMMON_ENGLISH_WORDS, suggest_names_from_text, suggest_pronunciation


def _safe_list(value: Any, limit: int = 12) -> list:
    return value[:limit] if isinstance(value, list) else []


def _safe_merge(self, out: dict, data: Any, seen: set[str], source_text: str = "") -> None:
    if not isinstance(data, dict):
        return

    for raw in _safe_list(data.get("characters")):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
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
        words = [w.strip(".,!?;:()[]{}") for w in written.split()]
        ordinary = bool(words) and all(
            re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", w or "") and w.casefold() in COMMON_ENGLISH_WORDS
            for w in words
        )
        language = str(raw.get("source_language") or "").casefold()
        if ordinary and language in {"", "english", "en", "unknown"}:
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
    existing = {
        str(item.get("written") or "").casefold()
        for item in result.get("pronunciation", [])
        if isinstance(item, dict)
    }
    for name in suggest_names_from_text(text):
        key = name.casefold()
        if key in existing or key in COMMON_ENGLISH_WORDS:
            continue
        words = [w.strip(".,!?;:()[]{}") for w in name.split()]
        if not words or all(
            re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", w or "") and w.casefold() in COMMON_ENGLISH_WORDS
            for w in words
        ):
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
            "reason": "Conservative local name-pronunciation heuristic; review before saving.",
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
