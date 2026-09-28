from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Thread, Event
from typing import Callable
import shutil

from app.audio.assembler import assemble_m4b
from app.audio.metadata import sanitize_metadata, validate_cover
from app.chapters.detector import Chapter
from app.tts.base import TTSProvider
from app.tts.generator import generate_chapter
from app.tts.chunker import split_text
from app.tts.narration import prepare_for_narration


@dataclass
class GenerationSummary:
    chapters_total: int
    chapters_completed: int
    chapters_failed: list[int]
    chapters_completed_numbers: list[int] | None = None
    failure_details: dict[int, str] | None = None
    output_path: Path | None = None
    cancelled: bool = False
    packaging_failed: bool = False
    packaging_error: str | None = None


class GenerationManager:
    def __init__(
        self,
        provider: TTSProvider,
        voice: str,
        chapters: list[Chapter],
        project_audio_root: Path,
        on_progress: Callable[[int, int, int, str], None] | None = None,
        on_finished: Callable[[GenerationSummary], None] | None = None,
        pronunciation_dictionary: list[dict] | None = None,
        narration_speed: float = 0.90,
        pacing_profile: str = "natural",
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.chapters = chapters
        self.audio_root = project_audio_root
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.pronunciation_dictionary = pronunciation_dictionary or []
        self.narration_speed = narration_speed
        self.pacing_profile = pacing_profile
        self.metadata = metadata or {}
        self.cancel_event = Event()
        self._thread: Thread | None = None
        self.failed: list[int] = []
        self.failure_details: dict[int, str] = {}
        self._chunk_offsets: list[int] = []
        self._total_chunks = 0

    def start(
        self,
        output_path: Path | None = None,
        title: str = "Audiobook",
        author: str = "",
        cover: Path | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Generation is already running.")
        self.cancel_event.clear()
        effective_metadata = dict(self.metadata)
        if metadata:
            effective_metadata.update(metadata)
        self._thread = Thread(
            target=self._run,
            args=(output_path, title, author, cover, effective_metadata),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _run(self, output_path: Path | None, title: str, author: str, cover: Path | None, metadata: dict[str, str]) -> None:
        # This directory is deliberately called working: it is not the user's
        # audiobook library and can be removed after a successful package build.
        self.audio_root.mkdir(parents=True, exist_ok=True)
        completed = 0
        self.failed = []
        self.failure_details = {}
        self._chunk_offsets = []
        offset = 0
        for chapter in self.chapters:
            self._chunk_offsets.append(offset)
            narration_text = prepare_for_narration(
                chapter.text,
                self.pronunciation_dictionary,
            ).narration_text
            if hasattr(self.provider, "split_for_cast"):
                raw_parts = self.provider.split_for_cast(narration_text, self.voice)
            else:
                raw_parts = [(chunk, self.voice) for chunk in split_text(narration_text)]
            from app.tts.pacing import split_for_pacing
            for part, _part_voice in raw_parts:
                offset += len(split_for_pacing(part))
        self._total_chunks = offset
        generated_chapter_dirs: list[Path] = []
        completed_numbers: list[int] = []
        self._emit(0, len(self.chapters), 0, f"plan:{self._total_chunks}")
        cancelled = False
        packaging_failed = False
        packaging_error = None

        for index, chapter in enumerate(self.chapters):
            if self.cancel_event.is_set():
                cancelled = True
                break
            try:
                self._emit(
                    index + 1,
                    len(self.chapters),
                    offset,
                    f"chunk-start:{offset + 1}/{max(1, self._total_chunks)}",
                )
                result = generate_chapter(
                    chapter,
                    self.provider,
                    self.voice,
                    self.audio_root,
                    lambda done, total, i=index: self._progress(
                        i, len(self.chapters), done, total
                    ),
                    pronunciation_dictionary=self.pronunciation_dictionary,
                    narration_speed=self.narration_speed,
                    pacing_profile=self.pacing_profile,
                )
                if result.chunks_completed != result.chunks_total:
                    raise RuntimeError("Chapter generation is incomplete.")
                completed += 1
                completed_numbers.append(chapter.number)
                generated_chapter_dirs.append(result.output_path)
                self._emit(index + 1, len(self.chapters), 1, "chapter-complete")
            except Exception as exc:
                self.failed.append(chapter.number)
                self.failure_details[chapter.number] = str(exc)
                self._emit(index + 1, len(self.chapters), 0, f"chapter-failed: {exc}")

        final_output = None
        if not cancelled and not self.failed and completed == len(self.chapters) and output_path:
            try:
                cover = validate_cover(cover)
                # Use the exact directories returned by chapter generation.
                # Reconstructing them from chapter titles can diverge from
                # generator sanitization and cause false "No audio chunks" errors.
                if len(generated_chapter_dirs) != len(self.chapters):
                    raise RuntimeError("Chapter generation completed, but the generated audio directory list is incomplete.")
                final_output = assemble_m4b(
                    generated_chapter_dirs,
                    output_path,
                    sanitize_metadata(title, "Audiobook"),
                    sanitize_metadata(author),
                    cover,
                    [c.title for c in self.chapters],
                    metadata=metadata,
                )
                self._emit(len(self.chapters), len(self.chapters), 1, "m4b-complete")
                # Only delete intermediate files after the final M4B has been
                # created and validated.
                self._clean_working_audio()
            except Exception as exc:
                packaging_failed = True
                packaging_error = str(exc)
                self._emit(len(self.chapters), len(self.chapters), 0, f"m4b-failed: {exc}")

        summary = GenerationSummary(
            len(self.chapters),
            completed,
            list(self.failed),
            completed_numbers,
            self.failure_details,
            final_output,
            cancelled,
            packaging_failed,
            packaging_error,
        )
        close = getattr(self.provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        if self.on_finished:
            self.on_finished(summary)

    def _clean_working_audio(self) -> None:
        if self.audio_root.exists():
            for child in self.audio_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                elif child.is_file():
                    try:
                        child.unlink()
                    except OSError:
                        pass

    def _progress(self, chapter_index: int, chapter_total: int, done: int, total: int) -> None:
        offset = self._chunk_offsets[chapter_index] if chapter_index < len(self._chunk_offsets) else 0
        overall_done = offset + done
        self._emit(
            chapter_index + 1,
            chapter_total,
            overall_done,
            f"chunk:{overall_done}/{max(1, self._total_chunks)}",
        )

    def _emit(self, chapter: int, total: int, done: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(chapter, total, done, message)

    @staticmethod
    def _safe_title(value: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "chapter"
