from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.tts.pacing import is_heading_line
from app.chapters.heading_rules import (
    CHAPTER_HEADING_PATTERNS, TOC_HEADING_RE,
    heading_title as _heading_title,
    is_chapter_heading_like as _is_chapter_heading_like,
)


@dataclass
class ExtractedBook:
    title: str
    source_path: Path
    text: str


SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".epub", ".docx"}

# Standalone ebook download/page watermarks. A bare "Page 12" is only
# removed if it names a page label from PDF extraction; bare numeric lines are
# handled by the contextual cleanup below rather than at this stage.
NOISE_PATTERNS = (
    re.compile(r"^https?://(?:www\.)?mp4directs\.com(?:/.*)?$", re.I),
    re.compile(r"^(?:www\.)?mp4directs\.com(?:/.*)?$", re.I),
    re.compile(r"^Goldenagato\s*\|\s*mp4directs\.com\s*$", re.I),
    re.compile(r"^Page\s+\d+\s*$", re.I),
    re.compile(r"^Page\s+\d+\s+.*mp4directs\.com.*$", re.I),
    re.compile(r"^https?://(?:www\.)?asianovel\.com(?:/.*)?$", re.I),
    re.compile(r"^(?:www\.)?asianovel\.com(?:/.*)?$", re.I),
    re.compile(r"^https?://(?:www\.)?mp4directs\.com(?:/.*)?$", re.I),
)


BOOK_NOISE_PATTERNS = (
    # These candidates are only considered removable when they appear in at
    # least two chapters. A standalone "Report" or a number can be real story
    # content and must never be removed from a single occurrence by itself.
    re.compile(r"^(?:report|read\s+online|download)$", re.I),
    re.compile(r"^\d{1,5}$"),
    re.compile(r"^page\s+\d{1,5}$", re.I),
    # Known light-novel downloader sites are eligible for repeated-noise
    # removal. A generic domain is not: story text may intentionally mention it.
    re.compile(r"^(?:https?://)?(?:www\.)?(?:asianovel\.com|mp4directs\.com)(?:/.*)?$", re.I),
    re.compile(r"^.*(?:asianovel\.com|mp4directs\.com).*$", re.I),
)

# A conservative, reusable word-coverage check for import previews. Chapter
# bodies can repeat short headings/TOC labels, so compare normalized token
# multisets rather than requiring raw text equality.
def _coverage_heading_key(title: str) -> str:
    value = str(title or "").strip()
    value = re.sub(r"(?:\.{2,}|…+)\s*\d+\s*$", "", value)
    value = re.sub(r"\s{2,}\d+\s*$", "", value)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _toc_entry_title(line: str) -> str | None:
    """Accept headings in a declared TOC when they use dotted leaders/page numbers."""
    raw = str(line or "").strip()
    if not raw:
        return None
    without_page = re.sub(r"(?:\.{2,}|…+)\s*\d+\s*$", "", raw).strip()
    if without_page != raw:
        title = _heading_title(without_page, allow_slash=True)
        if title is not None:
            return title
    return _heading_title(raw, allow_slash=True)


def _coverage_source_lines(source_text: str) -> list[str]:
    """Exclude only a duplicate-aware TOC block that the analyzer also removes."""
    lines = str(source_text or "").splitlines()
    toc_indices = [i for i, line in enumerate(lines) if TOC_HEADING_RE.fullmatch(line.strip())]
    for toc_index in toc_indices:
        candidates: list[tuple[int, str]] = []
        for index in range(toc_index + 1, len(lines)):
            title = _toc_entry_title(lines[index])
            if title is not None:
                candidates.append((index, title))
        for first_position, (first_index, first_title) in enumerate(candidates):
            first_key = _coverage_heading_key(first_title)
            if not first_key:
                continue
            for repeat_index, repeat_title in candidates[first_position + 1:]:
                if _coverage_heading_key(repeat_title) != first_key:
                    continue
                next_marker = next(
                    (index for index, _title in candidates if index > repeat_index),
                    len(lines),
                )
                story_lines = [
                    line.strip() for line in lines[repeat_index + 1:next_marker]
                    if line.strip()
                ]
                if sum(len(line.split()) for line in story_lines) >= 12 and story_lines:
                    return lines[:toc_index] + lines[repeat_index:]
    return lines


def chapter_text_coverage(source_text: str, chapters: list) -> tuple[int, int, float]:
    coverage_source = "\n".join(_coverage_source_lines(source_text))
    source_words = len(re.findall(r"\b[\w’'-]+\b", coverage_source, re.UNICODE))
    chapter_text = "\n".join(str(getattr(chapter, "text", "") or "") for chapter in chapters)
    body_words = len(re.findall(r"\b[\w’'-]+\b", chapter_text, re.UNICODE))
    # The detector deliberately removes heading lines from chapter bodies,
    # but preserves their titles as Chapter.title. Count those titles as
    # retained source text so books with many short chapters are not rejected.
    title_text = "\n".join(str(getattr(chapter, "title", "") or "") for chapter in chapters)
    title_words = len(re.findall(r"\b[\w’'-]+\b", title_text, re.UNICODE))
    chapter_words = body_words + title_words
    coverage = chapter_words / source_words if source_words else (
        1.0 if not (chapter_text or title_text).strip() else 0.0
    )
    return source_words, chapter_words, coverage


def validate_chapter_text_coverage(source_text: str, chapters: list, *, minimum: float = 0.90) -> None:
    """Raise an actionable error when chapter segmentation loses source content.

    This is deliberately a token-coverage guard, not an equality assertion:
    headings are excluded from bodies by design, and TOC/duplicate cleanup may
    legitimately remove text. For short texts it uses the same ratio but does
    not let a zero denominator accidentally pass.
    """
    if not 0.0 <= minimum <= 1.0:
        raise ValueError("minimum coverage must be between 0 and 1")
    source_words, chapter_words, coverage = chapter_text_coverage(source_text, chapters)
    # Short books can legitimately have more of their extracted text in
    # headings/front matter, so guard them by absolute loss too.
    minimum_words = min(20, max(1, int(source_words * minimum))) if source_words else 0
    if source_words and chapter_words < minimum_words:
        raise ValueError(
            f"Chapter detection retained only {chapter_words:,} of {source_words:,} words. "
            "Import was stopped to protect your book from losing content."
        )
    if source_words >= 40 and coverage < minimum:
        raise ValueError(
            f"Chapter detection retained only {chapter_words:,} of {source_words:,} "
            f"source words ({coverage:.0%} coverage). Import was stopped to protect "
            "your book from losing content. Review the heading rules or choose a "
            "different import format."
        )


def _split_adjacent_dialogue(line: str) -> str:
    # Separate back-to-back quoted utterances such as:
    # “...?” “...”
    # "..." "..."
    # This is intentionally conservative; ordinary quoted words inside prose remain intact.
    pattern = re.compile(r'([”’"」』])\s+(?=[“‘"「『])')
    separated = pattern.sub(lambda match: match.group(1) + "\n", line)
    # A few light novels use <<...>> for telepathy, skills, or system messages.
    # Keep adjacent utterances as separate dialogue units instead of reflowing them
    # into one long line.
    return re.sub(r">>\s*(?=<<)", ">>\n", separated)


def reflow_source_text(text: str) -> str:
    """Normalize imported line wrapping without destroying paragraph/dialogue structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", text)
    output = []

    for paragraph in paragraphs:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in paragraph.split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            continue

        rebuilt: list[str] = []
        for raw_line in lines:
            parts = _split_adjacent_dialogue(raw_line).split("\n")
            for part in parts:
                line = part.strip()
                if not line:
                    continue
                if not rebuilt:
                    rebuilt.append(line)
                    continue

                previous = rebuilt[-1]

                # Never join a new dialogue line, heading, list item, or bullet.
                starts_structural = line.startswith(
                    ("“", "‘", '"', "'", "「", "『", "<<", "—", "–", "-", "•", "*")
                )
                structural = (
                    starts_structural
                    or _is_chapter_heading_like(line)
                    or is_heading_line(line)
                )
                previous_is_heading = (
                    _is_chapter_heading_like(previous)
                    or is_heading_line(previous)
                )

                # A chapter heading is always a hard source boundary. Never
                # merge its body line into the heading even when the heading
                # itself does not end with terminal punctuation.

                # Clear PDF-style hard wrap: previous line does not end a
                # sentence, so it is still part of the same sentence.
                if not structural and not previous_is_heading and not re.search(r"[.!?…:;][\"'”’»)]*$", previous):
                    if previous.endswith("-") and line and line[0].islower():
                        rebuilt[-1] = previous[:-1] + line
                    else:
                        rebuilt[-1] = f"{previous} {line}".strip()
                    continue

                # If a new line starts with a quote/dash after a complete
                # thought, keep the dialogue boundary.
                if structural:
                    rebuilt.append(line)
                    continue

                # Two complete prose sentences can remain separate visual
                # lines. This makes speaker assignment and review easier.
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
    repeated_noise = {re.sub(r"\s+", " ", str(item)).strip().casefold() for item in (repeated_noise or set())}
    removed: list[str] = []
    kept: list[str] = []
    lines = text.splitlines()
    page_noise_indices: set[int] = set()

    # A bare page number is considered noise only when adjacent to a known
    # watermark or the site's page label. A URL/domain line is independently
    # removable; this also handles extracted PDF text where columns reflow.
    for idx, raw in enumerate(lines):
        value = raw.strip().casefold()
        if re.fullmatch(r"\d{1,5}", value):
            neighbors = []
            if idx > 0:
                neighbors.append(lines[idx - 1].strip().casefold())
            if idx + 1 < len(lines):
                neighbors.append(lines[idx + 1].strip().casefold())
            if any(
                neighbor == "report"
                or "asianovel.com" in neighbor
                or "mp4directs.com" in neighbor
                for neighbor in neighbors
            ):
                page_noise_indices.add(idx)

    obvious_noise = (
        re.compile(r"^https?://", re.I),
        re.compile(r"^(?:www\.)?[^\s]+\.(?:com|net|org|cc|me)(?:/.*)?$", re.I),
        re.compile(r"^.*(?:asianovel\.com|mp4directs\.com).*$", re.I),
        re.compile(r"^\d{1,5}\s+report$", re.I),
    )
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if idx in page_noise_indices:
            if line:
                removed.append(line)
            continue
        normalized = re.sub(r"\s+", " ", line).casefold()
        report_watermark = False
        if normalized == "report":
            neighbors = []
            if idx > 0:
                neighbors.append(lines[idx - 1].strip().casefold())
            if idx + 1 < len(lines):
                neighbors.append(lines[idx + 1].strip().casefold())
            report_watermark = any(
                re.fullmatch(r"\d{1,5}", neighbor)
                or "asianovel.com" in neighbor
                or "mp4directs.com" in neighbor
                for neighbor in neighbors
            )
        is_noise = (
            normalized in repeated_noise
            or report_watermark
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
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    elif suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".epub":
        text = _extract_epub(path)
    else:
        text = _extract_docx(path)
    return ExtractedBook(title=path.stem, source_path=path, text=clean_text(text))


def pdf_extraction_quality_warning(page_count: int, word_count: int) -> str | None:
    """Return a blocking diagnostic for suspiciously sparse long-PDF extraction."""
    pages = max(0, int(page_count))
    words = max(0, int(word_count))
    if pages >= 30 and words < max(500, pages * 25):
        return (
            f"PDF text extraction appears incomplete: only {words:,} words were extracted "
            f"from a {pages:,}-page PDF. Import was stopped to avoid creating a partial "
            "audiobook. Check that the PDF has a searchable text layer, run OCR on the "
            "source if needed, or import an EPUB/TXT version. Your source file was not changed."
        )
    return None


def _extract_pdf(path: Path) -> str:
    import fitz

    pages = []
    with fitz.open(path) as document:
        page_count = len(document)
        for page in document:
            pages.append(page.get_text("text"))
    text = "\n\n".join(pages)
    warning = pdf_extraction_quality_warning(page_count, len(text.split()))
    if warning:
        raise ValueError(warning)
    return text


def _extract_epub(path: Path) -> str:
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub(str(path))
    document_items = list(book.get_items_of_type(ITEM_DOCUMENT))

    # EPUB manifest order is not necessarily reading order. Follow the spine
    # first, then append unreferenced document items as a fallback for malformed
    # books that omit content from the spine.
    by_id = {item.get_id(): item for item in document_items}
    ordered_items = []
    seen_ids = set()
    for spine_entry in getattr(book, "spine", []) or []:
        item_id = spine_entry[0] if isinstance(spine_entry, (tuple, list)) else spine_entry
        item = by_id.get(item_id)
        if item is not None and item_id not in seen_ids:
            ordered_items.append(item)
            seen_ids.add(item_id)
    ordered_items.extend(item for item in document_items if item.get_id() not in seen_ids)

    parts = []
    for item in ordered_items:
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            parts.append(text)
    return "\n\n".join(parts)

def _extract_docx(path: Path) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl

    document = Document(path)
    parts = []

    # Walk document body blocks in their original order. Some books place
    # story text inside one-cell tables, so reading paragraphs alone can
    # silently omit those sections.
    for block in document.element.body.iterchildren():
        if isinstance(block, CT_P):
            paragraph = Paragraph(block, document)
            if paragraph.text.strip():
                parts.append(paragraph.text)
        elif isinstance(block, CT_Tbl):
            table = Table(block, document)
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" ".join(cells))
    return "\n\n".join(parts)

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
