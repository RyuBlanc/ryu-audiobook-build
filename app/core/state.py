from __future__ import annotations

from pathlib import Path
import json
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
    project_folder.mkdir(parents=True, exist_ok=True)
    (project_folder / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
