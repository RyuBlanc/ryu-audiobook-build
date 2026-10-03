from __future__ import annotations

from dataclasses import dataclass
import re

from app.chapters.characters import (
    analyze_chapter,
    _all_dialogue_spans,
    _clean_dialogue,
    _speaker_near_quote,
    _discover_candidates,
    _is_plausible_name,
)
from app.chapters.detector import Chapter


@dataclass(frozen=True)
class DialogueSegment:
    index: int
    text: str
    start: int
    end: int
    suggested_speaker: str | None
    confidence: float
    suggestions: tuple[tuple[str, float, str], ...] = ()


def dialogue_segment_for_selection(
    chapter: Chapter,
    start: int,
    end: int,
) -> DialogueSegment | None:
    """Return a fast, local speaker suggestion for one selected dialogue.

    The chapter editor previously ran the full chapter character analysis every
    time the Assign Dialogue dialog opened. Large chapters could therefore take
    several seconds before the dialog even appeared. Assignment needs only the
    selected dialogue and nearby evidence, so keep this path deliberately
    local and cheap. Existing manual assignments remain the strongest signal.
    """
    text = chapter.text or ""
    start = max(0, min(int(start), len(text)))
    end = max(start, min(int(end), len(text)))
    if end <= start:
        return None

    spans = _all_dialogue_spans(text)
    overlaps = [
        (span_start, span_end, raw)
        for span_start, span_end, raw in spans
        if span_start < end and start < span_end
    ]
    if not overlaps:
        return None

    def overlap_ratio(span: tuple[int, int, str]) -> float:
        span_start, span_end, _raw = span
        overlap = max(0, min(end, span_end) - max(start, span_start))
        selected_len = max(1, end - start)
        span_len = max(1, span_end - span_start)
        return max(overlap / selected_len, overlap / span_len)

    overlaps.sort(key=overlap_ratio, reverse=True)
    best_start, best_end, raw = overlaps[0]
    if len(overlaps) > 1 and overlap_ratio(overlaps[0]) < 0.90:
        return DialogueSegment(1, _clean_dialogue(raw), best_start, best_end, None, 0.0, ())

    manual_items = list(getattr(chapter, "dialogue_assignments", []))
    manual_speakers = [
        str(item.get("speaker", "")).strip()
        for item in manual_items
        if str(item.get("speaker", "")).strip()
    ]

    exact_manual = next(
        (
            item for item in manual_items
            if int(item.get("start", -1)) == best_start
            and int(item.get("end", -1)) == best_end
            and str(item.get("speaker", "")).strip()
        ),
        None,
    )

    # A narrow local window is enough to find nearby names without running the
    # full chapter-wide character detector used by the AI analysis screen.
    local_before_start = max(0, best_start - 1800)
    local_after_end = min(len(text), best_end + 1200)
    local_window = text[local_before_start:local_after_end]
    discovered = {
        name for name in _discover_candidates(local_window)
        if _is_plausible_name(name)
    }
    candidates = list(dict.fromkeys(manual_speakers + sorted(discovered)))

    last_speaker = None
    previous_manual = [
        item for item in manual_items
        if int(item.get("end", -1)) <= best_start
        and str(item.get("speaker", "")).strip()
    ]
    if previous_manual:
        previous_manual.sort(key=lambda item: int(item.get("end", -1)))
        last_speaker = str(previous_manual[-1].get("speaker", "")).strip() or None

    before = text[max(0, best_start - 700):best_start]
    after = text[best_end:min(len(text), best_end + 500)]
    speaker, confidence = _speaker_near_quote(
        text, best_start, best_end, candidates, None, last_speaker
    )
    aliases: dict[str, str] = {}
    suggestions = _rank_suggestions(
        chapter,
        best_start,
        best_end,
        before,
        after,
        candidates,
        aliases,
        last_speaker,
    )

    if exact_manual is not None:
        exact_name = str(exact_manual.get("speaker", "")).strip()
        suggestions = [
            (exact_name, 1.0, "Saved manual assignment for this exact dialogue."),
            *[
                item for item in suggestions
                if item[0].casefold() != exact_name.casefold()
            ],
        ]
        speaker, confidence = exact_name, 1.0
    elif suggestions:
        top_name, top_confidence, _ = suggestions[0]
        if confidence <= 0 or top_confidence > confidence:
            speaker, confidence = top_name, top_confidence

    return DialogueSegment(
        1,
        _clean_dialogue(raw),
        best_start,
        best_end,
        speaker,
        confidence,
        tuple(suggestions[:5]),
    )


def dialogue_segments(chapter: Chapter) -> list[DialogueSegment]:
    """Return dialogue spans with ranked, evidence-backed speaker suggestions."""
    analysis = analyze_chapter(chapter)
    manual_speakers = [
        str(item.get("speaker", "")).strip()
        for item in getattr(chapter, "dialogue_assignments", [])
        if str(item.get("speaker", "")).strip()
    ]

    discovered = {
        name for name in _discover_candidates(chapter.text or "")
        if _is_plausible_name(name)
    }
    candidates = list(dict.fromkeys(
        [c.name for c in analysis.characters] + manual_speakers + sorted(discovered)
    ))
    aliases = {
        alias.casefold(): c.name
        for c in analysis.characters
        for alias in c.aliases
    }

    text = chapter.text or ""
    spans = _all_dialogue_spans(text)
    result: list[DialogueSegment] = []
    last_speaker: str | None = None

    for number, (start, end, raw) in enumerate(spans, 1):
        before = text[max(0, start - 700):start]
        after = text[end:min(len(text), end + 500)]
        speaker, confidence = _speaker_near_quote(
            text, start, end, candidates, analysis.narrator.name, last_speaker
        )
        suggestions = _rank_suggestions(
            chapter, start, end, before, after, candidates, aliases, last_speaker
        )
        if suggestions:
            top_name, top_confidence, _ = suggestions[0]
            if confidence <= 0 or top_confidence > confidence:
                speaker, confidence = top_name, top_confidence

        result.append(
            DialogueSegment(
                number,
                _clean_dialogue(raw),
                start,
                end,
                speaker,
                confidence,
                tuple(suggestions),
            )
        )
        if speaker and confidence >= 0.78:
            last_speaker = speaker

    return result


def _rank_suggestions(
    chapter: Chapter,
    start: int,
    end: int,
    before: str,
    after: str,
    candidates: list[str],
    aliases: dict[str, str],
    last_speaker: str | None,
) -> list[tuple[str, float, str]]:
    """Rank only evidence-backed candidates; never invent a random character."""
    scores: dict[str, tuple[float, str]] = {}

    def add(name: str, score: float, evidence: str) -> None:
        current = scores.get(name)
        if current is None or score > current[0]:
            scores[name] = (score, evidence)

    for item in getattr(chapter, "dialogue_assignments", []):
        try:
            a_start = int(item.get("start", -1))
            a_end = int(item.get("end", -1))
        except (TypeError, ValueError):
            continue
        if a_start == start and a_end == end:
            name = str(item.get("speaker", "")).strip()
            if name:
                add(name, 1.0, "Saved manual assignment for this exact dialogue.")
        elif a_start <= start < a_end or start <= a_start < end:
            name = str(item.get("speaker", "")).strip()
            if name:
                add(name, 0.94, "Overlapping saved manual assignment.")

    verbs = r"said|asked|replied|answered|shouted|yelled|whispered|muttered|called|cried|exclaimed|added|insisted|wondered|demanded|begged|sighed|snapped|murmured|screamed|explained|remarked|responded|mumbled|stammered|laughed|groaned"

    for name in candidates:
        escaped = re.escape(name)
        alias_variants = [
            re.escape(alias)
            for alias, canonical in aliases.items()
            if canonical.casefold() == name.casefold()
        ]
        name_pattern = "(?:" + "|".join([escaped] + alias_variants) + ")"

        if re.search(rf"{name_pattern}\s+(?:{verbs})\b", after, re.I):
            add(name, 0.99, "Matched a speaker name + speech verb after the dialogue.")
        if re.search(rf"(?:{verbs})\s+{name_pattern}\b", after, re.I):
            add(name, 0.98, "Matched a speech verb + speaker name after the dialogue.")
        if re.search(rf"{name_pattern}\s+(?:{verbs})\b\s*$", before, re.I | re.S):
            add(name, 0.99, "Matched a speaker name + speech verb before the dialogue.")
        if re.search(rf"(?:{verbs})\s+{name_pattern}\s*$", before, re.I | re.S):
            add(name, 0.98, "Matched a speech verb + speaker name before the dialogue.")
        if re.search(rf"{name_pattern}\s*[:—–-]\s*$", before, re.I | re.S):
            add(name, 0.95, "Matched a speaker label immediately before the dialogue.")
        if re.search(rf"(?m)^\s*{name_pattern}\s*[:—–-]?\s*$", before[-260:], re.I):
            add(name, 0.94, "Matched a speaker label on the preceding line.")
        if re.search(rf"[”\"」』]\s*,?\s*{name_pattern}\s+(?:{verbs})\b", after, re.I):
            add(name, 0.97, "Matched a post-dialogue speaker tag.")

    if last_speaker and re.search(
        rf"^\s*[,;:—–-]?\s*(?:he|she|they|I)\s+(?:{verbs})\b", after, re.I
    ):
        add(last_speaker, 0.66, "Pronoun speech tag continues the previous speaker.")

    nearby_text = before[-280:] + "\n" + after[:280]
    for name in candidates:
        count = len(re.findall(rf"\b{re.escape(name)}\b", nearby_text, re.I))
        if count and name not in scores:
            add(
                name,
                min(0.54, 0.32 + 0.08 * count),
                "Character name appears near the dialogue.",
            )

    ranked = sorted(
        ((name, score, evidence) for name, (score, evidence) in scores.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )
    return ranked[:5]


def infer_speaker_for_quote(
    text: str,
    start: int,
    end: int,
    speaker_names: list[str],
    narrator_name: str | None = None,
    last_speaker: str | None = None,
) -> str | None:
    speaker, _ = _speaker_near_quote(
        text, start, end, speaker_names, narrator_name, last_speaker
    )
    return speaker


def _find_name(text: str, candidates: list[str], aliases: dict[str, str]) -> str | None:
    folded = text.casefold()
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate.casefold() in folded:
            return candidate
    for alias, canonical in sorted(
        aliases.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if alias in folded:
            return canonical
    return None
