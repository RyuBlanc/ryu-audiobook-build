from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from app.core.paths import library_root, settings_root

MAX_RECENT_IMPORT_AGE = timedelta(days=7)


def _record_path() -> Path:
    return settings_root() / "latest-import.json"


def _is_active_library_project(folder: Path) -> bool:
    try:
        root = library_root().resolve()
        resolved = folder.resolve()
        return resolved != root and root in resolved.parents and resolved.is_dir() and (resolved / "project.json").is_file() and (resolved / "chapters.json").is_file()
    except (OSError, RuntimeError):
        return False


def record_latest_import(project) -> dict:
    """Persist a successfully-created project as the latest import."""
    folder = Path(project.folder).resolve()
    if not _is_active_library_project(folder):
        raise ValueError("Only an active, saved Library project can be recorded as the latest import.")
    source = getattr(project, "source_path", None)
    payload = {
        "title": str(getattr(project, "title", folder.name)),
        "project_folder": str(folder),
        "source_name": Path(source).name if source else "",
        "chapter_count": len(getattr(project, "chapters", []) or []),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = _record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return payload


def load_latest_import(now: datetime | None = None) -> dict | None:
    """Return recent import metadata only while the project still exists in Library."""
    path = _record_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not payload.get("project_folder") or not payload.get("imported_at"):
            raise ValueError("Latest-import record is incomplete.")
        folder = Path(payload["project_folder"]).resolve()
        imported_at = datetime.fromisoformat(str(payload["imported_at"]))
        if imported_at.tzinfo is None:
            imported_at = imported_at.replace(tzinfo=timezone.utc)
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        age = clock - imported_at.astimezone(timezone.utc)
        if age < timedelta(minutes=-5) or age > MAX_RECENT_IMPORT_AGE or not _is_active_library_project(folder):
            path.unlink(missing_ok=True)
            return None
        payload["project_folder"] = str(folder)
        return payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None


def clear_latest_import_for_folder(folder: str | Path) -> bool:
    """Clear the progress-card record if that project's folder is deleted or moved to Trash."""
    path = _record_path()
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded = Path(payload.get("project_folder", "")).resolve()
        target = Path(folder).resolve()
        if recorded == target or not _is_active_library_project(recorded):
            path.unlink(missing_ok=True)
            return True
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return True
    return False
