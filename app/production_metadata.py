from __future__ import annotations

import re
from pathlib import Path
from typing import Any


METADATA_FIELD_LABELS = {
    "title": "Book Title",
    "author": "Author",
    "narrator": "Narrator",
    "publisher": "Publisher",
    "series": "Series",
    "series_volume": "Series Volume",
    "language": "Language",
    "year": "Release Year",
    "genre": "Genre",
    "cover_path": "Cover Image",
}

# The supplied Stage 5 Step 5.1 plan groups all ten entries under
# "Required metadata fields". Keep that full list release-blocking.
REQUIRED_METADATA_FIELDS = (
    "title", "author", "narrator", "publisher", "series",
    "series_volume", "language", "year", "genre", "cover_path",
)


def normalize_metadata_text(value: Any, *, max_length: int = 500) -> str:
    """Normalize metadata without silently supplying a fake value."""
    if value is None:
        return ""
    normalized = " ".join(str(value).replace("\\x00", " ").split())
    return normalized[:max(1, int(max_length))]


def _validated_cover_path(value: Any) -> str:
    """A required cover must be a real, non-empty image in an M4B-supported format."""
    raw = normalize_metadata_text(value, max_length=4096)
    if not raw:
        return ""
    try:
        path = Path(raw).expanduser()
        if path.suffix.casefold() not in {".jpg", ".jpeg", ".png"}:
            return ""
        if not path.is_file() or path.stat().st_size <= 0:
            return ""
        return str(path.resolve())
    except (OSError, RuntimeError, ValueError):
        return ""


def missing_required_metadata_fields(
    project_title: str,
    state: dict[str, Any] | None,
    narrator_profile: str | None,
) -> list[str]:
    """Return every mandatory label missing from persisted state/effective profile."""
    saved = state if isinstance(state, dict) else {}
    year = normalize_metadata_text(saved.get("year"), max_length=10)
    values = {
        "title": normalize_metadata_text(project_title),
        "author": normalize_metadata_text(saved.get("author")),
        "narrator": normalize_metadata_text(narrator_profile),
        "publisher": normalize_metadata_text(saved.get("publisher")),
        "series": normalize_metadata_text(saved.get("series")),
        "series_volume": normalize_metadata_text(saved.get("series_volume"), max_length=120),
        "language": normalize_metadata_text(saved.get("language"), max_length=120),
        "year": year if re.fullmatch(r"\\d{4}", year) else "",
        "genre": normalize_metadata_text(saved.get("genre")),
        "cover_path": _validated_cover_path(saved.get("cover_path")),
    }
    return [METADATA_FIELD_LABELS[key] for key in REQUIRED_METADATA_FIELDS if not values[key]]
