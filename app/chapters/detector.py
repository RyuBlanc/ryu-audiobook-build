from __future__ import annotations

from dataclasses import dataclass
import re

from app.documents.parser import remove_page_noise


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

# Deliberately not used for automatic chapter detection. Numbered prose such as
# "1. I even got..." is common in extracted novels and must remain story text.
NUMBERED_PATTERN = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s+(.{1,120})\s*$")
TITLE_WITH_NUMBER_PATTERN = re.compile(
    r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ ._'’:&/()\\[\\]–—-]{0,50}\\.\\d{1,4}(?:\\s+.+)?$"
)


def detect_chapters(text: str) -> list[Chapter]:
    """Detect likely chapter headings without throwing away ordinary story text."""
    text = remove_page_noise(text)
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
    lowered = line.lower()
    if re.search(r"(https?://|www\.)", lowered):
        return None

    for pattern in EXPLICIT_PATTERNS:
        match = pattern.match(line)
        if match:
            suffix = (match.group(3) or "").strip() if match.lastindex and match.lastindex >= 3 else ""
            if _looks_like_body_sentence(line, suffix):
                continue
            # Preserve the original heading instead of reconstructing a title.
            return line.strip()

    if re.match(r"^\s*[IVXLCDM]{1,8}(?:\s+|\s*[-:–—.]\s*).{1,100}$", line, re.I):
        return line

    if TITLE_WITH_NUMBER_PATTERN.match(line):
        return line

    return None




def _looks_like_body_sentence(line: str, suffix: str) -> bool:
    """Reject extracted prose that happens to begin with Chapter/Part."""
    suffix = suffix.strip()
    if len(line) > 90:
        return True

    # A real heading may be long, but a quoted sentence is overwhelmingly
    # likely to be body prose. This specifically prevents extracted light
    # novels such as: Chapter 8 "I even bought new pants. You can't tell..."
    if re.search(r'["“”「」『』]', suffix):
        return True

    # Multiple sentence boundaries are a strong prose signal.
    if len(re.findall(r"[.!?。！？]", suffix)) >= 2:
        return True

    if "," in suffix and len(suffix.split()) >= 7:
        return True
    if re.search(r"[!?]$", suffix):
        return True

    # Normal chapter titles are usually short. Long, sentence-like suffixes
    # should stay in the chapter body instead of becoming a chapter marker.
    if len(suffix.split()) > 14:
        return True

    return False
