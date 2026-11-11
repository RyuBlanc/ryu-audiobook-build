from __future__ import annotations

import json
import unicodedata


def _canonical_identity_text(value: str) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip().casefold()


def character_identity_key(name: str, series: str) -> str:
    """Build an unambiguous, Unicode-normalized key for a series-scoped identity."""
    canonical_name = _canonical_identity_text(name)
    canonical_series = _canonical_identity_text(series)
    return json.dumps([canonical_series, canonical_name], ensure_ascii=False, separators=(",", ":"))


def parse_character_identity_key(value: str) -> tuple[str, str] | None:
    """Return (series, name) from an identity key created by this module."""
    try:
        parsed = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 2:
        return None
    series, name = (_canonical_identity_text(part) for part in parsed)
    if not series or not name:
        return None
    return series, name
