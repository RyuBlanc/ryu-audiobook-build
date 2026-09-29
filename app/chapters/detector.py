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

    valid_markers: list[tuple[int, str]] = []
    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if position == 0:
            preamble = "\n".join(lines[:start]).strip()
            if preamble:
                body = f"{preamble}\n\n{body}".strip()
        if body:
            valid_markers.append((start, title))

    if not valid_markers:
        return [Chapter(1, "Full Book", text.strip())] if text.strip() else []

    chapters: list[Chapter] = []
    preamble = "\n".join(lines[: valid_markers[0][0]]).strip()

    for position, (start, title) in enumerate(valid_markers):
        end = valid_markers[position + 1][0] if position + 1 < len(valid_markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            continue
        chapters.append(Chapter(len(chapters) + 1, title, body))

    return chapters


def _heading_title(line: str) -> str | None:
    if re.search(r"(?:https?://|www\.|mp4directs\.com)", line, re.I):
        return None

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
