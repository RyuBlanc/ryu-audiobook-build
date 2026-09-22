from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass
class Chapter:
    number: int
    title: str
    text: str

CHAPTER_PATTERNS = [
    re.compile(r"^\s*(chapter|chap\.)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(r"^\s*(part)\s+([0-9IVXLCDM]+)(?:\s*[-:–—.]\s*)?(.*)$", re.I),
    re.compile(r"^\s*(prologue|epilogue|foreword|preface|introduction|afterword)\s*$", re.I),
]

def detect_chapters(text: str) -> list[Chapter]:
    lines = text.splitlines()
    markers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate:
            continue
        if _looks_like_heading(candidate):
            markers.append((index, candidate))

    if not markers:
        return [Chapter(1, "Full Book", text.strip())] if text.strip() else []

    chapters: list[Chapter] = []
    for position, (start, title) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        chapters.append(Chapter(len(chapters) + 1, title, body))

    return chapters

def _looks_like_heading(line: str) -> bool:
    for pattern in CHAPTER_PATTERNS:
        if pattern.match(line):
            return True
    if len(line) <= 90 and line.upper() == line and re.search(r"[A-Z]", line):
        return True
    return False
