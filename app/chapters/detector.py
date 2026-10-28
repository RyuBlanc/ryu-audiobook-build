from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.documents.parser import remove_page_noise


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


EXPLICIT_PATTERNS = [
    re.compile(r"^\s*(chapter|chap\.)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(
        r"^\s*(prologue|epilogue|foreword|preface|introduction|afterword|interlude|"
        r"side story|extra|bonus)\s*(.*)$",
        re.I,
    ),
]

TITLE_WITH_NUMBER_PATTERN = re.compile(
    r"^\s*[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ _'’&/-]{0,35}\.(\d{1,4})\s*(.*)$"
)
LIFE_WITH_SPACE_PATTERN = re.compile(
    r"^\s*Life\s+([0-9IVXLCDM]+)\s*(.*)$",
    re.I,
)
NEW_LIFE_PATTERN = re.compile(r"^\s*New\s+Life(?:\s*[:–—-]\s*(.*))?\s*$", re.I)
PART_HEADING_PATTERN = re.compile(
    r"^\s*(?:part|book|volume)\s+(?:\d+|[IVXLCDM]+)(?:\s*[:–—.-]\s*.+)?\s*$",
    re.I,
)
# These are named section titles such as "BLACK DOG/BIRTH". Restrict this
# pattern to full-line uppercase slash-separated headings to avoid treating
# ordinary dialogue or lowercase prose as structural markers.
UPPERCASE_SLASH_SECTION_PATTERN = re.compile(
    r"^[A-Z0-9][A-Z0-9 '&.\-]*(?:\s*/\s*[A-Z0-9][A-Z0-9 '&.\-]*)+$"
)


def detect_chapters(text: str) -> list[Chapter]:
    """Detect chapter markers conservatively without discarding story text."""
    text = remove_page_noise(text)
    lines = text.splitlines()
    markers: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate:
            continue
        heading = _heading_title(candidate)
        if heading is not None:
            markers.append((index, heading))

    if not markers:
        return [Chapter(1, "Full Book", text.strip())] if text.strip() else []

    # Some books format a chapter heading as two adjacent heading lines, for
    # example "BLACK DOG/BIRTH" followed by "Part 1". Treat the pair as one
    # heading, while preserving the line after the final heading as the body.
    # Do not merge unrelated empty headings (for example, an empty Chapter 2
    # followed by Chapter 3), because each detected marker defines a boundary.
    combined_markers: list[tuple[int, str, int]] = []
    position = 0
    while position < len(markers):
        start, title = markers[position]
        last_heading_line = start
        if position + 1 < len(markers):
            next_start, next_title = markers[position + 1]
            blank_gap = not any(
                lines[line_index].strip()
                for line_index in range(start + 1, next_start)
            )
            previous_is_named_section = bool(
                UPPERCASE_SLASH_SECTION_PATTERN.fullmatch(title)
            )
            previous_is_part = bool(PART_HEADING_PATTERN.fullmatch(title))
            next_is_named_section = bool(
                UPPERCASE_SLASH_SECTION_PATTERN.fullmatch(next_title)
            )
            next_is_part = bool(PART_HEADING_PATTERN.fullmatch(next_title))
            if blank_gap and (
                (previous_is_named_section and next_is_part)
                or (previous_is_part and next_is_named_section)
            ):
                # Keep the semantic section name first regardless of source
                # layout, with the part marker as its companion title.
                title = (
                    f"{title} — {next_title}"
                    if previous_is_named_section
                    else f"{next_title} — {title}"
                )
                last_heading_line = next_start
                position += 2
            else:
                position += 1
        else:
            position += 1
        combined_markers.append((start, title, last_heading_line))

    chapters: list[Chapter] = []
    preamble = "\n".join(lines[:combined_markers[0][0]]).strip()

    # Use every detected marker to establish boundaries. Filtering empty
    # chapters before calculating boundaries can accidentally pull an empty
    # chapter heading into the preceding chapter's narration text.
    for position, (start, title, last_heading_line) in enumerate(combined_markers):
        end = combined_markers[position + 1][0] if position + 1 < len(combined_markers) else len(lines)
        body = "\n".join(lines[last_heading_line + 1:end]).strip()
        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            # Empty heading records are omitted, but their boundaries still
            # remain respected so headings never leak into neighboring bodies.
            continue
        chapters.append(Chapter(len(chapters) + 1, title, body))

    if chapters:
        return chapters
    return [Chapter(1, "Full Book", text.strip())] if text.strip() else []


def _heading_title(line: str) -> str | None:
    if re.search(r"(?:https?://|www\.|mp4directs\.com)", line, re.I):
        return None

    if PART_HEADING_PATTERN.fullmatch(line):
        return line
    if len(line) <= 90 and UPPERCASE_SLASH_SECTION_PATTERN.fullmatch(line):
        return line

    for pattern in EXPLICIT_PATTERNS:
        match = pattern.match(line)
        if match:
            suffix = (match.group(match.lastindex) or "").strip() if match.lastindex else ""
            if _looks_like_body_sentence(line, suffix):
                continue
            return line

    match = TITLE_WITH_NUMBER_PATTERN.match(line)
    if match:
        suffix = (match.group(2) or "").strip()
        if not suffix or len(suffix.split()) <= 12:
            return line

    match = LIFE_WITH_SPACE_PATTERN.match(line)
    if match:
        suffix = (match.group(2) or "").strip()
        if len(suffix.split()) <= 12:
            return line

    if NEW_LIFE_PATTERN.match(line):
        return line

    return None


def _looks_like_body_sentence(line: str, suffix: str) -> bool:
    suffix = suffix.strip()
    if len(line) > 90:
        return True
    if re.search(r'["“”「」『』]', suffix):
        return True
    if len(re.findall(r"[.!?。！？]", suffix)) >= 2:
        return True
    if "," in suffix and len(suffix.split()) >= 7:
        return True
    if re.search(r"[!?]$", suffix):
        return True
    if len(suffix.split()) > 14:
        return True
    return False
