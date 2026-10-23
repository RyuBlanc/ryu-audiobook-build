from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid

from app.core.paths import app_root, library_root


def trash_root() -> Path:
    """App-managed reversible-deletion store, outside the active Library."""
    return app_root() / "Trash" / "projects"


def _manifest_path(folder: Path) -> Path:
    return folder / "trash-manifest.json"


def trash_project(project) -> Path:
    """Move a project to managed Trash, saving only safe recovery metadata.

    The moved project folder keeps its chapters, source copy, generated work,
    and state (including pronunciation dictionary) intact until permanently
    purged. A separate history event is appended before removal from Library.
    """
    root = library_root().resolve()
    folder = Path(project.folder).resolve()
    if folder == root or root not in folder.parents:
        raise ValueError("Refusing to trash a folder outside the audiobook library.")
    if not folder.is_dir():
        raise FileNotFoundError(f"Project folder does not exist: {folder}")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry_id = uuid.uuid4().hex
    trash_root().mkdir(parents=True, exist_ok=True)
    destination = trash_root() / f"{now[:10]}-{entry_id}"
    destination.mkdir(parents=False, exist_ok=False)
    target = destination / folder.name
    try:
        shutil.move(str(folder), str(target))
        manifest = {
            "id": entry_id,
            "title": str(getattr(project, "title", folder.name)),
            "deleted_at": now,
            "original_folder_name": folder.name,
            "project_folder": str(target),
            "restorable": True,
        }
        _manifest_path(destination).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _append_history({
            "event": "project_trashed",
            "project_title": manifest["title"],
            "deleted_at": now,
            "trash_id": entry_id,
        })
        return destination
    except Exception:
        # Best effort rollback: do not silently strand a project if a manifest
        # cannot be persisted.
        if target.exists() and not folder.exists():
            folder.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(folder))
        shutil.rmtree(destination, ignore_errors=True)
        raise


def list_trashed_projects() -> list[dict]:
    root = trash_root()
    if not root.exists():
        return []
    entries = []
    for entry in root.iterdir():
        manifest_path = _manifest_path(entry)
        if not entry.is_dir() or not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("restorable") and Path(data.get("project_folder", "")).is_dir():
                entries.append(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return sorted(entries, key=lambda item: item.get("deleted_at", ""), reverse=True)


def restore_project(trash_entry: str | Path) -> Path:
    """Restore a trashed project to its original folder, choosing a safe suffix on collision."""
    entry = Path(trash_entry).resolve()
    root = trash_root().resolve()
    if entry == root or root not in entry.parents:
        raise ValueError("Refusing to restore from outside the managed Trash.")
    manifest_path = _manifest_path(entry)
    if not manifest_path.is_file():
        raise FileNotFoundError("Trash recovery record was not found.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("restorable"):
        raise ValueError("This Trash entry is not restorable.")
    project_folder = Path(manifest["project_folder"]).resolve()
    if entry.resolve() not in project_folder.parents:
        raise ValueError("Trash entry points outside its own recovery folder.")
    library = library_root().resolve()
    library.mkdir(parents=True, exist_ok=True)
    name = str(manifest.get("original_folder_name") or project_folder.name)
    destination = library / name
    suffix = 2
    while destination.exists():
        destination = library / f"{name} (restored {suffix})"
        suffix += 1
    shutil.move(str(project_folder), str(destination))
    _append_history({
        "event": "project_restored",
        "project_title": str(manifest.get("title") or name),
        "restored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trash_id": manifest.get("id"),
    })
    shutil.rmtree(entry, ignore_errors=True)
    return destination


def _append_history(event: dict) -> None:
    """Append a small, independent history record that survives project deletion."""
    path = app_root() / "History" / "project-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def purge_trashed_project(trash_entry: str | Path) -> None:
    """Permanently erase one entry only from the managed Trash folder."""
    entry = Path(trash_entry).resolve()
    root = trash_root().resolve()
    if entry == root or root not in entry.parents:
        raise ValueError("Refusing to purge a folder outside the managed Trash.")
    if not _manifest_path(entry).is_file():
        raise ValueError("Refusing to purge an unrecognized Trash entry.")
    manifest = json.loads(_manifest_path(entry).read_text(encoding="utf-8"))
    project_folder = Path(manifest.get("project_folder", "")).resolve()
    if entry not in project_folder.parents:
        raise ValueError("Trash manifest points outside its recovery folder.")
    shutil.rmtree(entry)
    _append_history({
        "event": "project_purged",
        "project_title": str(manifest.get("title") or ""),
        "purged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trash_id": manifest.get("id"),
    })
