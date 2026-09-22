from __future__ import annotations

from pathlib import Path
import json
from typing import Any

def load_state(project_folder: Path) -> dict[str, Any]:
    path = project_folder / "state.json"
    if not path.exists():
        return {"voice_id": None, "output_path": None, "cover_path": None, "status": "new", "completed_chapters": [], "failed_chapters": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"voice_id": None, "output_path": None, "cover_path": None, "status": "new", "completed_chapters": [], "failed_chapters": []}

def save_state(project_folder: Path, state: dict[str, Any]) -> None:
    project_folder.mkdir(parents=True, exist_ok=True)
    (project_folder / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
