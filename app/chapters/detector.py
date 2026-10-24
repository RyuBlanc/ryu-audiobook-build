from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.documents.parser import remove_page_noise
from app.chapters.heading_rules import heading_title as parse_heading_title, is_slash_title_candidate


@dataclass
class Chapter:
    number: int
    title: str
    text: str
    # Stable character/dialogue assignments are kept with the chapter so manual
    # corrections survive reloads and can later feed the narration director.
    dialogue_assignments: list[dict] = field(default_factory=list)
    # Review state is persisted with each chapter; older project JSON defaults to needs_review.
    review_status: str = "needs_review"
    # Explicitly exclude this chapter from audiobook generation while keeping its text.
    skip_for_generation: bool = False


def detect_chapters(text: str) -> list[Chapter]:
    """Detect common light-novel chapter formats without splitting on dialogue.

    Detection uses whole-line heading rules, a duplicate-aware table-of-contents
    guard, and a conservative repeated-title heuristic for slash-style headings.
    It never invents chapter boundaries from ordinary quoted dialogue.
    """
    lines = remove_page_noise(text).splitlines()
    lines = _remove_toc_when_story_heading_repeats(lines)

    slash_heading_indices = _slash_heading_marker_indices(lines)
    markers: list[tuple[int, str]] = []

    for index, raw_line in enumerate(lines):
        candidate = raw_line.strip()
        if not candidate:
            continue
        heading = _heading_title(candidate, allow_slash=index in slash_heading_indices)
        if heading is not None:
            markers.append((index, heading))

    cleaned_text = "\n".join(lines).strip()
    if not markers:
        return [Chapter(1, "Full Book", cleaned_text)] if cleaned_text else []

    chapters: list[Chapter] = []
    preamble = "\n".join(lines[:markers[0][0]]).strip()

    # Boundaries are computed from every marker before empty bodies are omitted,
    # so empty headings can never leak into the preceding chapter's body.
    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            continue
        chapters.append(Chapter(len(chapters) + 1, title, body))

    if chapters:
        return chapters
    return [Chapter(1, "Full Book", cleaned_text)] if cleaned_text else []


def _heading_title(line: str, *, allow_slash: bool = False) -> str | None:
    return parse_heading_title(line, allow_slash=allow_slash)


def _heading_key(title: str) -> str:
    value = str(title or "").strip()
    value = re.sub(r"(?:\.{2,}|…+)\s*\d+\s*$", "", value)
    value = re.sub(r"\s{2,}\d+\s*$", "", value)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _remove_toc_when_story_heading_repeats(lines: list[str]) -> list[str]:
    """Drop a TOC block only when a listed heading reappears with story text.

    Requiring a duplicate heading plus a substantive body avoids deleting a
    legitimate mention of 'Contents' or a short front-matter heading.
    """
    toc_indices = [i for i, line in enumerate(lines) if _TOC_HEADING_RE.fullmatch(line.strip())]
    for toc_index in toc_indices:
        candidates: list[tuple[int, str]] = []
        for index in range(toc_index + 1, len(lines)):
            title = _heading_title(lines[index])
            if title is not None:
                candidates.append((index, title))
        for first_position, (first_index, first_title) in enumerate(candidates):
            first_key = _heading_key(first_title)
            if not first_key:
                continue
            for repeat_index, repeat_title in candidates[first_position + 1:]:
                if _heading_key(repeat_title) != first_key:
                    continue
                next_marker = next(
                    (index for index, _title in candidates if index > repeat_index),
                    len(lines),
                )
                story_lines = [line.strip() for line in lines[repeat_index + 1:next_marker] if line.strip()]
                word_count = sum(len(line.split()) for line in story_lines)
                if word_count >= 12 and len(story_lines) >= 1:
                    return lines[:toc_index] + lines[repeat_index:]
    return lines


def _slash_heading_marker_indices(lines: list[str]) -> set[int]:
    """Accept title-only slash headings only when a repeated heading pattern exists."""
    candidates: list[int] = []
    for index, line in enumerate(lines):
        if not is_slash_title_candidate(line):
            continue
        if index > 0 and lines[index - 1].strip():
            continue
        # A heading needs a real body after it; this excludes a slash phrase
        # embedded in front matter or a bare table-of-contents entry.
        word_count = 0
        for later in lines[index + 1:]:
            if _heading_title(later) is not None or is_slash_title_candidate(later):
                break
            if later.strip():
                word_count += len(later.split())
            if word_count >= 12:
                break
        if word_count >= 12:
            candidates.append(index)
    return set(candidates) if len(candidates) >= 2 else set()
