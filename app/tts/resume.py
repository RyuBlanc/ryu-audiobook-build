from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from app.tts.generator import is_valid_wav_chunk


@dataclass(frozen=True)
class GenerationResumeState:
    completed_chapters: tuple[int, ...]
    partial_chapters: tuple[int, ...]
    resume_available: bool


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def inspect_generation_state(audio_root: Path, chapters) -> GenerationResumeState:
    """Inspect only identity-matched, complete, readable chunk checkpoints."""
    completed: list[int] = []
    partial: list[int] = []

    if not audio_root.exists():
        return GenerationResumeState((), (), False)

    for chapter in chapters:
        prefix = f"{int(chapter.number):03d}_"
        candidates = sorted(
            path for path in audio_root.glob(f"{prefix}*")
            if path.is_dir()
        )
        if not candidates:
            continue

        chapter_id = str(getattr(chapter, "chapter_id", "") or "").strip()
        if chapter_id:
            matching = [
                candidate for candidate in candidates
                if str(_read_json(candidate / "narration.json").get("chapter_id") or "").strip() == chapter_id
            ]
            # A checkpoint with the same chapter number but a different stable
            # identity belongs to another chapter revision and is not reusable.
            candidates = matching

        if not candidates:
            continue
        if len(candidates) != 1:
            partial.append(int(chapter.number))
            continue

        chapter_dir = candidates[0]
        state = _read_json(chapter_dir / "generation.json")
        try:
            total = int(state.get("chunks_total") or 0)
        except (TypeError, ValueError, OverflowError):
            total = 0
        signature = str(state.get("generation_signature") or "").strip()
        persisted: set[int] = set()
        values = state.get("completed")
        if isinstance(values, list):
            for value in values:
                try:
                    index = int(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 <= index < total:
                    persisted.add(index)

        chunks_dir = chapter_dir / "chunks"
        valid = {
            index for index in persisted
            if is_valid_wav_chunk(chunks_dir / f"{index + 1:05d}.wav")
        }
        expected = set(range(total))
        if total > 0 and signature and valid == expected:
            completed.append(int(chapter.number))
        else:
            # Keep an invalid/incomplete folder visible as partial so the user
            # can resume and let the generator repair only incompatible chunks.
            partial.append(int(chapter.number))

    return GenerationResumeState(
        tuple(completed),
        tuple(partial),
        bool(completed or partial),
    )
