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


def prepare_learning_index(
    examples: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index feedback once by normalized (series, canonical speaker) for fast ranking.

    A book can contain thousands of quotations and a series can accumulate thousands
    of confirmed examples. Scanning the entire memory for every candidate on every
    quotation made analysis cost grow as quotations × cast × all saved examples.
    The index keeps ranking local to the selected speaker and series.
    """
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in examples:
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker") or "").strip().casefold()
        if not speaker:
            continue
        key = (_series_key(str(row.get("series") or "")), speaker)
        index.setdefault(key, []).append(row)
    return index


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


def rename_speaker_feedback(
    *, series: str, old_speaker: str, new_speaker: str, path: Path | None = None,
) -> dict[str, Any]:
    """Move confirmed feedback to a renamed character while retaining the old name as an alias."""
    series_name = str(series or "").strip()
    old_name = str(old_speaker or "").strip()
    new_name = str(new_speaker or "").strip()
    if not series_name or not old_name or not new_name:
        raise ValueError("Learning feedback rename needs a series and both character names.")
    if old_name.casefold() == new_name.casefold():
        return {"renamed": False, "count": 0}

    store = _load_store(path)
    renamed = 0
    for row in store["examples"]:
        if _series_key(str(row.get("series") or "")) != _series_key(series_name):
            continue
        if str(row.get("speaker") or "").strip().casefold() != old_name.casefold():
            continue
        row["speaker"] = new_name[:160]
        aliases = [
            str(value).strip() for value in (row.get("aliases") or [])
            if str(value or "").strip()
            and str(value).strip().casefold() not in {old_name.casefold(), new_name.casefold()}
        ]
        aliases.insert(0, old_name[:160])
        row["aliases"] = list(dict.fromkeys(aliases))[:12]
        renamed += 1
    if renamed:
        _write_store(store, path)
    return {"renamed": bool(renamed), "count": renamed, "series": series_name}


def source_grounded_speaker_for_continuity(
    suggestions: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> str:
    """Return a continuity anchor only for an explicit name + speech-tag source match.

    A high confidence score based on remembered examples is not enough to make a
    new speaker the next line's pronoun anchor. Otherwise one mistaken guess can
    cascade across many later dialogue lines.
    """
    if not suggestions:
        return ""
    best = suggestions[0]
    if not isinstance(best, dict):
        return ""
    evidence = str(best.get("evidence") or "").strip()
    name = str(best.get("name") or "").strip()
    if evidence != "Explicit character name and speech tag found next to this passage.":
        return ""
    return name if _is_plausible_name(name) else ""


def rank_speaker_suggestions(
    *,
    chapter_text: str,
    start: int,
    end: int,
    detected: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    known_characters: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    learning_examples: list[dict[str, Any]] | tuple[dict[str, Any], ...] | dict[tuple[str, str], list[dict[str, Any]]] = (),
    last_speaker: str = "",
    last_speaker_series: str = "",
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
    learning_index = (
        learning_examples if isinstance(learning_examples, dict)
        else prepare_learning_index(learning_examples)
    )
    speech_verb = r"(?:" + _SPEECH_VERBS + r")"
    candidate_map: dict[str, dict[str, Any]] = {}

    def add_candidate(
        name: str,
        aliases: list[str] | tuple[str, ...] = (),
        base_score: float = 0.0,
        evidence: str = "",
        series: str = "",
    ) -> None:
        canonical = str(name or "").strip()
        if not canonical or not _is_plausible_name(canonical):
            return
        series_name = re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", str(series or "").strip())[:300]
        key = canonical.casefold() + "\0" + _series_key(series_name)
        item = candidate_map.get(key)
        if item is None:
            item = {"name": canonical, "series": series_name, "aliases": [], "score": 0.0, "evidence": ""}
            candidate_map[key] = item
        item["aliases"] = list(dict.fromkeys([
            *item["aliases"],
            *(str(alias).strip() for alias in aliases if str(alias or "").strip())
        ]))
        if base_score > float(item["score"]):
            item["score"] = min(1.0, max(0.0, float(base_score)))
            item["evidence"] = str(evidence or "")

    known_names: set[str] = set()
    canonical_by_name: dict[str, tuple[str, list[str], str]] = {}
    for row in known_characters:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("primary_name") or "").strip()
        if not name:
            continue
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = list(dict.fromkeys(
            str(alias).strip() for alias in aliases
            if str(alias or "").strip() and str(alias).strip().casefold() != name.casefold()
        )) if isinstance(aliases, (list, tuple)) else []
        series = str(row.get("series") or "").strip()
        if not series:
            scope = str(row.get("scope") or "").strip()
            series = re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", scope).strip() if re.match(r"(?i)^\s*series\s*[·:-]", scope) else scope
        known_names.add(name.casefold())
        # A canonical name may be reused in a different series. Preserve the
        # first project-scoped match instead of allowing a later library row to
        # silently rebind a detected alias to another series.
        canonical_by_name.setdefault(name.casefold(), (name, aliases, series))
        for alias in aliases:
            known_names.add(alias.casefold())
            canonical_by_name.setdefault(alias.casefold(), (name, aliases, series))
        add_candidate(name, aliases, 0.10, "Saved character in this series.", series)

    for row in detected:
        if not isinstance(row, dict):
            continue
        detected_name = str(row.get("name") or "").strip()
        if not detected_name:
            continue
        evidence = str(row.get("evidence") or "")
        matched = canonical_by_name.get(detected_name.casefold())
        canonical_name = matched[0] if matched else detected_name
        canonical_aliases = matched[1] if matched else []
        canonical_series = matched[2] if matched else str(row.get("series") or "")
        is_known = matched is not None or detected_name.casefold() in known_names
        tag_names = list(dict.fromkeys([detected_name, canonical_name, *canonical_aliases]))
        escaped = "|".join(re.escape(value) for value in sorted(tag_names, key=len, reverse=True))
        nearby_context = before + "\n" + after
        explicit_tag = bool(
            re.search(r"(?i)(?:" + escaped + r")\s*(?:,\s*)?" + speech_verb + r"\b", nearby_context)
            or re.search(r"(?i)" + speech_verb + r"\s+(?:" + escaped + r")\b", nearby_context)
            or re.search(r"(?m)^\s*(?:" + escaped + r")\s*[:：—–-]\s*$", before)
        )
        # Unknown detector labels are not accepted merely because they are
        # capitalized. They require a source-grounded speaker tag or saved cast.
        if not is_known and not explicit_tag:
            continue
        score = float(row.get("confidence") or 0.0)
        if score > 1.0:
            score /= 100.0
        add_candidate(
            canonical_name, canonical_aliases,
            max(0.52 if explicit_tag else 0.0, score * (1.0 if explicit_tag else 0.78)),
            evidence if is_known else (evidence or "Explicit speech attribution in source text."),
            canonical_series,
        )

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
        candidate_series = _series_key(str(item.get("series") or ""))
        # Only the same canonical speaker in the same explicit series can teach
        # this candidate. An unscoped candidate must not inherit series feedback.
        matching_examples = learning_index.get(
            (candidate_series, item["name"].casefold()), ()
        )
        for example in matching_examples:
            if not isinstance(example, dict):
                continue
            example_series = _series_key(str(example.get("series") or ""))
            if candidate_series != example_series:
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
    pronoun_continuity = bool(re.match(r"(?is)^\s*[,.;:!?—–-]?\s*(?:he|she|they|I|we)\s+(?:" + _SPEECH_VERBS + r")\b", after[:180]))
    if last and pronoun_continuity:
        last_series_key = _series_key(last_speaker_series)
        for item in candidate_map.values():
            item_series_key = _series_key(str(item.get("series") or ""))
            if last_series_key and item_series_key and item_series_key != last_series_key:
                continue
            if item["name"].casefold() == last.casefold() or last.casefold() in {value.casefold() for value in item["aliases"]}:
                if float(item["score"]) < 0.74:
                    item["score"] = 0.74
                    item["evidence"] = "Pronoun speech tag continues the previously confirmed speaker."

    rows = [
        {"name": str(item["name"]), "series": str(item.get("series") or ""),
         "confidence": round(float(item["score"]), 4), "evidence": str(item["evidence"])}
        for item in candidate_map.values() if float(item["score"]) >= 0.52
    ]
    rows.sort(key=lambda row: (-float(row["confidence"]), str(row["name"]).casefold(), str(row.get("series") or "").casefold()))
    return rows[:5]
