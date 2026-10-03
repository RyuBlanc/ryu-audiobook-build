from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import wave
import subprocess
import imageio_ffmpeg
from typing import Callable

from app.chapters.detector import Chapter
from app.tts.base import TTSProvider
from app.tts.chunker import split_text
from app.tts.narration import prepare_for_narration
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.multivoice import synthesize_voice_set


@dataclass
class GenerationResult:
    chapter_number: int
    output_path: Path
    chunks_total: int
    chunks_completed: int


@dataclass(frozen=True)
class ChapterPlan:
    chapter_dir: Path
    chunks_with_voices: tuple[tuple[str, str | list[str] | None], ...]
    signature: str
    completed: frozenset[int]


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


def _provider_signature(provider: TTSProvider, voice: str | None, chunks: list[tuple[str, str | list[str] | None]]) -> str:
    custom = getattr(provider, "generation_signature", None)
    if callable(custom):
        base = custom()
    else:
        base = f"{provider.__class__.__module__}.{provider.__class__.__name__}:{voice or ''}"
    payload = {"base": base, "chunks": [(text, chunk_voice) for text, chunk_voice in chunks]}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _apply_narration_speed(path: Path, speed: float) -> None:
    """Change playback tempo without changing pitch."""
    speed = max(0.5, min(2.0, float(speed)))
    if abs(speed - 1.0) < 0.001:
        return
    temp_path = path.with_suffix(".tempo.wav")
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(path),
         "-filter:a", f"atempo={speed:.3f}", "-c:a", "pcm_s16le", str(temp_path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not temp_path.exists() or temp_path.stat().st_size < 1024:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Could not apply narration speed {speed:.2f}x. {detail}")
    temp_path.replace(path)

def prepare_chapter_plan(
    chapter: Chapter,
    provider: TTSProvider,
    voice: str,
    output_root: Path,
    pronunciation_dictionary: list[dict] | None = None,
    narration_speed: float = 0.90,
    pacing_profile: str = "natural",
) -> ChapterPlan:
    """Prepare deterministic chapter chunks and identify resumable work.

    Completed chunk entries are trusted only when the generation signature
    still matches the current text/voice/settings and the corresponding WAV
    file is present. This lets long-book resumes avoid re-opening every
    completed WAV file on every run.
    """
    chapter_dir = output_root / f"{chapter.number:03d}_{safe_name(chapter.title)}"
    chunks_dir = chapter_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    narration = prepare_for_narration(
        chapter.text,
        pronunciation_dictionary=pronunciation_dictionary,
    )
    (chapter_dir / "narration.json").write_text(
        json.dumps(
            {
                "chapter": chapter.number,
                "title": chapter.title,
                "source_characters": len(chapter.text),
                "narration_characters": len(narration.narration_text),
                "narration_text": narration.narration_text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if hasattr(provider, "split_for_cast"):
        try:
            raw_chunks_with_voices = provider.split_for_cast(
                narration.narration_text,
                voice,
                dialogue_assignments=getattr(chapter, "dialogue_assignments", []),
            )
        except TypeError as exc:
            if "dialogue_assignments" not in str(exc):
                raise
            raw_chunks_with_voices = provider.split_for_cast(narration.narration_text, voice)
    else:
        raw_chunks_with_voices = [
            (chunk, voice) for chunk in split_text(narration.narration_text)
        ]

    chunks_with_voices: list[tuple[str, str | list[str] | None]] = []
    for chunk_text, chunk_voice in raw_chunks_with_voices:
        paced_chunks = split_for_pacing(
            chunk_text,
            max_chars=int(getattr(provider, "recommended_chunk_chars", 1400)),
            max_sentences=int(getattr(provider, "recommended_chunk_sentences", 2)),
        )
        if not paced_chunks:
            continue
        chunks_with_voices.extend((item, chunk_voice) for item in paced_chunks)

    chunks = [item[0] for item in chunks_with_voices]
    if not chunks:
        raise ValueError(
            f"Chapter {chapter.number} \"{chapter.title}\" contains no readable text to synthesize."
        )

    configure_narration = getattr(provider, "configure_narration", None)
    if callable(configure_narration):
        configure_narration(narration_speed, pacing_profile)

    signature = _provider_signature(provider, voice, chunks_with_voices)
    signature = hashlib.sha256(
        json.dumps(
            {
                "base": signature,
                "narration_speed": narration_speed,
                "pacing_profile": pacing_profile,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    state = load_state(chapter_dir)
    if (
        state.get("chunks_total") != len(chunks)
        or state.get("generation_signature") != signature
    ):
        state = {
            "completed": [],
            "chunks_total": len(chunks),
            "generation_signature": signature,
        }
        save_state(chapter_dir, state)
    else:
        state.setdefault("chunks_total", len(chunks))
        state.setdefault("generation_signature", signature)

    completed: set[int] = set()
    for value in state.get("completed") or []:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        output = chunks_dir / f"{index + 1:05d}.wav"
        if 0 <= index < len(chunks) and output.exists():
            completed.add(index)

    return ChapterPlan(
        chapter_dir=chapter_dir,
        chunks_with_voices=tuple(chunks_with_voices),
        signature=signature,
        completed=frozenset(completed),
    )


def generate_chapter(
    chapter: Chapter,
    provider: TTSProvider,
    voice: str,
    output_root: Path,
    progress: Callable[[int, int], None] | None = None,
    pronunciation_dictionary: list[dict] | None = None,
    narration_speed: float = 0.90,
    pacing_profile: str = "natural",
) -> GenerationResult:
    plan = prepare_chapter_plan(
        chapter,
        provider,
        voice,
        output_root,
        pronunciation_dictionary=pronunciation_dictionary,
        narration_speed=narration_speed,
        pacing_profile=pacing_profile,
    )
    chapter_dir = plan.chapter_dir
    chunks_dir = chapter_dir / "chunks"
    chunks_with_voices = list(plan.chunks_with_voices)
    chunks = [item[0] for item in chunks_with_voices]
    signature = plan.signature

    state = load_state(chapter_dir)
    completed = set(plan.completed)

    # Report already-complete work once. This is especially important for
    # resumed five-hour+ books: the UI can show real progress immediately
    # without re-opening every historical WAV just to validate it again.
    if progress and completed:
        progress(len(completed), len(chunks))

    for index, chunk in enumerate(chunks):
        filename = f"{index + 1:05d}.wav"
        output = chunks_dir / filename

        # A completed chunk with a matching generation signature is already
        # validated from the previous run. Reusing it should be effectively
        # free on resume.
        if index in completed and output.exists():
            continue

        chunk_voice = chunks_with_voices[index][1]
        if isinstance(chunk_voice, list):
            synthesize_voice_set(provider, chunk, chunk_voice, output)
        else:
            provider.synthesize(chunk, output, chunk_voice)
        if not getattr(provider, "handles_narration_controls", False):
            if abs(narration_speed - 1.0) > 0.001:
                _apply_narration_speed(output, narration_speed)
            pause_ms = pause_after_ms(chunk, pacing_profile)
            if pause_ms:
                append_silence(output, pause_ms)

        if not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError(
                f"Audio chunk {index + 1}/{len(chunks)} was not created: {output.name}"
            )
        try:
            with wave.open(str(output), "rb") as wav_file:
                if wav_file.getnframes() <= 0 or wav_file.getframerate() <= 0:
                    raise RuntimeError(
                        f"Audio chunk {index + 1}/{len(chunks)} is empty: {output.name}"
                    )
        except (wave.Error, OSError) as exc:
            raise RuntimeError(
                f"Audio chunk {index + 1}/{len(chunks)} is not a valid WAV: "
                f"{output.name} ({exc})"
            ) from exc

        completed.add(index)
        state["completed"] = sorted(completed)
        save_state(chapter_dir, state)
        if progress:
            progress(len(completed), len(chunks))

    (chapter_dir / "manifest.json").write_text(
        json.dumps(
            {
                "chapter": chapter.number,
                "title": chapter.title,
                "chunks": len(chunks),
                "completed": len(completed),
                "generation_signature": signature,
                "narration_speed": narration_speed,
                "pacing_profile": pacing_profile,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return GenerationResult(
        chapter.number,
        chapter_dir,
        len(chunks),
        len(completed),
    )

