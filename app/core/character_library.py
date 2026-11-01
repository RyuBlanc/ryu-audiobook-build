from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import tempfile
import uuid

from app.core.paths import settings_root


def character_library_path() -> Path:
    """Persistent, series-level character registry shared across local books."""
    return settings_root() / "character_library.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_store() -> dict:
    return {"version": 1, "active": [], "deleted": []}


def _read_store(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(payload, dict):
        return _empty_store()
    active = payload.get("active", [])
    deleted = payload.get("deleted", [])
    return {
        "version": 1,
        "active": [dict(row) for row in active if isinstance(row, dict)] if isinstance(active, list) else [],
        "deleted": [dict(row) for row in deleted if isinstance(row, dict)] if isinstance(deleted, list) else [],
    }


def _write_store(store: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".character-library-", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise


def _safe_count(value: Any, *, maximum: int | None = None) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        number = 0
    number = max(0, number)
    return min(number, maximum) if maximum is not None else number


def _safe_confidence(value: Any, *, default: int = 0) -> int:
    """Normalize fractional analyzer confidence and percentage inputs to 0–100."""
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not (score == score and abs(score) != float("inf")):
        return default
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return max(0, min(100, int(round(score))))


def _clean_names(values, primary: str = "") -> list[str]:
    result: list[str] = []
    seen = {str(primary or "").strip().casefold()} if str(primary or "").strip() else set()
    if isinstance(values, (list, tuple)):
        for value in values:
            name = str(value or "").strip()
            key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            result.append(name)
            if len(result) >= 5:
                break
    return result


def list_characters(series: str | None = None, include_deleted: bool = False, path: Path | None = None) -> list[dict]:
    store = _read_store(path or character_library_path())
    rows = list(store["active"])
    if include_deleted:
        rows.extend(store["deleted"])
    if series and series.strip():
        wanted = series.strip().casefold()
        rows = [row for row in rows if str(row.get("series") or "").strip().casefold() == wanted]
    return sorted(rows, key=lambda row: (str(row.get("series") or "").casefold(), str(row.get("primary_name") or "").casefold()))


def list_deleted_characters(path: Path | None = None) -> list[dict]:
    """List soft-deleted character records separately for the recovery view."""
    return _read_store(path or character_library_path())["deleted"]


def sync_characters(
    series: str,
    rows: list[dict],
    source_project_folder: str = "",
    source_project_title: str = "",
    *,
    update_names: bool = False,
    update_voice: bool = False,
    path: Path | None = None,
) -> list[dict]:
    """Merge real Character Studio rows into the reusable series registry.

    Analysis can refresh dialogue and confidence without overwriting a name/sample
    that the user edited in Character Library. Explicit Character Studio renames
    and voice-assignment actions opt into their respective update flags.
    """
    series_name = str(series or "").strip()
    if not series_name:
        return list_characters(path=path)
    target = path or character_library_path()
    store = _read_store(target)
    active = store["active"]
    series_key = series_name.casefold()

    for source in rows or []:
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or source.get("primary_name") or "").strip()
        if not name or name.casefold() == "narrator":
            continue
        incoming_aliases = _clean_names(source.get("aliases") or [], name)
        incoming_keys = {name.casefold(), *(alias.casefold() for alias in incoming_aliases)}
        match = None
        for item in active:
            if str(item.get("series") or "").strip().casefold() != series_key:
                continue
            existing_keys = {
                str(item.get("primary_name") or "").strip().casefold(),
                *(str(alias).strip().casefold() for alias in (item.get("aliases") or [])),
            }
            existing_keys.discard("")
            if incoming_keys & existing_keys:
                match = item
                break

        examples = source.get("examples") or []
        sample = str(source.get("dialogue_sample") or (examples[0] if examples else "") or "").strip()
        voice = str(source.get("voice") or source.get("voice_name") or "").strip() or None
        if match is None:
            # A soft-deleted identity stays in the recovery bin; normal analysis
            # must not silently recreate it as a new active duplicate.
            deleted_match = False
            for item in store["deleted"]:
                if str(item.get("series") or "").strip().casefold() != series_key:
                    continue
                existing_keys = {
                    str(item.get("primary_name") or "").strip().casefold(),
                    *(str(alias).strip().casefold() for alias in (item.get("aliases") or [])),
                }
                existing_keys.discard("")
                if incoming_keys & existing_keys:
                    deleted_match = True
                    break
            if deleted_match:
                continue
            record = {
                "id": uuid.uuid4().hex,
                "series": series_name,
                "primary_name": name,
                "short": str(source.get("short") or name.split()[0])[:120],
                "aliases": incoming_aliases,
                "voice_name": voice,
                "dialogue_sample": sample,
                "dialogue_sample_source": "character-studio",
                "pronunciation": str(source.get("pronunciation") or "").strip(),
                "notes": str(source.get("notes") or "").strip()[:4000],
                "line_count": _safe_count(source.get("line_count", source.get("lines", source.get("dialogue_count", 0)))),
                "chapter_count": _safe_count(source.get("chapter_count", source.get("chapters", 0))),
                "confidence": _safe_confidence(source.get("confidence", 100)),
                "source_project_folder": str(source_project_folder or ""),
                "source_project_title": str(source_project_title or ""),
                "created_at": _timestamp(),
                "updated_at": _timestamp(),
            }
            active.append(record)
            continue

        match["series"] = series_name
        source_short = str(source.get("short") or "").strip()
        if source_short and (update_names or not str(match.get("short") or "").strip()):
            match["short"] = source_short[:120]
        elif not str(match.get("short") or "").strip():
            match["short"] = str(match.get("primary_name") or name).split()[0][:120]
        old_primary = str(match.get("primary_name") or "").strip()
        aliases = _clean_names(match.get("aliases") or [], old_primary)
        if update_names and name.casefold() != old_primary.casefold():
            aliases = _clean_names([*aliases, old_primary], name)
            match["primary_name"] = name
        for alias in incoming_aliases:
            aliases = _clean_names([*aliases, alias], str(match.get("primary_name") or ""))
        match["aliases"] = aliases
        if update_voice or not match.get("voice_name"):
            match["voice_name"] = voice
        if sample and (
            not str(match.get("dialogue_sample") or "").strip()
            or str(match.get("dialogue_sample_source") or "") != "manual"
        ):
            match["dialogue_sample"] = sample
            match["dialogue_sample_source"] = "character-studio"
        if source.get("pronunciation"):
            match["pronunciation"] = str(source["pronunciation"]).strip()
        if str(source.get("notes") or "").strip():
            match["notes"] = str(source.get("notes") or "").strip()[:4000]
        if any(key in source for key in ("line_count", "lines", "dialogue_count")):
            match["line_count"] = _safe_count(source.get("line_count", source.get("lines", source.get("dialogue_count", 0))))
        if any(key in source for key in ("chapter_count", "chapters")):
            match["chapter_count"] = _safe_count(source.get("chapter_count", source.get("chapters", 0)))
        if "confidence" in source:
            match["confidence"] = _safe_confidence(source.get("confidence", 100))
        match["source_project_folder"] = str(source_project_folder or match.get("source_project_folder") or "")
        match["source_project_title"] = str(source_project_title or match.get("source_project_title") or "")
        match["updated_at"] = _timestamp()

    _write_store(store, target)
    return list_characters(path=target)


def update_character(record_id: str, changes: dict, path: Path | None = None) -> dict:
    target = path or character_library_path()
    store = _read_store(target)
    record = next((item for item in store["active"] if str(item.get("id")) == str(record_id)), None)
    if record is None:
        raise KeyError("The character is no longer in the active Character Library.")
    series = str(changes.get("series", record.get("series", "")) or "").strip()
    primary = str(changes.get("primary_name", record.get("primary_name", "")) or "").strip()
    if not series or not primary:
        raise ValueError("Series name and primary character name are required.")
    old_primary = str(record.get("primary_name") or "").strip()
    aliases = _clean_names(changes.get("aliases", record.get("aliases", [])), primary)
    if old_primary and old_primary.casefold() != primary.casefold():
        aliases = _clean_names([*aliases, old_primary], primary)
    record["series"] = series
    record["primary_name"] = primary
    if "short" in changes:
        record["short"] = str(changes.get("short") or primary.split()[0])[:120]
    elif not str(record.get("short") or "").strip():
        record["short"] = primary.split()[0][:120]
    record["aliases"] = aliases
    if "dialogue_sample" in changes:
        record["dialogue_sample"] = str(changes.get("dialogue_sample") or "").strip()
        record["dialogue_sample_source"] = "manual"
    if "pronunciation" in changes:
        record["pronunciation"] = str(changes.get("pronunciation") or "").strip()
    if "notes" in changes:
        record["notes"] = str(changes.get("notes") or "").strip()[:4000]
    if "voice_name" in changes:
        record["voice_name"] = str(changes.get("voice_name") or "").strip() or None
    record["updated_at"] = _timestamp()
    _write_store(store, target)
    return dict(record)


def soft_delete_character(record_id: str, path: Path | None = None) -> dict:
    target = path or character_library_path()
    store = _read_store(target)
    index = next((i for i, item in enumerate(store["active"]) if str(item.get("id")) == str(record_id)), None)
    if index is None:
        raise KeyError("The character is no longer in the active Character Library.")
    record = store["active"].pop(index)
    record["deleted_at"] = _timestamp()
    record["updated_at"] = record["deleted_at"]
    store["deleted"].append(record)
    _write_store(store, target)
    return dict(record)


def restore_character(record_id: str, path: Path | None = None) -> dict:
    target = path or character_library_path()
    store = _read_store(target)
    index = next((i for i, item in enumerate(store["deleted"]) if str(item.get("id")) == str(record_id)), None)
    if index is None:
        raise KeyError("The character is no longer in the recovery bin.")
    record = store["deleted"].pop(index)
    record.pop("deleted_at", None)
    record["updated_at"] = _timestamp()
    store["active"].append(record)
    _write_store(store, target)
    return dict(record)
