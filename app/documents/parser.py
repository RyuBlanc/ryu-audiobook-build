from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class ExtractedBook:
    title: str
    source_path: Path
    text: str


SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".epub", ".docx"}

# Standalone ebook download/page watermarks. These patterns are intentionally
# narrow so normal URLs or story text are not deleted.
NOISE_PATTERNS = (
    re.compile(r"^https?://(?:www\.)?mp4directs\.com(?:/.*)?$", re.I),
    re.compile(r"^(?:www\.)?mp4directs\.com(?:/.*)?$", re.I),
    re.compile(r"^Goldenagato\s*\|\s*mp4directs\.com\s*$", re.I),
    re.compile(r"^Page\s+\d+\s*$", re.I),
    re.compile(r"^Page\s+\d+\s+.*mp4directs\.com.*$", re.I),
)

BOOK_NOISE_PATTERNS = (
    re.compile(r"^(?:report|read\s+online|download)$", re.I),
    re.compile(r"^\d{1,5}$"),
    re.compile(r"^page\s+\d{1,5}$", re.I),
    re.compile(r"^(?:www\.)?[^\s]+\.(?:com|net|org|cc|me)(?:/.*)?$", re.I),
    re.compile(r"^.*(?:asianovel\.com|mp4directs\.com).*$", re.I),
)

CHAPTER_HEADING_PATTERNS = (
    re.compile(r"^\s*(?:chapter|chap\.)\s+[0-9IVXLCDM]+(?:\s*[-:–—.]\s*)?.*$", re.I),
    re.compile(r"^\s*(?:prologue|epilogue|foreword|preface|introduction|afterword|interlude|side\s+story|extra|bonus)\b.*$", re.I),
    re.compile(r"^\s*[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ _'’&/-]{0,35}\.\d{1,4}\s+.*$", re.I),
    re.compile(r"^\s*Life\s*[0-9IVXLCDM]+(?:\s+.*)?$", re.I),
    re.compile(r"^\s*New\s+Life(?:\s*[:–—-].*)?$", re.I),
)

def _is_chapter_heading_like(line: str) -> bool:
    candidate = re.sub(r"\s+", " ", line).strip()
    if not candidate or len(candidate) > 120:
        return False
    return any(pattern.fullmatch(candidate) for pattern in CHAPTER_HEADING_PATTERNS)


def reflow_source_text(text: str) -> str:
    """Rejoin obvious PDF line wraps while preserving real paragraph/dialogue breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", text)
    output = []

    for paragraph in paragraphs:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in paragraph.split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            continue

        rebuilt: list[str] = [lines[0]]
        for line in lines[1:]:
            previous = rebuilt[-1]
            intentional_break = (
                previous.endswith((".", "!", "?", "…", ":", ";"))
                and (
                    line.startswith(("“", '"', "‘", "'", "—", "–", "-", "•", "*"))
                    or _is_chapter_heading_like(line)
                )
            )
            if _is_chapter_heading_like(previous) or _is_chapter_heading_like(line):
                intentional_break = True
            if intentional_break:
                rebuilt.append(line)
                continue

            if previous.endswith("-") and line and line[0].islower():
                rebuilt[-1] = previous[:-1] + line
                continue

            previous_terminal = bool(re.search(r"[.!?…][\"'”’»)]*$", previous))
            next_starts_sentence = bool(re.match(r"^[A-ZÀ-ÖØ-Þ0-9]", line))
            if not previous_terminal or not next_starts_sentence:
                rebuilt[-1] = f"{previous} {line}".strip()
            else:
                rebuilt.append(line)

        output.append("\n".join(rebuilt).strip())

    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(output)).strip()


def detect_repeated_book_noise(chapter_texts: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for text in chapter_texts:
        seen_in_chapter: set[str] = set()
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            normalized = line.casefold()
            if any(pattern.fullmatch(line) for pattern in BOOK_NOISE_PATTERNS):
                if normalized not in seen_in_chapter:
                    counts[normalized] = counts.get(normalized, 0) + 1
                    seen_in_chapter.add(normalized)
    return {line: count for line, count in counts.items() if count >= 2}


def clean_import_noise(text: str, repeated_noise: set[str] | None = None) -> tuple[str, list[str]]:
    repeated_noise = {str(item).casefold() for item in (repeated_noise or set())}
    removed: list[str] = []
    kept: list[str] = []
    obvious_noise = (
        re.compile(r"^https?://", re.I),
        re.compile(r"^(?:www\.)?[^\s]+\.(?:com|net|org|cc|me)(?:/.*)?$", re.I),
        re.compile(r"^.*(?:asianovel\.com|mp4directs\.com).*$", re.I),
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        normalized = re.sub(r"\s+", " ", line).casefold()
        is_noise = (
            normalized in repeated_noise
            or any(pattern.fullmatch(line) for pattern in obvious_noise)
        )
        if is_noise and line:
            removed.append(line)
            continue
        kept.append(raw_line)
    return reflow_source_text("\n".join(kept)), removed


def extract_text(path: Path) -> ExtractedBook:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported book format: {suffix or 'unknown'}")
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".epub":
        text = _extract_epub(path)
    else:
        text = _extract_docx(path)
    return ExtractedBook(title=path.stem, source_path=path, text=clean_text(text))


def _extract_pdf(path: Path) -> str:
    import fitz

    pages = []
    with fitz.open(path) as document:
        for page in document:
            pages.append(page.get_text("text"))
    return "\n\n".join(pages)


def _extract_epub(path: Path) -> str:
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub(str(path))
    parts = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _extract_docx(path: Path) -> str:
    from docx import Document

    document = Document(path)
    return "\n\n".join(p.text for p in document.paragraphs if p.text.strip())


def remove_page_noise(text: str) -> str:
    kept = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if any(pattern.fullmatch(line) for pattern in NOISE_PATTERNS):
            continue
        # Some PDF extractors keep the page number and watermark on one line.
        if re.fullmatch(r"Page\s+\d+\s+.*mp4directs\.com.*", line, re.I):
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = remove_page_noise(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return reflow_source_text(text).strip()
