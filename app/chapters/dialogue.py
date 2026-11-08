from __future__ import annotations

from dataclasses import dataclass
import re

from app.chapters.characters import (
    analyze_chapter,
    _all_dialogue_spans,
    _clean_dialogue,
    _speaker_near_quote,
    _discover_candidates,
    _discover_explicit_speakers,
    _is_plausible_name,
)
from app.chapters.detector import Chapter
from app.chapters.assignment_utils import assignment_speakers


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
    project_folder=None,
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
            if int(item.get("start", -1)) == start
            and int(item.get("end", -1)) == end
            and str(item.get("speaker", "")).strip()
        ),
        None,
    )
    if exact_manual is not None:
        exact_name = str(exact_manual.get("speaker", "")).strip()
        selected_raw = text[start:end]
        return DialogueSegment(
            1,
            _clean_dialogue(selected_raw),
            start,
            end,
            exact_name,
            1.0,
            ((exact_name, 1.0, "Saved manual assignment for this exact selection."),),
        )

    # A narrow local window is enough to find nearby names without running the
    # full chapter-wide character detector used by the AI analysis screen.
    local_before_start = max(0, best_start - 1800)
    local_after_end = min(len(text), best_end + 1200)
    local_window = text[local_before_start:local_after_end]
    discovered_names = _discover_candidates(local_window)
    discovered_names.update(_discover_explicit_speakers(local_window))
    discovered = {
        name for name in discovered_names
        if _is_plausible_name(name)
    }
    learned_examples = []
    learning_scope = ""
    learned_speakers = []
    if project_folder is not None:
        try:
            from app.chapters.character_learning import (
                learning_scope_for_project,
                load_learning_examples,
            )
            learning_scope = learning_scope_for_project(project_folder)
            if learning_scope:
                learned_examples = load_learning_examples(learning_scope)
                learned_speakers = list(dict.fromkeys(
                    str(row.get("speaker") or "").strip()
                    for row in learned_examples
                    if isinstance(row, dict)
                    and str(row.get("speaker") or "").strip()
                ))
        except (OSError, ValueError, TypeError):
            learned_examples = []
            learned_speakers = []
            learning_scope = ""

    candidates = list(dict.fromkeys(
        manual_speakers + sorted(discovered) + learned_speakers
    ))

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

    # Explicitly confirmed series/book-local speaker examples can improve
    # later suggestions. They remain suggestions only: a remembered match is
    # never written back as an assignment until the user confirms it.
    if learning_scope and candidates:
        try:
            from app.chapters.character_learning import rank_speaker_suggestions
            known_characters = [
                {"name": name, "series": learning_scope}
                for name in candidates
            ]
            learned = rank_speaker_suggestions(
                    chapter_text=text,
                    start=best_start,
                    end=best_end,
                    known_characters=known_characters,
                    learning_examples=learned_examples,
                last_speaker=last_speaker or "",
                last_speaker_series=learning_scope,
            )
            combined = {item[0].casefold(): item for item in suggestions}
            for item in learned:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                candidate = (
                    name,
                    max(0.0, min(1.0, float(item.get("confidence") or 0.0))),
                    str(item.get("evidence") or "Matches a confirmed local character example."),
                )
                previous = combined.get(name.casefold())
                if previous is None or candidate[1] > previous[1]:
                    combined[name.casefold()] = candidate
            suggestions = sorted(
                combined.values(),
                key=lambda item: (-item[1], item[0].casefold()),
            )[:5]
        except (OSError, ValueError, TypeError):
            # Learning memory is optional and must never disable ordinary
            # source-grounded dialogue assignment when its local store is unreadable.
            pass

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


def _clean_segment_dialogue(value: str) -> str:
    raw = str(value or "").strip()
    pairs = (("“", "”"), ("\u201c", "\u201d"), ("「", "」"), ("『", "』"),
             ("«", "»"), ("‘", "’"), ("'", "'"), ('"', '"'))
    for opening, closing in pairs:
        if raw.startswith(opening) and raw.endswith(closing) and len(raw) > len(opening) + len(closing):
            raw = raw[len(opening):-len(closing)].strip()
            break
    if raw and raw[0] in {"—", "–", "-"}:
        raw = raw[1:].strip()
    return _clean_dialogue(raw)


def dialogue_segments(chapter: Chapter) -> list[DialogueSegment]:
    """Return Production's exact speaker segments with reviewable suggestions.

    The generation preflight and Character Studio must not independently
    discover dialogue spans. Reuse the canonical source-position segmentation
    so quoted, single-quoted, dash-led and saved/overlapping dialogue spans are
    counted exactly once in both places.
    """
    analysis = analyze_chapter(chapter)
    chapter_text = str(chapter.text or "")
    discovered_names = _discover_candidates(chapter_text)
    discovered_names.update(_discover_explicit_speakers(chapter_text))
    discovered = {
        name for name in discovered_names
        if _is_plausible_name(name)
    }
    saved_speakers = []
    for assignment in getattr(chapter, "dialogue_assignments", []) or []:
        if isinstance(assignment, dict):
            saved_speakers.extend(assignment_speakers(assignment))
    candidates = list(dict.fromkeys(
        [c.name for c in analysis.characters] + saved_speakers + sorted(discovered)
    ))
    aliases = {
        alias.casefold(): c.name
        for c in analysis.characters
        for alias in c.aliases
    }

    from app.chapters.speaker_segmentation import segment_chapter_speakers
    source_segments = [
        row for row in segment_chapter_speakers(chapter)
        if row.kind != "narration" and row.end > row.start
    ]
    result: list[DialogueSegment] = []
    last_speaker: str | None = None
    for number, row in enumerate(source_segments, 1):
        start, end = int(row.start), int(row.end)
        before = chapter_text[max(0, start - 700):start]
        after = chapter_text[end:min(len(chapter_text), end + 500)]
        suggestions = _rank_suggestions(
            chapter, start, end, before, after, candidates, aliases, last_speaker
        )
        speaker = row.speaker if row.kind == "character_dialogue" else None
        confidence = 1.0 if speaker else 0.0
        if suggestions:
            top_name, top_confidence, _evidence = suggestions[0]
            if confidence <= 0 or top_confidence > confidence:
                speaker, confidence = top_name, top_confidence
        result.append(DialogueSegment(
            number,
            _clean_segment_dialogue(row.text),
            start,
            end,
            speaker,
            confidence,
            tuple(suggestions),
        ))
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

    matching_assignments = []
    for item in getattr(chapter, "dialogue_assignments", []):
        if not isinstance(item, dict):
            continue
        try:
            a_start = int(item.get("start", -1))
            a_end = int(item.get("end", -1))
        except (TypeError, ValueError):
            continue
        if a_start == start and a_end == end:
            matching_assignments.append((item, 1.0, "Saved assignment for this exact source passage."))
        elif a_start <= start < a_end or start <= a_start < end:
            matching_assignments.append((item, 0.94, "Overlapping saved assignment."))
    assignment_sets = {
        tuple(sorted(str(name).casefold() for name in assignment_speakers(item)))
        for item, _score, _evidence in matching_assignments
        if assignment_speakers(item)
    }
    # If overlapping records disagree, require review instead of silently
    # selecting whichever legacy/new assignment happened to be iterated first.
    if len(assignment_sets) == 1:
        for item, score, evidence in matching_assignments:
            for name in assignment_speakers(item):
                add(name, score, evidence)


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
