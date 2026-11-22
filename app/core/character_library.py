from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any
import tempfile
import unicodedata
import uuid

from app.core.paths import settings_root


log = logging.getLogger(__name__)


def _identity_key(value: Any) -> str:
    """Use one Unicode-normalized comparison key across every book in a series."""
    return unicodedata.normalize("NFC", str(value or "")).strip().casefold()


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
    primary_key = _identity_key(primary)
    seen = {primary_key} if primary_key else set()
    if isinstance(values, (list, tuple)):
        for value in values:
            name = unicodedata.normalize("NFC", str(value or "")).strip()
            key = _identity_key(name)
            if not name or key in seen:
                continue
            seen.add(key)
            result.append(name)
    return result


def list_characters(series: str | None = None, include_deleted: bool = False, path: Path | None = None) -> list[dict]:
    store = _read_store(path or character_library_path())
    rows = list(store["active"])
    if include_deleted:
        rows.extend(store["deleted"])
    if series and series.strip():
        wanted = _identity_key(series)
        rows = [row for row in rows if _identity_key(row.get("series")) == wanted]
    return sorted(rows, key=lambda row: (str(row.get("series") or "").casefold(), str(row.get("primary_name") or "").casefold()))


def prune_invalid_character_records(
    series: str,
    path: Path | None = None,
    protected_names: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Move invalid legacy detections to Recovery and remove invalid aliases.

    Cleanup is restricted to one series. Invalid primary rows are retained in
    the existing deleted/recovery store rather than permanently erased.
    Explicit source assignments may protect a legitimate identity, but the
    shared validator still rejects hard function words and interjections.
    """
    wanted = str(series or "").strip()
    if not wanted:
        return {"removed": 0, "aliases_removed": 0}
    from app.chapters.characters import is_likely_character_name, is_user_confirmed_character_record

    protected = {
        str(value or "").strip().casefold()
        for value in (protected_names or ())
        if str(value or "").strip()
    }
    target = path or character_library_path()
    store = _read_store(target)
    kept: list[dict] = []
    removed = 0
    aliases_removed = 0
    changed = False
    for row in store["active"]:
        if str(row.get("series") or "").strip().casefold() != wanted.casefold():
            kept.append(row)
            continue
        primary = str(row.get("primary_name") or row.get("name") or "").strip()
        trusted = is_user_confirmed_character_record(row) or primary.casefold() in protected
        if not primary or not is_likely_character_name(primary, trusted=trusted):
            deleted = dict(row)
            deleted_at = _timestamp()
            deleted["deleted_at"] = deleted_at
            deleted["updated_at"] = deleted_at
            deleted["deletion_reason"] = "Removed from active cast by character-name quality cleanup"
            store["deleted"].append(deleted)
            removed += 1
            changed = True
            continue

        raw_aliases = row.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        raw_aliases = list(raw_aliases) if isinstance(raw_aliases, (list, tuple)) else []
        alias_trusted = trusted or bool(row.get("manual_aliases"))
        valid_aliases: list[str] = []
        seen = {primary.casefold()}
        for alias in raw_aliases:
            value = str(alias or "").strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            if not is_likely_character_name(value, trusted=alias_trusted) or (
                key in {"oh", "ah", "uh", "hmm", "huh", "um", "erm", "eh", "the", "a", "an", "any"}
            ):
                aliases_removed += 1
                changed = True
                continue
            seen.add(key)
            valid_aliases.append(value)
        if valid_aliases != raw_aliases:
            row["aliases"] = valid_aliases
            row["updated_at"] = _timestamp()
            changed = True
        kept.append(row)

    if changed:
        store["active"] = kept
        _write_store(store, target)
    return {"removed": removed, "aliases_removed": aliases_removed}


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
    series_key = _identity_key(series_name)

    for source in rows or []:
        if not isinstance(source, dict):
            continue
        name = unicodedata.normalize("NFC", str(source.get("name") or source.get("primary_name") or "")).strip()
        if not name or _identity_key(name) == "narrator":
            continue
        incoming_aliases = _clean_names(source.get("aliases") or [], name)
        incoming_keys = {_identity_key(name), *(_identity_key(alias) for alias in incoming_aliases)}
        incoming_keys.discard("")
        incoming_variant = _identity_key(source.get("identity_variant") or source.get("version") or "")
        active_matches = []
        variant_conflicts = []
        for item in active:
            if _identity_key(item.get("series")) != series_key:
                continue
            existing_keys = {
                _identity_key(item.get("primary_name") or item.get("name")),
                *(_identity_key(alias) for alias in (item.get("aliases") or [])),
            }
            existing_keys.discard("")
            if incoming_keys & existing_keys:
                if _identity_key(item.get("identity_variant")) == incoming_variant:
                    active_matches.append(item)
                else:
                    variant_conflicts.append(item)
        deleted_matches = []
        for item in store["deleted"]:
            if _identity_key(item.get("series")) != series_key:
                continue
            deleted_keys = {
                _identity_key(item.get("primary_name") or item.get("name")),
                *(_identity_key(alias) for alias in (item.get("aliases") or [])),
            }
            deleted_keys.discard("")
            if incoming_keys & deleted_keys:
                deleted_matches.append(item)
        if variant_conflicts or len(active_matches) > 1 or deleted_matches:
            reason = (
                "different age/version identity" if variant_conflicts
                else "multiple active Character Library identities" if len(active_matches) > 1
                else "matching identity in Recovery Bin"
            )
            log.warning(
                "Skipped Character Library sync for %r in series %r: %s. Resolve the identity before syncing.",
                name, series_name, reason,
            )
            continue
        match = active_matches[0] if active_matches else None

        examples = source.get("examples") or []
        if not isinstance(examples, (list, tuple)):
            examples = [str(examples)] if str(examples or "").strip() else []
        sample = str(source.get("dialogue_sample") or (examples[0] if examples else "") or "").strip()
        voice = str(source.get("voice") or source.get("voice_name") or "").strip() or None
        if match is None:
            # A soft-deleted identity stays in the recovery bin; normal analysis
            # must not silently recreate it as a new active duplicate.
            deleted_match = False
            for item in store["deleted"]:
                if _identity_key(item.get("series")) != series_key:
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
                "user_created": bool(source.get("user_created")),
                "manual": bool(source.get("manual")),
                "manual_aliases": bool(source.get("manual_aliases")),
                "imported_from_workbook": bool(source.get("imported_from_workbook")),
                "character_origin": str(source.get("character_origin") or ""),
                "character_library_id": str(source.get("character_library_id") or ""),
                "source_project_folder": str(source_project_folder or ""),
                "source_project_title": str(source_project_title or ""),
                "created_at": _timestamp(),
                "updated_at": _timestamp(),
            }
            identity_variant = str(source.get("identity_variant") or source.get("version") or "").strip()
            if identity_variant:
                record["identity_base_name"] = str(source.get("identity_base_name") or source.get("base_name") or name).strip()
                record["identity_variant"] = identity_variant
            active.append(record)
            continue

        match["series"] = series_name
        identity_variant = str(source.get("identity_variant") or source.get("version") or "").strip()
        if identity_variant:
            match["identity_base_name"] = str(source.get("identity_base_name") or source.get("base_name") or match.get("identity_base_name") or name).strip()
            match["identity_variant"] = identity_variant
        for flag in ("user_created", "manual", "manual_aliases", "imported_from_workbook"):
            if source.get(flag):
                match[flag] = True
        for flag in ("character_origin", "character_library_id"):
            if str(source.get(flag) or "").strip():
                match[flag] = str(source.get(flag) or "").strip()
        source_short = str(source.get("short") or "").strip()
        if source_short and (update_names or not str(match.get("short") or "").strip()):
            match["short"] = source_short[:120]
        elif not str(match.get("short") or "").strip():
            match["short"] = str(match.get("primary_name") or name).split()[0][:120]
        old_primary = str(match.get("primary_name") or "").strip()
        aliases = _clean_names(match.get("aliases") or [], old_primary)
        if update_names and _identity_key(name) != _identity_key(old_primary):
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




def merge_imported_character_records(
    series: str,
    rows: list[dict],
    path: Path | None = None,
) -> list[dict]:
    """Merge workbook identities into the canonical series registry in one atomic write.

    Existing primary names and voice assignments are preserved. Name/alias collisions
    across different characters and matches in Recovery fail closed.
    """
    series_name = str(series or "").strip()
    if not series_name:
        raise ValueError("A series name is required before merging imported characters.")
    target = path or character_library_path()
    store = _read_store(target)
    active = store["active"]
    deleted = store["deleted"]
    results: list[dict] = []

    def _variant(record: dict) -> str:
        return _identity_key(record.get("identity_variant"))

    def _tokens(record: dict) -> set[str]:
        primary = str(record.get("primary_name") or record.get("name") or "").strip()
        aliases = record.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        return {
            _identity_key(value)
            for value in [primary, *(aliases if isinstance(aliases, (list, tuple)) else [])]
            if _identity_key(value)
        }

    for incoming in rows or []:
        if not isinstance(incoming, dict):
            raise ValueError("Every imported Character Register entry must be an object.")
        primary = unicodedata.normalize("NFC", str(incoming.get("canonical_name") or incoming.get("primary_name") or "")).strip()
        if not primary or _identity_key(primary) == "narrator":
            raise ValueError("Imported characters need a non-empty name; Narrator is reserved.")
        if len(primary) > 160:
            raise ValueError("Imported character names must be 160 characters or fewer.")
        variant = unicodedata.normalize("NFC", str(incoming.get("identity_variant") or "")).strip()
        if len(variant) > 120:
            raise ValueError("Imported age/version labels must be 120 characters or fewer.")
        base_name = unicodedata.normalize("NFC", str(incoming.get("identity_base_name") or primary)).strip()
        if len(base_name) > 160:
            raise ValueError("Imported identity base names must be 160 characters or fewer.")
        raw_aliases = incoming.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        aliases = _clean_names(raw_aliases, primary)
        if any(len(alias) > 160 for alias in aliases):
            raise ValueError("Imported character aliases must be 160 characters or fewer.")
        incoming_notes = str(incoming.get("notes") or "").strip()
        if len(incoming_notes) > 4000:
            raise ValueError("Imported character notes must be 4,000 characters or fewer.")
        incoming_tokens = {_identity_key(primary), *(_identity_key(value) for value in aliases)}
        if any(not value for value in incoming_tokens):
            raise ValueError("Imported character names and aliases cannot be empty.")

        wanted_id = str(incoming.get("library_id") or "").strip()
        matches = []
        if wanted_id:
            matches = [
                item for item in active
                if str(item.get("id") or "") == wanted_id
                and _identity_key(item.get("series")) == _identity_key(series_name)
            ]
            if len(matches) != 1:
                raise KeyError("A matched Character Library identity changed before import. Review the workbook again.")
            if _variant(matches[0]) != variant.casefold():
                raise ValueError("The matched character version changed before import. Review the workbook again.")
        else:
            for item in active:
                if _identity_key(item.get("series")) != _identity_key(series_name):
                    continue
                if _variant(item) != variant.casefold():
                    continue
                if incoming_tokens & _tokens(item):
                    matches.append(item)
            if len(matches) > 1:
                raise ValueError("An imported name or alias matches multiple series characters. Resolve the duplicate before importing.")

        deleted_matches = [
            item for item in deleted
            if _identity_key(item.get("series")) == _identity_key(series_name)
            and incoming_tokens & _tokens(item)
        ]
        if deleted_matches:
            raise ValueError(
                "This name or alias matches an identity in the Character Library Recovery Bin. "
                "Restore or resolve that identity before importing; a duplicate will not be created."
            )

        match = matches[0] if matches else None
        for item in active:
            if item is match or _identity_key(item.get("series")) != _identity_key(series_name):
                continue
            if incoming_tokens & _tokens(item):
                raise ValueError(
                    "An imported name or alias is already used by another character in this series: "
                    + str(item.get("primary_name") or item.get("name") or "Unnamed")
                )

        if match is None:
            record = {
                "id": uuid.uuid4().hex,
                "series": series_name,
                "primary_name": primary,
                "short": str(incoming.get("short") or primary.split()[0])[:120],
                "aliases": aliases,
                "voice_name": str(incoming.get("existing_voice_name") or "").strip() or None,
                "dialogue_sample": "",
                "dialogue_sample_source": "character-workbook",
                "pronunciation": "",
                "notes": incoming_notes,
                "line_count": 0,
                "chapter_count": 0,
                "confidence": 100,
                "user_created": True,
                "manual": True,
                "manual_aliases": True,
                "imported_from_workbook": True,
                "identity_base_name": base_name,
                "identity_variant": variant,
                "created_at": _timestamp(),
                "updated_at": _timestamp(),
            }
            active.append(record)
        else:
            record = match
            existing_primary = str(record.get("primary_name") or primary).strip()
            merged = _clean_names([*(record.get("aliases") or []), *aliases], existing_primary)
            record["aliases"] = merged
            record["series"] = series_name
            record["user_created"] = True
            record["manual"] = True
            record["manual_aliases"] = True
            record["imported_from_workbook"] = True
            if variant:
                record["identity_variant"] = variant
                record["identity_base_name"] = base_name
            if incoming_notes and not str(record.get("notes") or "").strip():
                record["notes"] = incoming_notes
            record["updated_at"] = _timestamp()

        results.append(dict(record))

    if rows:
        _write_store(store, target)
    return results


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
    record["manual"] = True
    record["manual_aliases"] = True
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

    record = store["deleted"][index]
    series_key = _identity_key(record.get("series"))

    def _identity_tokens(item: dict) -> set[str]:
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        values = [item.get("primary_name") or item.get("name"), *(
            aliases if isinstance(aliases, (list, tuple)) else []
        )]
        return {_identity_key(value) for value in values if _identity_key(value)}

    restoring_tokens = _identity_tokens(record)
    conflicts = [
        item for item in store["active"]
        if _identity_key(item.get("series")) == series_key
        and restoring_tokens.intersection(_identity_tokens(item))
    ]
    if conflicts:
        conflict_names = sorted({
            str(item.get("primary_name") or item.get("name") or "Unnamed character").strip()
            for item in conflicts
        })
        raise ValueError(
            "Cannot restore this character because one or more names or aliases are already in use "
            "by an active character in this series (%s). Resolve the identity conflict first." %
            ", ".join(conflict_names[:4])
        )

    # Do not remove the Recovery Bin record until every collision check passes.
    record = store["deleted"].pop(index)
    record.pop("deleted_at", None)
    record["updated_at"] = _timestamp()
    store["active"].append(record)
    _write_store(store, target)
    return dict(record)



def _validated_record_ids(record_ids: Any) -> list[str]:
    """Validate and de-duplicate explicit Character Library record IDs."""
    if not isinstance(record_ids, (list, tuple, set)):
        raise ValueError("Supply one or more Character Library record IDs.")
    values = [str(value or "").strip() for value in record_ids]
    if any(not value for value in values):
        raise ValueError("Character Library record IDs cannot be empty.")
    selected = list(dict.fromkeys(values))
    if not selected:
        raise ValueError("Select at least one character.")
    return selected


def soft_delete_characters_many(
    record_ids: list[str] | tuple[str, ...] | set[str],
    path: Path | None = None,
) -> list[dict]:
    """Move multiple active character records to Recovery in one atomic write.

    Every requested ID must still be active. A stale or invalid selection fails
    before the store is modified, preventing a misleading partial deletion.
    Voice profile files are not touched; only reusable Character Library rows
    move between the active and deleted collections.
    """
    selected = _validated_record_ids(record_ids)
    target = path or character_library_path()
    store = _read_store(target)
    active_by_id = {
        str(row.get("id") or ""): row
        for row in store["active"]
        if str(row.get("id") or "")
    }
    missing = [record_id for record_id in selected if record_id not in active_by_id]
    if missing:
        raise KeyError(
            "One or more selected characters are no longer active. Refresh the Character Library and try again."
        )

    selected_set = set(selected)
    deleted_at = _timestamp()
    moved: list[dict] = []
    remaining: list[dict] = []
    for row in store["active"]:
        if str(row.get("id") or "") not in selected_set:
            remaining.append(row)
            continue
        record = dict(row)
        record["deleted_at"] = deleted_at
        record["updated_at"] = deleted_at
        store["deleted"].append(record)
        moved.append(dict(record))

    store["active"] = remaining
    _write_store(store, target)
    return moved


def purge_deleted_characters_many(
    record_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    path: Path | None = None,
) -> list[dict]:
    """Permanently purge selected Recovery rows, or all rows when IDs are None.

    Passing an explicit empty selection is rejected. Passing None is the
    deliberate Clear All operation. The active Character Library is untouched.
    """
    target = path or character_library_path()
    store = _read_store(target)
    if record_ids is None:
        selected = [str(row.get("id") or "") for row in store["deleted"]]
        selected = [value for value in selected if value]
        if not selected:
            return []
    else:
        selected = _validated_record_ids(record_ids)

    deleted_by_id = {
        str(row.get("id") or ""): row
        for row in store["deleted"]
        if str(row.get("id") or "")
    }
    missing = [record_id for record_id in selected if record_id not in deleted_by_id]
    if missing:
        raise KeyError(
            "One or more selected characters are no longer in Recovery. Refresh the Recovery Bin and try again."
        )

    selected_set = set(selected)
    purged = [dict(row) for row in store["deleted"] if str(row.get("id") or "") in selected_set]
    store["deleted"] = [
        row for row in store["deleted"]
        if str(row.get("id") or "") not in selected_set
    ]
    _write_store(store, target)
    return purged
