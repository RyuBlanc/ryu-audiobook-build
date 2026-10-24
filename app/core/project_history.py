from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

from app.core.paths import settings_root


def history_path() -> Path:
    return settings_root() / "project_history.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_deleted_project_records(path: Path | None = None) -> list[dict]:
    target = path or history_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [dict(row) for row in data if isinstance(row, dict)]


def _write(records: list[dict], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".project-history-", suffix=".tmp", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(target)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise


def record_project_deletion(project, state: dict, *, output_path: str = "", output_removed: bool = False, path: Path | None = None) -> str:
    """Persist a standalone history snapshot before the project folder is removed."""
    target = path or history_path()
    records = load_deleted_project_records(target)
    record_id = uuid.uuid4().hex
    records.append({
        "id": record_id,
        "title": str(getattr(project, "title", "") or "Untitled"),
        "series": str(state.get("series_name") or state.get("series") or ""),
        "original_project_folder": str(getattr(project, "folder", "") or ""),
        "source_filename": Path(project.source_path).name if getattr(project, "source_path", None) else "",
        "deleted_at": _timestamp(),
        "deletion_state": "pending",
        "chapter_count": len(getattr(project, "chapters", []) or []),
        "completed_chapters": len(state.get("completed_chapters") or []),
        "failed_chapters": len(state.get("failed_chapters") or []),
        "last_status": str(state.get("status") or "new"),
        "output_path": str(output_path or ""),
        "output_removed": bool(output_removed),
    })
    _write(records, target)
    return record_id


def update_project_deletion(record_id: str, *, deletion_state: str, output_removed: bool | None = None, path: Path | None = None) -> None:
    target = path or history_path()
    records = load_deleted_project_records(target)
    found = False
    for record in records:
        if str(record.get("id")) != str(record_id):
            continue
        record["deletion_state"] = str(deletion_state)
        if output_removed is not None:
            record["output_removed"] = bool(output_removed)
        found = True
        break
    if found:
        _write(records, target)
