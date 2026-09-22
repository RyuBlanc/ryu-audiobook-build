from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Thread, Event
from typing import Callable

from app.audio.assembler import assemble_m4b
from app.audio.inspect import validate_audio_file
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

    def start(self, output_path: Path | None = None, title: str = "Audiobook", author: str = "", cover: Path | None = None) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Generation is already running.")
        self.cancel_event.clear()
        self._thread = Thread(target=self._run, args=(output_path, title, author, cover), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _run(self, output_path: Path | None, title: str, author: str, cover: Path | None) -> None:
        self.audio_root.mkdir(parents=True, exist_ok=True)
        completed = 0
        self.failed = []

        for index, chapter in enumerate(self.chapters):
            if self.cancel_event.is_set():
                break
            try:
                chapter_root = self.audio_root / f"{chapter.number:03d}"
                result = generate_chapter(
                    chapter,
                    self.provider,
                    self.voice,
                    self.audio_root,
                    progress=lambda done, total, i=index: self._progress(i, len(self.chapters), done, total),
                )
                if result.chunks_completed != result.chunks_total:
                    raise RuntimeError("Chapter generation is incomplete.")
                completed += 1
                if self.on_progress:
                    self.on_progress(index + 1, len(self.chapters), 1, "chapter-complete")
            except Exception:
                self.failed.append(chapter.number)
                if self.on_progress:
                    self.on_progress(index + 1, len(self.chapters), 0, "chapter-failed")

        final_output = None
        if not self.cancel_event.is_set() and not self.failed and completed == len(self.chapters) and output_path:
            cover = validate_cover(cover)
            chapter_dirs = [
                self.audio_root / f"{chapter.number:03d}_{self._safe_title(chapter.title)}"
                for chapter in self.chapters
            ]
            final_output = assemble_m4b(
                chapter_dirs,
                output_path,
                sanitize_metadata(title, "Audiobook"),
                sanitize_metadata(author),
                cover,
            )

        summary = GenerationSummary(len(self.chapters), completed, list(self.failed), final_output)
        if self.on_finished:
            self.on_finished(summary)

    def _progress(self, chapter_index: int, chapter_total: int, done: int, total: int) -> None:
        if self.on_progress:
            self.on_progress(chapter_index + 1, chapter_total, done, total)

    @staticmethod
    def _safe_title(value: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "chapter"
