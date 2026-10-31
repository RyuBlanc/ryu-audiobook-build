from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
from typing import Any


def _default_state() -> dict[str, Any]:
    return {
        "voice_id": None,
        "voice_profile": None,
        "output_path": None,
        "cover_path": None,
        "backend": "automatic",
        "status": "new",
        "completed_chapters": [],
        "failed_chapters": [],
    }


def load_state(project_folder: Path) -> dict[str, Any]:
    path = project_folder / "state.json"
    if not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = _default_state()
        if isinstance(data, dict):
            state.update(data)
        return state
    except (OSError, ValueError, json.JSONDecodeError):
        return _default_state()


def save_state(project_folder: Path, state: dict[str, Any]) -> None:
    """Persist project state with a same-directory atomic replace.

    Serialize before creating the temporary file so invalid values cannot
    disturb the last good state. The previous state.json remains in place
    until the complete new payload has been flushed and atomically replaced.
    """
    if not isinstance(state, dict):
        raise TypeError("Project state must be a JSON object.")

    path = project_folder / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
