from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class GenerationResumeState:
    completed_chapters: tuple[int, ...]
    partial_chapters: tuple[int, ...]
    resume_available: bool


def inspect_generation_state(audio_root: Path, chapters) -> GenerationResumeState:
    completed: list[int] = []
    partial: list[int] = []

    if not audio_root.exists():
        return GenerationResumeState((), (), False)

    for chapter in chapters:
        prefix = f"{chapter.number:03d}_"
        candidates = sorted(
            path for path in audio_root.glob(f"{prefix}*")
            if path.is_dir()
        )
        if not candidates:
            continue

        chapter_dir = candidates[0]
        state_path = chapter_dir / "generation.json"
        state = {}
        if state_path.exists():
            try:
                value = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    state = value
            except (OSError, ValueError, json.JSONDecodeError):
                state = {}

        total = int(state.get("chunks_total") or 0)
        done = len(state.get("completed") or [])
        if total > 0 and done >= total:
            completed.append(chapter.number)
        elif done > 0 or (chapter_dir / "chunks").exists():
            partial.append(chapter.number)

    return GenerationResumeState(
        tuple(completed),
        tuple(partial),
        bool(completed or partial),
    )
