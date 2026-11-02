from __future__ import annotations

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
REQUIRED_METADATA_FIELDS = ("title", "author", "narrator", "language", "genre")


def normalize_metadata_text(value: Any, *, max_length: int = 500) -> str:
    """Normalize metadata without silently supplying a fake value."""
    if value is None:
        return ""
    normalized = " ".join(str(value).replace("\x00", " ").split())
    return normalized[:max(1, int(max_length))]


def missing_required_metadata_fields(
    project_title: str,
    state: dict[str, Any] | None,
    narrator_profile: str | None,
) -> list[str]:
    """Return required labels missing from persisted state/effective narrator."""
    saved = state if isinstance(state, dict) else {}
    values = {
        "title": normalize_metadata_text(project_title),
        "author": normalize_metadata_text(saved.get("author")),
        "narrator": normalize_metadata_text(narrator_profile),
        "language": normalize_metadata_text(saved.get("language")),
        "genre": normalize_metadata_text(saved.get("genre")),
    }
    return [METADATA_FIELD_LABELS[key] for key in REQUIRED_METADATA_FIELDS if not values[key]]
