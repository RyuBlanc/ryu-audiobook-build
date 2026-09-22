from __future__ import annotations

from pathlib import Path

SUPPORTED_COVERS = {".jpg", ".jpeg", ".png"}

def validate_cover(path: Path | None) -> Path | None:
    if path is None:
        return None
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in SUPPORTED_COVERS:
        raise ValueError("Cover must be JPG or PNG.")
    return path

def sanitize_metadata(value: str, fallback: str = "") -> str:
    value = " ".join(value.replace("\x00", "").split())
    return value[:500] if value else fallback
