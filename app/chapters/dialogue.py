from __future__ import annotations

from dataclasses import dataclass
import re

from app.chapters.characters import analyze_chapter, _all_dialogue_spans, _clean_dialogue
from app.chapters.detector import Chapter


@dataclass(frozen=True)
class DialogueSegment:
    index: int
    text: str
    start: int
    end: int
    suggested_speaker: str | None
    confidence: float


def dialogue_segments(chapter: Chapter) -> list[DialogueSegment]:
    """Return selectable dialogue spans with conservative speaker suggestions."""
    analysis = analyze_chapter(chapter)
    candidates = [c.name for c in analysis.characters]
    aliases = {alias.casefold(): c.name for c in analysis.characters for alias in c.aliases}
    text = chapter.text or ""
    spans = _all_dialogue_spans(text)
    result: list[DialogueSegment] = []
    last_speaker: str | None = None
    for number, (start, end, raw) in enumerate(spans, 1):
        before = text[max(0, start - 420):start]
        after = text[end:min(len(text), end + 260)]
        speaker, confidence = _suggest_speaker(before, after, candidates, aliases, last_speaker)
        result.append(DialogueSegment(number, _clean_dialogue(raw), start, end, speaker, confidence))
        if speaker and confidence >= 0.70:
            last_speaker = speaker
    return result


def _suggest_speaker(
    before: str,
    after: str,
    candidates: list[str],
    aliases: dict[str, str],
    last_speaker: str | None,
) -> tuple[str | None, float]:
    verbs = r"said|asked|replied|answered|shouted|yelled|whispered|muttered|called|cried|exclaimed|added|insisted|wondered|demanded|begged|sighed|snapped|murmured|screamed|explained|remarked|responded|mumbled"
    names = sorted(candidates, key=len, reverse=True)
    if names:
        name_re = "|".join(re.escape(n) for n in names)
        for pattern, score in (
            (rf"(?:{name_re})\s+(?:{verbs})\s*$", 0.99),
            (rf"(?:{verbs})\s+(?:{name_re})\s*$", 0.98),
            (rf"(?:{name_re})\s*[:—–-]\s*$", 0.96),
            (rf"[”\"»]\s*,?\s*(?:{verbs})\s+(?:{name_re})\b", 0.98),
        ):
            match = re.search(pattern, before, re.I | re.S)
            if match:
                found = _find_name(match.group(0), candidates, aliases)
                if found:
                    return found, score

    tag = re.search(rf"[,;:—–-]?\s*(?:{verbs})\b\s+(.{{0,80}})$", after, re.I | re.S)
    if tag:
        found = _find_name(tag.group(1), candidates, aliases)
        if found:
            return found, 0.95

    pronoun = re.search(rf"^\s*[,;:—–-]?\s*(he|she|they)\s+(?:{verbs})\b", after, re.I)
    if pronoun and last_speaker:
        return last_speaker, 0.68

    if last_speaker and re.search(r"^\s*[,;:—–-]?\s*(?:he|she|they)\b", after, re.I):
        return last_speaker, 0.60
    return None, 0.0


def _find_name(text: str, candidates: list[str], aliases: dict[str, str]) -> str | None:
    folded = text.casefold()
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate.casefold() in folded:
            return candidate
    for alias, canonical in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in folded:
            return canonical
    return None
