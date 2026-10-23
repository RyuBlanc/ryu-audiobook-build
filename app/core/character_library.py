from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from app.core.paths import app_root

MAX_ALIASES = 5


def character_library_path() -> Path:
    return app_root() / "Settings" / "character-library.json"


def load_character_library() -> list[dict]:
    """Load persisted reusable cast records. No demo/static entries are created."""
    path = character_library_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("characters", [])
        if not isinstance(payload, list):
            return []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []
    results = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        name = str(row.get("primary_name") or row.get("name") or "").strip()
        if not name:
            continue
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(value).strip() for value in aliases[:MAX_ALIASES] if str(value).strip()]
        normalized = dict(row)
        normalized["id"] = str(row.get("id") or uuid.uuid4().hex)
        normalized["series"] = str(row.get("series") or "").strip()
        normalized["primary_name"] = name
        normalized["aliases"] = aliases
        normalized["voice_name"] = str(row.get("voice_name") or row.get("voice") or "").strip()
        normalized["dialogue_sample"] = str(row.get("dialogue_sample") or "").strip()
        normalized["deleted"] = bool(row.get("deleted", False))
        results.append(normalized)
    return results


def save_character_library(characters: list[dict]) -> None:
    path = character_library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = []
    for row in characters:
        if not isinstance(row, dict):
            continue
        name = str(row.get("primary_name") or row.get("name") or "").strip()
        if not name:
            continue
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        normalized.append({
            **row,
            "id": str(row.get("id") or uuid.uuid4().hex),
            "series": str(row.get("series") or "").strip(),
            "primary_name": name,
            "aliases": [str(value).strip() for value in aliases[:MAX_ALIASES]],
            "voice_name": str(row.get("voice_name") or row.get("voice") or "").strip(),
            "dialogue_sample": str(row.get("dialogue_sample") or "").strip(),
            "deleted": bool(row.get("deleted", False)),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps({"version": 1, "characters": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def upsert_characters_from_studio(series: str, rows: list[dict]) -> int:
    """Merge analyzed/manual Character Studio entries into the reusable library.

    Identity is series + primary name; aliases and voice assignment stay reusable
    across volumes. A blank series is allowed but shown as Unassigned series.
    """
    series = str(series or "").strip()
    existing = load_character_library()
    by_key = {
        (str(row.get("series", "")).casefold(), str(row.get("primary_name", "")).casefold()): row
        for row in existing
    }
    changed = 0
    for source in rows:
        if not isinstance(source, dict):
            continue
        name = str(source.get("primary_name") or source.get("name") or "").strip()
        if not name:
            continue
        key = (series.casefold(), name.casefold())
        current = by_key.get(key)
        aliases = source.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(value).strip() for value in aliases if str(value).strip()][:MAX_ALIASES]
        if current is None:
            current = {
                "id": uuid.uuid4().hex,
                "series": series,
                "primary_name": name,
                "aliases": aliases,
                "voice_name": str(source.get("voice_name") or source.get("voice") or "").strip(),
                "dialogue_sample": str(source.get("dialogue_sample") or source.get("sample") or "").strip(),
                "deleted": False,
                "source": "character-studio",
            }
            existing.append(current)
            by_key[key] = current
        else:
            if aliases:
                current["aliases"] = list(dict.fromkeys(
                    [*current.get("aliases", []), *aliases]
                ))[:MAX_ALIASES]
            sample = str(source.get("dialogue_sample") or source.get("sample") or "").strip()
            if sample:
                current["dialogue_sample"] = sample
            if "voice_name" in source or "voice" in source:
                current["voice_name"] = str(source.get("voice_name") or source.get("voice") or "").strip()
            current["deleted"] = False
        changed += 1
    if changed:
        save_character_library(existing)
    return changed


def update_character(character_id: str, updates: dict) -> dict:
    rows = load_character_library()
    for row in rows:
        if row.get("id") != character_id:
            continue
        if "primary_name" in updates or "name" in updates:
            value = str(updates.get("primary_name", updates.get("name", ""))).strip()
            if not value:
                raise ValueError("Primary character name cannot be blank.")
            row["primary_name"] = value
        if "aliases" in updates:
            aliases = updates["aliases"]
            if not isinstance(aliases, list):
                raise ValueError("Aliases must be a list.")
            row["aliases"] = [str(value).strip() for value in aliases if str(value).strip()][:MAX_ALIASES]
        for key in ("series", "dialogue_sample"):
            if key in updates:
                row[key] = str(updates[key] or "").strip()
        # Voice reassignment intentionally remains in Character Studio.
        if "voice_name" in updates or "voice" in updates:
            raise ValueError("Change an assigned voice from Character Studio, not Character Library.")
        save_character_library(rows)
        return row
    raise KeyError(f"Character not found: {character_id}")


def soft_delete_character(character_id: str) -> dict:
    rows = load_character_library()
    for row in rows:
        if row.get("id") == character_id:
            row["deleted"] = True
            save_character_library(rows)
            return row
    raise KeyError(f"Character not found: {character_id}")


def restore_character(character_id: str) -> dict:
    rows = load_character_library()
    for row in rows:
        if row.get("id") == character_id:
            row["deleted"] = False
            save_character_library(rows)
            return row
    raise KeyError(f"Character not found: {character_id}")
