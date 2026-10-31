"""Source-position-based classification of narration and character dialogue."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.chapters.assignment_utils import assignment_speakers
from app.chapters.characters import _all_dialogue_spans
from app.chapters.detector import Chapter


NARRATOR_ROLE = "Narrator"
NARRATOR_KEY = NARRATOR_ROLE.casefold()


@dataclass(frozen=True)
class SpeakerSegment:
    chapter_number: int
    kind: str
    speaker: str | None
    speakers: tuple[str, ...]
    start: int
    end: int
    text: str
    source: str
    needs_review: bool = False


@dataclass(frozen=True)
class _SourceBlock:
    start: int
    end: int
    speakers: tuple[str, ...] = ()
    source: str = ""
    is_assignment: bool = False


def _dialogue_source_spans(text: str) -> list[tuple[int, int]]:
    """Return complete quote/dash dialogue spans without losing source offsets."""
    spans = {(int(start), int(end)) for start, end, _raw in _all_dialogue_spans(text)}
    # Smart single quotation marks are common in English light novels. Do not
    # include ordinary apostrophes in contractions or possessives as dialogue.
    for match in re.finditer(r"‘[^’\r\n]{2,}’", text):
        spans.add((match.start(), match.end()))
    # Straight single quotes are accepted only as a paired, standalone quote
    # with whitespace or punctuation around them, avoiding contractions.
    for match in re.finditer(r"(?<![\w])'([^'\r\n]{2,})'(?![\w])", text):
        spans.add((match.start(), match.end()))
    return sorted(spans, key=lambda item: (item[0], -(item[1] - item[0])))


def _valid_assignment_blocks(chapter: Chapter) -> list[_SourceBlock]:
    source = str(chapter.text or "")
    output: list[_SourceBlock] = []
    for item in getattr(chapter, "dialogue_assignments", []) or []:
        if not isinstance(item, dict):
            continue
        raw_start, raw_end = item.get("start"), item.get("end")
        if isinstance(raw_start, bool) or isinstance(raw_end, bool):
            continue
        try:
            start, end = int(raw_start), int(raw_end)
        except (TypeError, ValueError, OverflowError):
            continue
        if start < 0 or end <= start or end > len(source):
            continue
        exact = source[start:end]
        if not exact.strip() or (item.get("text") is not None and str(item.get("text")) != exact):
            continue
        speakers = tuple(dict.fromkeys(
            name for name in assignment_speakers(item) if name.strip()
        ))
        if not speakers:
            continue
        normalized_source = str(item.get("source") or "manual").strip().casefold()
        if normalized_source not in {"ai", "manual"}:
            normalized_source = "manual"
        output.append(_SourceBlock(start, end, speakers, normalized_source, True))
    return output


def _merge_dialogue_blocks(blocks: list[_SourceBlock]) -> list[tuple[int, int, tuple[str, ...], str, str, bool]]:
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda item: (item.start, -item.end))
    groups: list[list[_SourceBlock]] = []
    current: list[_SourceBlock] = []
    current_end = -1
    for block in ordered:
        if current and block.start >= current_end:
            groups.append(current)
            current = []
            current_end = -1
        current.append(block)
        current_end = max(current_end, block.end)
    if current:
        groups.append(current)

    results = []
    for group in groups:
        start = min(block.start for block in group)
        end = max(block.end for block in group)
        assignments = [block for block in group if block.is_assignment]
        speaker_sets = {tuple(sorted(name.casefold() for name in block.speakers)) for block in assignments}
        speakers = tuple(dict.fromkeys(name for block in assignments for name in block.speakers))
        if len(speaker_sets) > 1:
            kind, source, needs_review = "needs_speaker_review", "conflicting_saved_assignments", True
            speakers = ()
        elif speakers and all(name.casefold() == NARRATOR_KEY for name in speakers):
            kind, source, needs_review = "narration", assignments[0].source, False
        elif speakers:
            kind, source, needs_review = "character_dialogue", assignments[0].source, False
        else:
            kind, source, needs_review = "needs_speaker_review", "quoted_or_dash_dialogue", True
        results.append((start, end, speakers, kind, source, needs_review))
    return results


def _narration_gaps(text: str, start: int, end: int, chapter_number: int) -> list[SpeakerSegment]:
    """Split non-dialogue gaps into paragraph-sized, exact source passages."""
    fragment = text[start:end]
    results: list[SpeakerSegment] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=(?:\r?\n[ \t]*\r?\n)|\Z)", fragment, flags=re.S):
        local_start, local_end = match.span()
        absolute_start, absolute_end = start + local_start, start + local_end
        if absolute_end <= absolute_start:
            continue
        exact = text[absolute_start:absolute_end]
        if not exact.strip():
            continue
        results.append(SpeakerSegment(
            chapter_number=chapter_number, kind="narration",
            speaker=NARRATOR_ROLE, speakers=(NARRATOR_ROLE,),
            start=absolute_start, end=absolute_end, text=exact,
            source="automatic_non_dialogue", needs_review=False,
        ))
    return results


def segment_chapter_speakers(chapter: Chapter) -> list[SpeakerSegment]:
    """Classify a chapter into narrator, assigned character and review passages.

    Saved manual/AI spans take precedence over heuristic quote detection. Any
    detected dialogue without a saved character assignment is routed to review,
    never to Narrator. Every remaining non-whitespace source passage is Narrator.
    """
    text = str(getattr(chapter, "text", "") or "")
    chapter_number = int(getattr(chapter, "number", 0) or 0)
    if not text:
        return []

    blocks = [
        _SourceBlock(start, end)
        for start, end in _dialogue_source_spans(text)
        if 0 <= start < end <= len(text)
    ]
    blocks.extend(_valid_assignment_blocks(chapter))
    dialogue_segments = _merge_dialogue_blocks(blocks)

    output: list[SpeakerSegment] = []
    cursor = 0
    for start, end, speakers, kind, source, needs_review in dialogue_segments:
        if start > cursor:
            output.extend(_narration_gaps(text, cursor, start, chapter_number))
        exact = text[start:end]
        speaker = (
            NARRATOR_ROLE if kind == "narration" else
            (" + ".join(speakers) if speakers else None)
        )
        output.append(SpeakerSegment(
            chapter_number=chapter_number, kind=kind, speaker=speaker,
            speakers=speakers, start=start, end=end, text=exact,
            source=source, needs_review=needs_review,
        ))
        cursor = max(cursor, end)
    if cursor < len(text):
        output.extend(_narration_gaps(text, cursor, len(text), chapter_number))
    return sorted(output, key=lambda item: (item.start, item.end, item.kind))


def segment_project_speakers(chapters: list[Chapter]) -> list[SpeakerSegment]:
    """Return source-backed speaker segments for every chapter in reading order."""
    return [
        segment
        for chapter in chapters
        for segment in segment_chapter_speakers(chapter)
    ]
