from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile
import wave
from typing import Callable

from app.chapters.detector import Chapter
from app.tts.base import TTSProvider
from app.tts.chunker import split_text
from app.tts.narration import apply_pronunciation_dictionary_with_counts, prepare_for_narration
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.multivoice import synthesize_voice_set


@dataclass
class GenerationResult:
    chapter_number: int
    output_path: Path
    chunks_total: int
    chunks_completed: int


GENERATION_PIPELINE_VERSION = "2026-10-qwen3-story-expression-v6"

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


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Persist JSON without truncating the last good file if a write is interrupted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
        temp_name = None
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def save_state(chapter_dir: Path, state: dict) -> None:
    _atomic_write_json(state_path(chapter_dir), state)


def _provider_signature(provider: TTSProvider, voice: str | None, chunks: list[tuple[str, str | list[str] | None]]) -> str:
    custom = getattr(provider, "generation_signature", None)
    if callable(custom):
        base = custom()
    else:
        base = f"{provider.__class__.__module__}.{provider.__class__.__name__}:{voice or ''}"
    payload = {
        "pipeline": GENERATION_PIPELINE_VERSION,
        "base": base,
        "chunks": [(text, chunk_voice) for text, chunk_voice in chunks],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


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

    narration = prepare_for_narration(chapter.text)
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
        # Resolve saved dialogue offsets before replacements can change character counts.
        chunk_text, _rule_counts = apply_pronunciation_dictionary_with_counts(chunk_text, pronunciation_dictionary)
        paced_chunks = split_for_pacing(
            chunk_text,
            max_chars=int(getattr(provider, "recommended_chunk_chars", 1400)),
            max_sentences=int(getattr(provider, "recommended_chunk_sentences", 2)),
            split_on_expression_change=bool(getattr(provider, "split_on_expression_change", False)),
        )
        if not paced_chunks:
            continue
        chunks_with_voices.extend((item, chunk_voice) for item in paced_chunks)

    chunks = [item[0] for item in chunks_with_voices]
    if not chunks:
        raise ValueError(
            f"Chapter {chapter.number} \"{chapter.title}\" contains no readable text to synthesize."
        )

    # Persist a text-to-WAV manifest even when compatible chunks are reused.
    # Story-aware sound cues use each generated unit's real audio duration and
    # its source-text position rather than guessing from whole-chapter length.
    chunk_manifest = {
        "version": 1,
        "chapter": chapter.number,
        "title": chapter.title,
        "narration_speed": float(narration_speed),
        "pacing_profile": str(pacing_profile),
        "chunks": [
            {"index": index + 1, "file": f"{index + 1:05d}.wav", "text": item[0]}
            for index, item in enumerate(chunks_with_voices)
        ],
    }
    (chapter_dir / "chunk_manifest.json").write_text(
        json.dumps(chunk_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
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
        # Source text, voice, or narration settings changed. Old higher-index
        # WAVs must not leak into assembly, and the previously assembled
        # chapter must not be reused based only on modification timestamps.
        for cached_chunk in chunks_dir.glob("*.wav"):
            cached_chunk.unlink(missing_ok=True)
        for cache_name in ("chapter.m4a", ".audio-settings"):
            (chapter_dir / cache_name).unlink(missing_ok=True)
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
    persisted_indexes: set[int] = set()
    for value in state.get("completed") or []:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(chunks):
            persisted_indexes.add(index)

    invalid_cached_chunk = False
    for index in sorted(persisted_indexes):
        output = chunks_dir / f"{index + 1:05d}.wav"
        try:
            if not output.is_file() or output.stat().st_size < 1024:
                raise ValueError("cached audio chunk is missing or incomplete")
            with wave.open(str(output), "rb") as wav_file:
                if wav_file.getnframes() <= 0 or wav_file.getframerate() <= 0:
                    raise wave.Error("cached audio chunk has no readable audio frames")
        except (OSError, wave.Error, EOFError, ValueError):
            output.unlink(missing_ok=True)
            invalid_cached_chunk = True
            continue
        completed.add(index)

    if state.get("completed") != sorted(completed):
        state["completed"] = sorted(completed)
        save_state(chapter_dir, state)
    if invalid_cached_chunk:
        for cache_name in ("chapter.m4a", ".audio-settings"):
            (chapter_dir / cache_name).unlink(missing_ok=True)

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

    batch_provider = getattr(provider, "synthesize_batch", None)
    batch_size = max(1, int(getattr(provider, "recommended_batch_size", 1)))
    batch_disabled = False

    def validate_and_commit(index: int, output: Path, chunk: str) -> None:
        next_text = chunks[index + 1] if index + 1 < len(chunks) else None
        pause_ms = pause_after_ms(chunk, pacing_profile, next_text=next_text)
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
        if len(completed) % 4 == 0 or len(completed) == len(chunks):
            save_state(chapter_dir, state)
        if progress:
            progress(len(completed), len(chunks))

    index = 0
    while index < len(chunks):
        if index in completed and (chunks_dir / f"{index + 1:05d}.wav").exists():
            index += 1
            continue

        chunk_voice = chunks_with_voices[index][1]
        can_batch = (
            callable(batch_provider)
            and not batch_disabled
            and not isinstance(chunk_voice, list)
            and chunk_voice == voice
        )
        if can_batch:
            batch_indices = []
            probe = index
            while (
                probe < len(chunks)
                and len(batch_indices) < batch_size
            ):
                probe_voice = chunks_with_voices[probe][1]
                probe_output = chunks_dir / f"{probe + 1:05d}.wav"
                if probe in completed and probe_output.exists():
                    break
                if isinstance(probe_voice, list) or probe_voice != voice:
                    break
                batch_indices.append(probe)
                probe += 1

            if len(batch_indices) > 1:
                items = [
                    (
                        chunks[i],
                        chunks_dir / f"{i + 1:05d}.wav",
                    )
                    for i in batch_indices
                ]
                try:
                    batch_provider(items)
                except Exception as exc:
                    if "batch exceeded available GPU memory" in str(exc).casefold():
                        batch_disabled = True
                    else:
                        raise
                    for i in batch_indices:
                        output = chunks_dir / f"{i + 1:05d}.wav"
                        provider.synthesize(chunks[i], output, chunks_with_voices[i][1])
                for i in batch_indices:
                    validate_and_commit(i, chunks_dir / f"{i + 1:05d}.wav", chunks[i])
                index = batch_indices[-1] + 1
                continue

        filename = f"{index + 1:05d}.wav"
        output = chunks_dir / filename
        if index in completed and output.exists():
            index += 1
            continue

        if isinstance(chunk_voice, list):
            synthesize_voice_set(provider, chunks[index], chunk_voice, output)
        else:
            provider.synthesize(chunks[index], output, chunk_voice)

        validate_and_commit(index, output, chunks[index])
        index += 1

    state["completed"] = sorted(completed)
    save_state(chapter_dir, state)

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

