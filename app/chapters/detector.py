from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class Chapter:
    number: int
    title: str
    text: str


EXPLICIT_PATTERNS = [
    re.compile(r"^\s*(chapter|chap\.)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(r"^\s*(part)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(
        r"^\s*(prologue|epilogue|foreword|preface|introduction|afterword|interlude|"
        r"side story|extra|bonus)\s*(.*)$",
        re.I,
    ),
]

# Flexible title forms such as:
#   1. The Beginning
#   2 - The Beginning
#   Life.0
#   Volume 2
#   Side Story 1
NUMBERED_PATTERN = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s+(.{1,120})\s*$")
TITLE_WITH_NUMBER_PATTERN = re.compile(
    r"^(?=.{2,80}$)(?=.*\d)[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9 ._'’:&/()\[\]–—-]*$"
)


def detect_chapters(text: str) -> list[Chapter]:
    """Detect likely chapter headings without throwing away ordinary story text.

    Detection is intentionally conservative. A heading is removed from the
    chapter body only when it matches a strong heading pattern. Unusual titles
    can always be marked manually in the Chapter Editor.
    """
    lines = text.splitlines()
    markers: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate:
            continue
        heading = _heading_title(candidate, lines, index)
        if heading is not None:
            markers.append((index, heading))

    if not markers:
        return [Chapter(1, "Full Book", text.strip())] if text.strip() else []

    chapters: list[Chapter] = []
    preamble = "\n".join(lines[: markers[0][0]]).strip()

    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()

        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()

        chapters.append(Chapter(len(chapters) + 1, title, body))

    return chapters


def _heading_title(line: str, lines: list[str], index: int) -> str | None:
    for pattern in EXPLICIT_PATTERNS:
        match = pattern.match(line)
        if match:
            if match.lastindex and match.lastindex >= 2:
                number = match.group(2)
                suffix = (match.group(3) or "").strip()
                if pattern is EXPLICIT_PATTERNS[0]:
                    return f"Chapter {number}" + (f" - {suffix}" if suffix else "")
                if pattern is EXPLICIT_PATTERNS[1]:
                    return f"Part {number}" + (f" - {suffix}" if suffix else "")
                return match.group(1).title() + (f" - {suffix}" if suffix else "")
            return line

    match = NUMBERED_PATTERN.match(line)
    if match:
        return line

    # Titles such as "Life.0" are valid chapter names even though they do not
    # use the word Chapter. Require a digit and title-like characters so normal
    # dialogue such as "FLAP" or "DON!" is not promoted to a chapter.
    if TITLE_WITH_NUMBER_PATTERN.match(line):
        return line

    return None
