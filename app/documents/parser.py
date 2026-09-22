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

def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
