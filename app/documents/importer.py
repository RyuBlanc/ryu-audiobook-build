from __future__ import annotations

from pathlib import Path
import shutil

from .parser import ExtractedBook, extract_text

def import_book(source: str | Path, library_root: Path) -> ExtractedBook:
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    book = extract_text(source_path)
    destination = library_root / source_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    source_dir = destination / "source"
    source_dir.mkdir(exist_ok=True)
    shutil.copy2(source_path, source_dir / source_path.name)
    return book
