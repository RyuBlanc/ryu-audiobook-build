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


@dataclass
class GenerationSummary:
    chapters_total: int
    chapters_completed: int
    chapters_failed: list[int]
    output_path: Path | None = None
    cancelled: bool = False


class GenerationManager:
    def __init__(
        self,
        provider: TTSProvider,
        voice: str,
        chapters: list[Chapter],
        project_audio_root: Path,
        on_progress: Callable[[int, int, int, str], None] | None = None,
        on_finished: Callable[[GenerationSummary], None] | None = None,
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.chapters = chapters
        self.audio_root = project_audio_root
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.cancel_event = Event()
        self._thread: Thread | None = None
        self.failed: list[int] = []

    def start(
        self,
        output_path: Path | None = None,
        title: str = "Audiobook",
        author: str = "",
        cover: Path | None = None,
    ) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Generation is already running.")
        self.cancel_event.clear()
        self._thread = Thread(
            target=self._run,
            args=(output_path, title, author, cover),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _run(self, output_path: Path | None, title: str, author: str, cover: Path | None) -> None:
        # This directory is deliberately called working: it is not the user's
        # audiobook library and can be removed after a successful package build.
        self.audio_root.mkdir(parents=True, exist_ok=True)
        completed = 0
        self.failed = []
        cancelled = False

        for index, chapter in enumerate(self.chapters):
            if self.cancel_event.is_set():
                cancelled = True
                break
            try:
                result = generate_chapter(
                    chapter,
                    self.provider,
                    self.voice,
                    self.audio_root,
                    lambda done, total, i=index: self._progress(
                        i, len(self.chapters), done, total
                    ),
                )
                if result.chunks_completed != result.chunks_total:
                    raise RuntimeError("Chapter generation is incomplete.")
                completed += 1
                self._emit(index + 1, len(self.chapters), 1, "chapter-complete")
            except Exception as exc:
                self.failed.append(chapter.number)
                self._emit(index + 1, len(self.chapters), 0, f"chapter-failed: {exc}")

        final_output = None
        if not cancelled and not self.failed and completed == len(self.chapters) and output_path:
            try:
                cover = validate_cover(cover)
                chapter_dirs = [
                    self.audio_root / f"{c.number:03d}_{self._safe_title(c.title)}"
                    for c in self.chapters
                ]
                final_output = assemble_m4b(
                    chapter_dirs,
                    output_path,
                    sanitize_metadata(title, "Audiobook"),
                    sanitize_metadata(author),
                    cover,
                    [c.title for c in self.chapters],
                )
                self._emit(len(self.chapters), len(self.chapters), 1, "m4b-complete")
                # Only delete intermediate files after the final M4B has been
                # created and validated.
                self._clean_working_audio()
            except Exception as exc:
                self._emit(len(self.chapters), len(self.chapters), 0, f"m4b-failed: {exc}")

        summary = GenerationSummary(
            len(self.chapters),
            completed,
            list(self.failed),
            final_output,
            cancelled,
        )
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
        self._emit(chapter_index + 1, chapter_total, done, "chunk")

    def _emit(self, chapter: int, total: int, done: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(chapter, total, done, message)

    @staticmethod
    def _safe_title(value: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "chapter"
