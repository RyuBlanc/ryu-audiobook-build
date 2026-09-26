from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import wave
from typing import Callable

from app.chapters.detector import Chapter
from app.tts.base import TTSProvider
from app.tts.chunker import split_text

@dataclass
class GenerationResult:
    chapter_number: int
    output_path: Path
    chunks_total: int
    chunks_completed: int

def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).strip()
    return value or "chapter"

def state_path(chapter_dir: Path) -> Path:
    return chapter_dir / "generation.json"

def load_state(chapter_dir: Path) -> dict:
    path = state_path(chapter_dir)
    if not path.exists():
        return {"completed": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"completed": []}

def save_state(chapter_dir: Path, state: dict) -> None:
    state_path(chapter_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")

def generate_chapter(
    chapter: Chapter,
    provider: TTSProvider,
    voice: str,
    output_root: Path,
    progress: Callable[[int, int], None] | None = None,
) -> GenerationResult:
    chapter_dir = output_root / f"{chapter.number:03d}_{safe_name(chapter.title)}"
    chunks_dir = chapter_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if hasattr(provider, "split_for_cast"):
        chunks_with_voices = provider.split_for_cast(chapter.text, voice)
    else:
        chunks_with_voices = [(chunk, voice) for chunk in split_text(chapter.text)]
    chunks = [item[0] for item in chunks_with_voices]
    if not chunks:
        raise ValueError(
            f"Chapter {chapter.number} \"{chapter.title}\" contains no readable text to synthesize."
        )
    state = load_state(chapter_dir)
    previous_total = state.get("chunks_total")
    if previous_total is not None and previous_total != len(chunks):
        # A changed chapter split/cast assignment invalidates the old chunk map.
        state = {"completed": [], "chunks_total": len(chunks)}
    else:
        state.setdefault("chunks_total", len(chunks))
    completed = set(state.get("completed", []))

    for index, chunk in enumerate(chunks):
        filename = f"{index + 1:05d}.wav"
        output = chunks_dir / filename
        needs_generation = index not in completed or not output.exists()
        if needs_generation:
            chunk_voice = chunks_with_voices[index][1]
            provider.synthesize(chunk, output, chunk_voice)

        # Never mark a chunk complete unless the provider actually produced a
        # readable WAV file. This also repairs stale generation state from a
        # previous interrupted/failed run.
        if not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError(
                f"Audio chunk {index + 1}/{len(chunks)} was not created: {output.name}"
            )
        try:
            with wave.open(str(output), "rb") as wav:
                if wav.getnframes() <= 0 or wav.getframerate() <= 0:
                    raise RuntimeError(
                        f"Audio chunk {index + 1}/{len(chunks)} is empty: {output.name}"
                    )
        except (wave.Error, OSError) as exc:
            raise RuntimeError(
                f"Audio chunk {index + 1}/{len(chunks)} is not a valid WAV: {output.name} ({exc})"
            ) from exc

        if index not in completed:
            completed.add(index)
            state["completed"] = sorted(completed)
            save_state(chapter_dir, state)
        if progress:
            progress(len(completed), len(chunks))

    manifest = chapter_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"chapter": chapter.number, "title": chapter.title, "chunks": len(chunks), "completed": len(completed)},
            indent=2,
        ),
        encoding="utf-8",
    )
    return GenerationResult(chapter.number, chapter_dir, len(chunks), len(completed))
