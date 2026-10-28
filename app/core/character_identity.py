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

def set_character_voice_assignment(
    state: dict,
    name: str,
    series: str,
    profile_name: str,
) -> dict:
    """Return state with both scoped and legacy voice mappings updated.

    The series-scoped key is authoritative during cast routing. Updating only
    the legacy name map can leave a stale or explicitly empty scoped assignment
    in place, making the UI claim an assignment that generation does not use.
    """
    if not isinstance(state, dict):
        raise TypeError("Project state must be a dictionary.")

    character_name = str(name or "").strip()
    voice_name = str(profile_name or "").strip()
    if not character_name:
        raise ValueError("A character name is required.")
    if not voice_name:
        raise ValueError("A saved voice profile name is required.")

    updated = dict(state)
    identity_assignments = updated.get("voice_cast_identity_assignments", {})
    identity_assignments = dict(identity_assignments) if isinstance(identity_assignments, dict) else {}
    identity_assignments[character_identity_key(character_name, series)] = voice_name
    updated["voice_cast_identity_assignments"] = identity_assignments

    legacy_assignments = updated.get("voice_cast", {})
    legacy_assignments = dict(legacy_assignments) if isinstance(legacy_assignments, dict) else {}
    legacy_assignments[character_name] = voice_name
    updated["voice_cast"] = legacy_assignments
    return updated

