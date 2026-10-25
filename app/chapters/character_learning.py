"""Local, series-scoped feedback memory for dialogue-speaker analysis.

This is a transparent, deterministic learning layer: explicitly confirmed speaker
assignments become examples that improve later rankings. It does not train or
download a model, and it never saves an unconfirmed AI guess as ground truth.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from app.core.paths import settings_root
from app.chapters.characters import _is_plausible_name

_STORE_VERSION = 1
_MAX_TOTAL_EXAMPLES = 8000
_MAX_EXAMPLES_PER_SPEAKER_SERIES = 160
_SPEECH_VERBS = (
    "said|asked|replied|answered|shouted|yelled|whispered|muttered|called|cried|"
    "exclaimed|continued|added|insisted|wondered|demanded|begged|groaned|sighed|"
    "laughed|snapped|stammered|murmured|screamed|announced|explained|remarked|"
    "responded|mumbled|roared|stated|inquired|ordered|reassured|interrupted"
)
_TAG_VERBS = re.compile(r"\b(?:" + _SPEECH_VERBS + r")\b", re.IGNORECASE)
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_CONTEXT_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "at",
    "by", "for", "from", "with", "about", "into", "is", "was", "were", "be",
    "been", "being", "it", "its", "he", "she", "they", "them", "his", "her",
    "their", "i", "we", "you", "me", "my", "our", "your", "this", "that",
    "these", "those", "as", "if", "not", "no", "yes", "then", "when", "what",
    "who", "which", "how", "why", "there", "here", "just", "very", "really",
}


def _store_path(path: Path | None = None) -> Path:
    return path or (settings_root() / "character_learning.json")


def _load_store(path: Path | None = None) -> dict[str, Any]:
    target = _store_path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"version": _STORE_VERSION, "examples": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("examples"), list):
        return {"version": _STORE_VERSION, "examples": []}
    return {
        "version": _STORE_VERSION,
        "examples": [dict(row) for row in raw["examples"] if isinstance(row, dict)],
    }


def _write_store(store: dict[str, Any], path: Path | None = None) -> None:
    target = _store_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".character-learning-", suffix=".tmp", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(target)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise


def _normalize(value: str) -> str:
    value = str(value or "").casefold()
    return " ".join(_WORDS.findall(value))


def _context_tokens(value: str) -> set[str]:
    return {
        word for word in _WORDS.findall(str(value or "").casefold())
        if len(word) > 1 and word not in _CONTEXT_STOPWORDS
    }


def _similarity(left: str, right: str) -> float:
    a, b = _context_tokens(left), _context_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _series_key(value: str) -> str:
    return re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", str(value or "").strip()).casefold()


def load_learning_examples(series: str, path: Path | None = None) -> list[dict[str, Any]]:
    """Load only examples from the requested series; unrelated books stay isolated."""
    wanted = _series_key(series)
    if not wanted:
        return []
    rows = [
        row for row in _load_store(path)["examples"]
        if _series_key(str(row.get("series") or "")) == wanted
    ]
    return rows


def record_assignment_feedback(
    *,
    series: str,
    speaker: str,
    aliases: list[str] | tuple[str, ...] = (),
    chapter_text: str,
    start: int,
    end: int,
    source_text: str,
    chapter_title: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    """Store an explicitly saved/confirmed source passage as positive feedback."""
    series_name = str(series or "").strip()
    speaker_name = str(speaker or "").strip()
    source = str(chapter_text or "")
    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Learning feedback requires exact source offsets.") from exc
    if not series_name or not speaker_name:
        raise ValueError("Learning feedback needs a series and confirmed speaker.")
    if start < 0 or end <= start or end > len(source):
        raise ValueError("Learning feedback offsets are outside the saved chapter text.")
    exact = source[start:end]
    if exact != str(source_text or ""):
        raise ValueError("Learning feedback source text no longer matches the saved chapter.")
    if not _is_plausible_name(speaker_name):
        raise ValueError("The confirmed speaker name is not a plausible character label.")

    before = source[max(0, start - 420):start]
    after = source[end:min(len(source), end + 420)]
    context = before + "\n<SELECTED_DIALOGUE>\n" + exact + "\n</SELECTED_DIALOGUE>\n" + after
    normalized_dialogue = _normalize(exact)
    context_signature = _normalize(before[-260:]) + "|" + normalized_dialogue + "|" + _normalize(after[:260])
    feedback_key = hashlib.sha256(
        (_series_key(series_name) + "\0" + context_signature).encode("utf-8")
    ).hexdigest()
    alias_list = list(dict.fromkeys(
        str(value).strip() for value in aliases
        if str(value or "").strip() and str(value).strip().casefold() != speaker_name.casefold()
    ))[:12]
    row = {
        "feedback_key": feedback_key,
        "series": series_name[:300],
        "speaker": speaker_name[:160],
        "aliases": alias_list,
        "dialogue_text": exact[:5000],
        "normalized_dialogue": normalized_dialogue[:5000],
        "before_context": before[-420:],
        "after_context": after[:420],
        "context": context[-1400:],
        "chapter_title": str(chapter_title or "")[:300],
        "source": "explicit-user-confirmation",
        "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    store = _load_store(path)
    examples = store["examples"]
    # Reassigning the same source/context is a correction: replace its previous
    # label rather than teaching contradictory speakers for an identical event.
    examples = [old for old in examples if str(old.get("feedback_key") or "") != feedback_key]
    examples.append(row)
    # Bound growth while keeping the most recently confirmed examples per cast.
    per_series_speaker: dict[str, list[int]] = {}
    for index, item in enumerate(examples):
        key = _series_key(str(item.get("series") or "")) + "\0" + str(item.get("speaker") or "").casefold()
        per_series_speaker.setdefault(key, []).append(index)
    remove_indexes: set[int] = set()
    for indexes in per_series_speaker.values():
        if len(indexes) > _MAX_EXAMPLES_PER_SPEAKER_SERIES:
            remove_indexes.update(indexes[:-_MAX_EXAMPLES_PER_SPEAKER_SERIES])
    if len(examples) > _MAX_TOTAL_EXAMPLES:
        remove_indexes.update(range(max(0, len(examples) - _MAX_TOTAL_EXAMPLES)))
    store["examples"] = [item for index, item in enumerate(examples) if index not in remove_indexes]
    _write_store(store, path)
    return {"saved": True, "series": series_name, "speaker": speaker_name, "examples_for_series": len(load_learning_examples(series_name, path))}


def remove_assignment_feedback(
    *, series: str, chapter_text: str, start: int, end: int, source_text: str,
    path: Path | None = None,
) -> dict[str, Any]:
    """Remove the exact feedback row when a saved assignment is explicitly undone."""
    source = str(chapter_text or "")
    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Learning feedback removal needs exact source offsets.") from exc
    if start < 0 or end <= start or end > len(source) or source[start:end] != str(source_text or ""):
        raise ValueError("Learning feedback removal did not match the saved source passage.")
    before = source[max(0, start - 420):start]
    after = source[end:min(len(source), end + 420)]
    context_signature = _normalize(before[-260:]) + "|" + _normalize(source[start:end]) + "|" + _normalize(after[:260])
    feedback_key = hashlib.sha256(
        (_series_key(series) + "\0" + context_signature).encode("utf-8")
    ).hexdigest()
    store = _load_store(path)
    previous = len(store["examples"])
    store["examples"] = [row for row in store["examples"] if str(row.get("feedback_key") or "") != feedback_key]
    removed = previous - len(store["examples"])
    if removed:
        _write_store(store, path)
    return {"removed": bool(removed), "count": removed}


def rank_speaker_suggestions(
    *,
    chapter_text: str,
    start: int,
    end: int,
    detected: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    known_characters: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    learning_examples: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    last_speaker: str = "",
) -> list[dict[str, Any]]:
    """Rank known or explicitly evidenced speakers using rules and user feedback.

    Ordinary capitalized prose words are not admitted as new characters simply
    because they begin a sentence. Unknown names require a plausible name and a
    concrete speaker-tag pattern. Existing saved cast names and their aliases
    remain candidates, and confirmed examples raise relevant candidates' scores.
    """
    source = str(chapter_text or "")
    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError, OverflowError):
        return []
    if start < 0 or end <= start or end > len(source):
        return []
    dialogue = source[start:end]
    before = source[max(0, start - 500):start]
    after = source[end:min(len(source), end + 500)]
    nearby = before + "\n" + dialogue + "\n" + after
    speech_verb = r"(?:" + _SPEECH_VERBS + r")"
    candidate_map: dict[str, dict[str, Any]] = {}

    def add_candidate(name: str, aliases: list[str] | tuple[str, ...] = (), base_score: float = 0.0, evidence: str = "") -> None:
        canonical = str(name or "").strip()
        if not canonical or not _is_plausible_name(canonical):
            return
        key = canonical.casefold()
        item = candidate_map.get(key)
        if item is None:
            item = {"name": canonical, "aliases": [], "score": 0.0, "evidence": ""}
            candidate_map[key] = item
        item["aliases"] = list(dict.fromkeys([
            *item["aliases"],
            *(str(alias).strip() for alias in aliases if str(alias or "").strip())
        ]))
        if base_score > float(item["score"]):
            item["score"] = min(1.0, max(0.0, float(base_score)))
            item["evidence"] = str(evidence or "")

    known_names: set[str] = set()
    for row in known_characters:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("primary_name") or "").strip()
        if not name:
            continue
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = list(aliases) if isinstance(aliases, (list, tuple)) else []
        known_names.add(name.casefold())
        known_names.update(str(alias).strip().casefold() for alias in aliases if str(alias or "").strip())
        add_candidate(name, aliases, 0.10, "Saved character in this series.")
    for row in detected:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        evidence = str(row.get("evidence") or "")
        is_known = name.casefold() in known_names
        escaped = "|".join(re.escape(value) for value in sorted(
            {name, *(alias for cast in known_characters if isinstance(cast, dict)
                       and str(cast.get("name") or cast.get("primary_name") or "").casefold() == name.casefold()
                       for alias in (cast.get("aliases") or []) if isinstance(cast.get("aliases") or [], (list, tuple)))},
            key=len, reverse=True
        ))
        explicit_tag = bool(escaped) and bool(
            re.search(r"(?i)(?:" + escaped + r")\s*(?:,\s*)?" + speech_verb + r"\b", before + "\n" + after)
            or re.search(r"(?i)" + speech_verb + r"\s+(?:" + escaped + r")\b", before + "\n" + after)
            or re.search(r"(?m)^\s*(?:" + escaped + r")\s*[:：—–-]\s*$", before)
        ) if name else False
        # Non-library names are accepted only with a speech attribution marker.
        if not is_known and not explicit_tag:
            continue
        score = float(row.get("confidence") or 0.0)
        if score > 1.0:
            score /= 100.0
        add_candidate(name, (), max(0.52 if explicit_tag else 0.0, score * (1.0 if explicit_tag else 0.78)),
                      evidence if is_known else (evidence or "Explicit speech attribution in source text."))

    # Score direct attribution on either side of a quote. This is stronger than
    # generic proximity or a guess based on sentence-initial capitalization.
    for item in candidate_map.values():
        names = [item["name"], *item["aliases"]]
        escaped = "|".join(re.escape(name) for name in sorted(set(names), key=len, reverse=True))
        direct = bool(
            re.search(r"(?i)(?:" + escaped + r")\s*(?:,\s*)?" + speech_verb + r"\b", before[-300:])
            or re.search(r"(?i)" + speech_verb + r"\s+(?:" + escaped + r")\b", before[-300:])
            or re.search(r"(?i)(?:" + escaped + r")\s*(?:,\s*)?" + speech_verb + r"\b", after[:300])
            or re.search(r"(?i)" + speech_verb + r"\s+(?:" + escaped + r")\b", after[:300])
            or re.search(r"(?m)^\s*(?:" + escaped + r")\s*[:：—–-]\s*$", before[-180:])
        )
        if direct:
            item["score"] = max(float(item["score"]), 0.97)
            item["evidence"] = "Explicit character name and speech tag found next to this passage."
            continue
        for example in learning_examples:
            if not isinstance(example, dict) or str(example.get("speaker") or "").casefold() != item["name"].casefold():
                continue
            learned_dialogue = str(example.get("normalized_dialogue") or _normalize(str(example.get("dialogue_text") or "")))
            dialogue_match = learned_dialogue and learned_dialogue == _normalize(dialogue)
            learned_context = str(example.get("context") or "")
            similarity = _similarity(nearby, learned_context)
            if dialogue_match and similarity >= 0.25:
                score = 0.67 + min(0.30, similarity * 0.30)
                if score > float(item["score"]):
                    item["score"] = score
                    item["evidence"] = f"Matches a confirmed example for {item['name']} (context similarity {similarity:.0%})."
            elif similarity >= 0.48:
                score = 0.58 + min(0.30, (similarity - 0.48) * 0.58)
                if score > float(item["score"]):
                    item["score"] = score
                    item["evidence"] = f"Similar to a confirmed series example for {item['name']} (context similarity {similarity:.0%})."
        if not item["evidence"] and item["score"] <= 0.10:
            item["evidence"] = "Saved character; no strong local speech evidence yet."

    last = str(last_speaker or "").strip()
    pronoun_continuity = bool(re.match(r"(?is)^\s*[,;:—–-]?\s*(?:he|she|they|I)\s+(?:" + _SPEECH_VERBS + r")\b", after[:180]))
    if last and pronoun_continuity:
        for item in candidate_map.values():
            if item["name"].casefold() == last.casefold() or last.casefold() in {value.casefold() for value in item["aliases"]}:
                if float(item["score"]) < 0.74:
                    item["score"] = 0.74
                    item["evidence"] = "Pronoun speech tag continues the previously confirmed speaker."

    rows = [
        {"name": str(item["name"]), "confidence": round(float(item["score"]), 4),
         "evidence": str(item["evidence"])}
        for item in candidate_map.values() if float(item["score"]) >= 0.52
    ]
    rows.sort(key=lambda row: (-float(row["confidence"]), str(row["name"]).casefold()))
    return rows[:5]
