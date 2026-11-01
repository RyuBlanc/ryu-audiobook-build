from __future__ import annotations

import json


def character_identity_key(name: str, series: str) -> str:
    """Build an unambiguous, stable key for a series-scoped character identity."""
    canonical_name = str(name or "").strip().casefold()
    canonical_series = str(series or "").strip().casefold()
    return json.dumps([canonical_series, canonical_name], ensure_ascii=False, separators=(",", ":"))


def parse_character_identity_key(value: str) -> tuple[str, str] | None:
    """Return (series, name) from an identity key created by this module."""
    try:
        parsed = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 2:
        return None
    series, name = (str(part or "").strip().casefold() for part in parsed)
    if not series or not name:
        return None
    return series, name
