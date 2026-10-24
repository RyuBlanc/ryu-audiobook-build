from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.documents.parser import remove_page_noise
from app.chapters.heading_rules import TOC_HEADING_RE, heading_title as parse_heading_title, is_slash_title_candidate


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
    lines = _combine_split_slash_titles(lines)

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
    opening_is_story = _looks_like_story_preamble(preamble)
    if opening_is_story:
        # An unheaded opening page is real narration, not disposable front matter.
        # Keep it as a first-class chapter so users see/hear it separately.
        chapters.append(Chapter(1, "Opening", preamble))

    # Boundaries are computed from every marker before empty bodies are omitted,
    # so empty headings can never leak into the preceding chapter's body.
    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if position == 0 and preamble and not opening_is_story:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            continue
        # Preserve the source heading in the editable/narrated text as well as
        # in Chapter.title. Users need to hear the actual section being played,
        # especially titles split across page boundaries (for example
        # "BLACK DOG/BIRTH" followed by "Part 1").
        body = f"{title}\n{body}".strip()
        chapters.append(Chapter(len(chapters) + 1, title, body))

    if chapters:
        return chapters
    return [Chapter(1, "Full Book", cleaned_text)] if cleaned_text else []


def _combine_split_slash_titles(lines: list[str]) -> list[str]:
    """Join slash-style book titles and a following Part/Volume label."""
    output: list[str] = []
    index = 0
    section_re = re.compile(
        r"^(?:part|volume|vol\.?|book|arc)\s+"
        r"(?:\d{1,4}|[IVXLCDM]{1,12}|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)$",
        re.I,
    )
    while index < len(lines):
        current = lines[index].strip()
        if current and is_slash_title_candidate(current):
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines):
                section = lines[next_index].strip()
                if section_re.fullmatch(section) and parse_heading_title(section):
                    output.append(f"{current}: {section}")
                    index = next_index + 1
                    continue
        output.append(lines[index])
        index += 1
    return output


def _looks_like_story_preamble(preamble: str) -> bool:
    """Distinguish a substantial unheaded story opening from short front matter."""
    value = str(preamble or "").strip()
    if not value:
        return False
    words = re.findall(r"\b[\w’'-]+\b", value, re.UNICODE)
    if len(words) < 18 or not re.search(r"[.!?…。！？]", value):
        return False
    first_line = next((line.strip().casefold() for line in value.splitlines() if line.strip()), "")
    front_matter = (
        "translator note", "translator's note", "translator’s note",
        "translation note", "author's note", "author’s note", "disclaimer",
        "copyright", "table of contents", "contents", "written by ", "translated by ",
    )
    if first_line.startswith(front_matter):
        return False
    # Metadata-only pages are often short, uppercase or label-like and should
    # remain attached to the first chapter for manual review rather than split.
    if len(value.splitlines()) <= 2 and len(words) < 28 and value.isupper():
        return False
    return True


def _heading_title(line: str, *, allow_slash: bool = False) -> str | None:
    return parse_heading_title(line, allow_slash=allow_slash)


def _heading_key(title: str) -> str:
    value = str(title or "").strip()
    value = re.sub(r"(?:\.{2,}|…+)\s*\d+\s*$", "", value)
    value = re.sub(r"\s{2,}\d+\s*$", "", value)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _toc_entry_title(line: str) -> str | None:
    """Recognize TOC headings with dotted leaders/page numbers."""
    raw = str(line or "").strip()
    if not raw:
        return None
    without_page = re.sub(r"(?:\.{2,}|…+)\s*\d+\s*$", "", raw).strip()
    if without_page != raw:
        title = _heading_title(without_page)
        if title is not None:
            return title
    return _heading_title(raw)


def _remove_toc_when_story_heading_repeats(lines: list[str]) -> list[str]:
    """Drop a TOC block only when a listed heading reappears with story text.

    Requiring a duplicate heading plus a substantive body avoids deleting a
    legitimate mention of 'Contents' or a short front-matter heading.
    """
    toc_indices = [i for i, line in enumerate(lines) if TOC_HEADING_RE.fullmatch(line.strip())]
    for toc_index in toc_indices:
        candidates: list[tuple[int, str]] = []
        for index in range(toc_index + 1, len(lines)):
            title = _toc_entry_title(lines[index])
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
