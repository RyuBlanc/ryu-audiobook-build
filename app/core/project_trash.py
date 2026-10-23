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
    moved_artifacts: list[dict] = []
    manifest: dict = {}
    try:
        # The current generator normally stores the finished M4B inside the
        # project folder. Handle legacy/output paths outside it only when they
        # are under the app-managed Library root; never move arbitrary user files.
        state_path = folder / "state.json"
        state = {}
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                state = {}
        output_value = state.get("output_path") if isinstance(state, dict) else None
        output_path = Path(output_value).expanduser().resolve() if output_value else None
        external_output = None
        if output_path and output_path.exists() and folder not in output_path.parents:
            # Keep recovery constrained to app-owned files. The current project
            # output directory is within the project and therefore moves with it.
            managed_roots = (root,)
            if any(output_path != managed and managed in output_path.parents for managed in managed_roots):
                external_output = output_path

        shutil.move(str(folder), str(target))
        manifest = {
            "id": entry_id,
            "title": str(getattr(project, "title", folder.name)),
            "deleted_at": now,
            "original_folder_name": folder.name,
            "project_folder": str(target),
            "external_artifacts": [],
            "restorable": True,
        }
        if external_output and external_output.is_file():
            artifact_dir = destination / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            stored = artifact_dir / external_output.name
            suffix = 2
            while stored.exists():
                stored = artifact_dir / f"{external_output.stem} ({suffix}){external_output.suffix}"
                suffix += 1
            shutil.move(str(external_output), str(stored))
            moved_artifacts.append({"original_path": str(external_output), "trash_path": str(stored)})
            manifest["external_artifacts"].append({
                "original_path": str(external_output),
                "trash_path": str(stored),
            })
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
        for artifact in moved_artifacts:
            original_path = Path(artifact["original_path"])
            trashed_path = Path(artifact["trash_path"])
            if trashed_path.exists() and not original_path.exists():
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(trashed_path), str(original_path))
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
    restored_artifacts = []
    for artifact in manifest.get("external_artifacts", []):
        try:
            original_path = Path(artifact["original_path"]).expanduser()
            trashed_path = Path(artifact["trash_path"]).resolve()
            if entry not in trashed_path.parents or not trashed_path.is_file():
                continue
            restore_to = original_path
            if restore_to.exists():
                restore_to = restore_to.with_name(
                    f"{restore_to.stem} (restored {datetime.now().strftime('%H%M%S')}){restore_to.suffix}"
                )
            restore_to.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trashed_path), str(restore_to))
            restored_artifacts.append((original_path, restore_to))
        except (KeyError, OSError, ValueError):
            continue
    # If an external generated audiobook was restored to a collision-safe path,
    # update this project's state pointer without touching pronunciation data.
    if restored_artifacts:
        state_path = destination / "state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                current_output = str(state.get("output_path") or "")
                for original_path, restored_path in restored_artifacts:
                    if current_output == str(original_path):
                        state["output_path"] = str(restored_path)
                        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                        break
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
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
