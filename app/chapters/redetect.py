"""Safe chapter re-detection over the user's current saved text.

This operation never reparses the original import and silently overwrites editor changes.
It only commits a new segmentation if every proposed chapter body maps to an exact,
ordered substring of the current saved text. Structural metadata is then reconciled
against those source spans; assignments whose offsets no longer safely map are dropped.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Iterable

from app.chapters.detector import Chapter, detect_chapters


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _first_nonempty_line(value: str) -> str:
    return next((line.strip() for line in str(value or "").splitlines() if line.strip()), "")


def redetect_chapters_preserving_edits(
    existing_chapters: Iterable[Chapter],
) -> tuple[list[Chapter], dict[str, int | bool]]:
    """Re-detect current chapter text without changing or silently losing its contents.

    Chapter boundaries and editor whitespace may be reorganized, but all non-whitespace
    source characters must be represented by exact chapter-text substrings in source order.
    A candidate that normalizes a heading, strips likely noise or otherwise changes text is
    rejected atomically. Manual titles on unchanged chapters are kept, review status is
    retained only for exact one-to-one chapter matches, excluded source spans stay excluded,
    and source-backed dialogue offsets are remapped by absolute source position.
    """
    previous = list(existing_chapters or [])
    if not previous:
        raise ValueError("Open a project with at least one chapter before re-detecting boundaries.")

    parts: list[str] = []
    old_ranges: list[tuple[int, int, Chapter]] = []
    cursor = 0
    for index, chapter in enumerate(previous):
        text = str(getattr(chapter, "text", "") or "")
        if not text.strip():
            raise ValueError(
                "Re-detection was stopped because a chapter is empty. Fill it or remove it first; "
                "no chapter text or metadata was changed."
            )
        if index:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(text)
        cursor += len(text)
        old_ranges.append((start, cursor, chapter))

    source_text = "".join(parts)
    if len(source_text) > 50_000_000:
        raise ValueError(
            "This book is too large to re-detect safely in one operation (50 million characters). "
            "No changes were saved."
        )

    detected = detect_chapters(source_text)
    if not detected:
        raise ValueError("No readable chapter text was detected. The saved project was left unchanged.")
    if (
        len(previous) > 1
        and len(detected) == 1
        and str(detected[0].title or "").strip().casefold() == "full book"
    ):
        raise ValueError(
            "No recognizable chapter headings were found. Re-detection would collapse your manual "
            "chapter boundaries, so nothing was changed."
        )

    proposed_ranges: list[tuple[int, int, Chapter]] = []
    source_cursor = 0
    for chapter in detected:
        candidate_text = str(getattr(chapter, "text", "") or "")
        if not candidate_text.strip():
            continue
        start = source_text.find(candidate_text, source_cursor)
        if start < 0:
            raise ValueError(
                "Re-detection was stopped because chapter detection would rewrite or remove saved text "
                "(for example, an unusual heading or page-noise line). No changes were saved."
            )
        if source_text[source_cursor:start].strip():
            raise ValueError(
                "Re-detection could not map every saved passage to a new chapter boundary. "
                "No changes were saved."
            )
        end = start + len(candidate_text)
        proposed_ranges.append((start, end, chapter))
        source_cursor = end
    if source_text[source_cursor:].strip():
        raise ValueError(
            "Re-detection would leave saved text outside the detected chapters. No changes were saved."
        )
    if not proposed_ranges:
        raise ValueError("No non-empty chapters were detected. The saved project was left unchanged.")

    total_assignments = sum(len(getattr(old, "dialogue_assignments", []) or []) for old in previous)
    preserved_assignments = 0
    result_chapters: list[Chapter] = []
    result_ranges: list[tuple[int, int, Chapter, Chapter | None]] = []
    review_reset_count = 0

    for number, (start, end, candidate) in enumerate(proposed_ranges, 1):
        candidate_text = str(candidate.text or "")
        exact_old = next(
            (
                old for old_start, old_end, old in old_ranges
                if old_start == start and old_end == end and str(old.text or "") == candidate_text
            ),
            None,
        )
        if exact_old is not None:
            title = str(exact_old.title or candidate.title)
            review_status = str(getattr(exact_old, "review_status", "needs_review") or "needs_review")
            review_status = review_status if review_status in {"needs_review", "reviewed"} else "needs_review"
        else:
            title = str(candidate.title or "Chapter " + str(number))
            review_status = "needs_review"
        if not title.strip():
            title = str(candidate.title or "Chapter " + str(number))

        # If a previously excluded passage becomes part of a different detected chapter,
        # conservatively keep that whole new chapter excluded rather than re-enable it.
        remains_skipped = any(
            bool(getattr(old, "skip_for_generation", False)) and start < old_end and end > old_start
            for old_start, old_end, old in old_ranges
        )
        item = Chapter(
            number=number,
            title=title[:500],
            text=candidate_text,
            dialogue_assignments=[],
            review_status=review_status,
            skip_for_generation=remains_skipped,
        )
        if exact_old is None:
            review_reset_count += 1
        result_chapters.append(item)
        result_ranges.append((start, end, item, exact_old))

    for old_start, _old_end, old in old_ranges:
        old_text = str(old.text or "")
        raw_assignments = list(getattr(old, "dialogue_assignments", []) or [])
        for assignment in raw_assignments:
            if not isinstance(assignment, dict):
                continue
            raw_start, raw_end = assignment.get("start"), assignment.get("end")
            if (
                isinstance(raw_start, bool) or isinstance(raw_end, bool)
                or not isinstance(raw_start, int) or not isinstance(raw_end, int)
                or raw_start < 0 or raw_end <= raw_start or raw_end > len(old_text)
            ):
                continue
            exact_text = str(assignment.get("text") or "")
            if not exact_text or old_text[raw_start:raw_end] != exact_text:
                continue
            absolute_start, absolute_end = old_start + raw_start, old_start + raw_end
            target = next(
                (
                    (start, end, chapter) for start, end, chapter, _exact_old in result_ranges
                    if start <= absolute_start and absolute_end <= end
                ),
                None,
            )
            if target is None:
                continue
            target_start, _target_end, target_chapter = target
            local_start, local_end = absolute_start - target_start, absolute_end - target_start
            if target_chapter.text[local_start:local_end] != exact_text:
                continue
            copied = deepcopy(assignment)
            copied.update({"start": local_start, "end": local_end, "text": exact_text})
            target_chapter.dialogue_assignments.append(copied)
            preserved_assignments += 1

    for chapter in result_chapters:
        chapter.dialogue_assignments.sort(
            key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0)))
        )

    return result_chapters, {
        "old_chapter_count": len(previous),
        "new_chapter_count": len(result_chapters),
        "review_reset_count": review_reset_count,
        "skipped_chapter_count": sum(bool(ch.skip_for_generation) for ch in result_chapters),
        "preserved_dialogue_assignment_count": preserved_assignments,
        "dropped_dialogue_assignment_count": max(0, total_assignments - preserved_assignments),
        "source_character_count": len(source_text),
        "text_preserved": True,
    }
