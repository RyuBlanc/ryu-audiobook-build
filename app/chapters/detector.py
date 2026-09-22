from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class Chapter:
    number: int
    title: str
    text: str


CHAPTER_PATTERNS = [
    # Explicit chapter/part headings.
    re.compile(r"^\s*(chapter|chap\.)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(r"^\s*(part)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(
        r"^\s*(prologue|epilogue|foreword|preface|introduction|afterword)\s*$",
        re.I,
    ),
    # Common numbered headings such as "1. FLAP" or "12 - The Beginning".
    re.compile(r"^\s*(\d{1,4})\s*[.)-]\s+(.{1,90})\s*$"),
]


def detect_chapters(text: str) -> list[Chapter]:
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

    chapters: list[Chapter] = []

    # Never discard text before the first detected heading. If there is
    # meaningful pre-heading material, keep it with the first chapter.
    preamble = "\n".join(lines[: markers[0][0]]).strip()

    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()

        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()

        chapters.append(Chapter(len(chapters) + 1, title, body))

    return chapters


def _heading_title(line: str) -> str | None:
    for pattern in CHAPTER_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue

        if pattern is CHAPTER_PATTERNS[0]:
            number = match.group(2)
            suffix = match.group(3).strip()
            return f"{match.group(1).title()} {number}" + (f" - {suffix}" if suffix else "")

        if pattern is CHAPTER_PATTERNS[1]:
            number = match.group(2)
            suffix = match.group(3).strip()
            return f"Part {number}" + (f" - {suffix}" if suffix else "")

        if pattern is CHAPTER_PATTERNS[2]:
            return match.group(1).title()

        # Numbered heading.
        return line

    return None
