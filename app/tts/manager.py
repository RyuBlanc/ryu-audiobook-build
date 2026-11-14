from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Thread, Event
import time
import re
from typing import Callable
import shutil
import wave

from app.audio.assembler import assemble_m4b
from app.audio.metadata import sanitize_metadata, validate_cover
from app.chapters.detector import Chapter
from app.tts.base import TTSProvider
from app.tts.generator import generate_chapter
from app.tts.chunker import split_text
from app.tts.narration import apply_pronunciation_dictionary_with_counts, prepare_for_narration


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
        bitrate: int | str | None = 256,
        background_audio_path: Path | None = None,
        background_audio_volume: float = 0.18,
        narration_volume: float = 1.0,
        cue_audio_volume: float = 0.25,
        ambience_audio_path: Path | None = None,
        ambience_audio_volume: float = 0.10,
        background_audio_fade_in: float = 2.0,
        background_audio_fade_out: float = 3.0,
        background_audio_mode: str = "manual",
        auto_music_style: str = "auto",
        auto_music_variation: int | str | Path | None = None,
        chapter_transition_sound: bool = False,
        story_effects_enabled: bool = False,
        story_effect_volume: float = 0.22,
        sound_cue_style: str = "classic-book",
        opening_cue_path: Path | None = None,
        page_turn_cue_path: Path | None = None,
        ending_cue_path: Path | None = None,
        scene_transition_cue_path: Path | None = None,
        chapter_bgm_overrides: dict[str, dict] | None = None,
        chapter_bgm_strategy: str | None = None,
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
        self.bitrate = bitrate
        self.background_audio_path = Path(background_audio_path) if background_audio_path else None
        self.background_audio_volume = max(0.0, min(0.50, float(background_audio_volume)))
        self.narration_volume = max(0.0, min(1.0, float(narration_volume)))
        self.cue_audio_volume = max(0.0, min(0.50, float(cue_audio_volume)))
        self.ambience_audio_path = Path(ambience_audio_path) if ambience_audio_path else None
        self.ambience_audio_volume = max(0.0, min(1.0, float(ambience_audio_volume)))
        self.background_audio_fade_in = max(0.0, min(30.0, float(background_audio_fade_in)))
        self.background_audio_fade_out = max(0.0, min(30.0, float(background_audio_fade_out)))
        self.background_audio_mode = str(background_audio_mode or "manual").casefold()
        self.auto_music_style = str(auto_music_style or "auto")
        if auto_music_variation is None:
            self.auto_music_variation = None
        else:
            try:
                self.auto_music_variation = int(auto_music_variation)
            except (TypeError, ValueError):
                self.auto_music_variation = str(auto_music_variation)
        self.chapter_transition_sound = bool(chapter_transition_sound)
        self.story_effects_enabled = bool(story_effects_enabled)
        self.story_effect_volume = max(0.0, min(0.50, float(story_effect_volume)))
        self.sound_cue_style = str(sound_cue_style or "classic-book")
        self.opening_cue_path = Path(opening_cue_path) if opening_cue_path else None
        self.page_turn_cue_path = Path(page_turn_cue_path) if page_turn_cue_path else None
        self.ending_cue_path = Path(ending_cue_path) if ending_cue_path else None
        # scene_transition_cue_path remains accepted as a legacy no-op argument.
        self.chapter_bgm_overrides = dict(chapter_bgm_overrides or {})
        raw_bgm_strategy = str(
            chapter_bgm_strategy if chapter_bgm_strategy is not None
            else ("custom" if self.chapter_bgm_overrides else "same")
        ).strip().casefold()
        if raw_bgm_strategy in {"same", "same-bgm", "same_bgm"}:
            self.chapter_bgm_strategy = "same"
        elif raw_bgm_strategy in {"custom", "chapter-based", "chapter_based", "chapter"}:
            self.chapter_bgm_strategy = "chapter-based"
        else:
            raise ValueError(f"Unsupported chapter BGM strategy: {chapter_bgm_strategy}")
        self.cancel_event = Event()
        self.pause_event = Event()
        self._thread: Thread | None = None
        self.failed: list[int] = []
        self.failure_details: dict[int, str] = {}
        self._completed_numbers: list[int] = []
        self._finished_callback_called = False
        self._chunk_offsets: list[int] = []
        self._chunk_work_offsets: list[int] = []
        self._chapter_work_units: list[list[int]] = []
        self._total_chunks = 0
        self._total_work_units = 0
        self.pronunciation_rule_counts: dict[str, int] = {}
        self._completed_chapter_audio_seconds: dict[int, float] = {}

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
        if not self.chapters:
            raise ValueError("No chapters are available for generation. Import a book or restore its chapters, then retry.")
        empty_chapters = [
            chapter for chapter in self.chapters
            if not str(getattr(chapter, "text", "") or "").strip()
        ]
        if empty_chapters:
            numbers = ", ".join(
                str(getattr(chapter, "number", index + 1))
                for index, chapter in enumerate(self.chapters)
                if chapter in empty_chapters
            )
            if len(empty_chapters) == len(self.chapters):
                raise ValueError(
                    "All chapters are empty. Add or restore chapter text, or exclude the empty chapters "
                    "from generation before retrying."
                )
            raise ValueError(
                f"Cannot start audiobook generation because chapter(s) {numbers} are empty. "
                "Review those chapters, restore their text, or mark them to skip before retrying. "
                "No audio was generated."
            )
        self.cancel_event.clear()
        self.pause_event.clear()
        self.failed = []
        self.failure_details = {}
        self._completed_numbers = []
        self._finished_callback_called = False
        effective_metadata = dict(self.metadata)
        if metadata:
            effective_metadata.update(metadata)
        self._thread = Thread(
            target=self._run,
            args=(output_path, title, author, cover, effective_metadata),
            daemon=True,
        )
        self._thread.start()

    def pause(self) -> None:
        """Pause at the next persisted chunk/batch boundary; never interrupt synthesis."""
        if self._thread and self._thread.is_alive():
            self.pause_event.set()

    def resume(self) -> None:
        """Continue a generation paused at a persisted chunk/batch checkpoint."""
        self.pause_event.clear()

    def _wait_if_paused(self, chapter: int, total: int) -> bool:
        notified = False
        while self.pause_event.is_set() and not self.cancel_event.is_set():
            if not notified:
                self._emit(
                    chapter,
                    total,
                    0,
                    "paused:Generation paused at a saved chunk/batch checkpoint. Resume to continue.",
                )
                notified = True
            time.sleep(0.15)
        return self.cancel_event.is_set()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.pause_event.clear()
        provider = self.provider
        cancel = getattr(provider, "request_cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass
            return
        # Avoid blocking the main window on providers whose close operation
        # waits for network/process shutdown. The generation thread performs
        # final cleanup after synthesis unwinds.
        close = getattr(provider, "close", None)
        if callable(close):
            Thread(target=close, name="RyuTTSCancelCleanup", daemon=True).start()

    def _run(self, output_path: Path | None, title: str, author: str, cover: Path | None, metadata: dict[str, str]) -> None:
        """Ensure unexpected worker failures become a terminal job result."""
        try:
            self._run_body(output_path, title, author, cover, metadata)
        except Exception as exc:
            message = f"Generation aborted unexpectedly: {exc}"
            try:
                self._emit(0, len(self.chapters), 0, f"fatal:{message}")
            except Exception:
                pass
            close = getattr(self.provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            if not self._finished_callback_called and self.on_finished:
                completed_numbers = list(self._completed_numbers)
                completed_set = set(completed_numbers)
                failed = list(self.failed)
                failed_set = set(failed)
                for chapter in self.chapters:
                    number = int(getattr(chapter, "number", 0) or 0)
                    if number not in completed_set and number not in failed_set:
                        failed.append(number)
                        self.failure_details.setdefault(number, message)
                summary = GenerationSummary(
                    chapters_total=len(self.chapters),
                    chapters_completed=len(completed_numbers),
                    chapters_failed=failed,
                    chapters_completed_numbers=completed_numbers,
                    failure_details=dict(self.failure_details),
                    output_path=None,
                    cancelled=self.cancel_event.is_set(),
                    packaging_failed=bool(output_path and len(completed_numbers) == len(self.chapters)),
                    packaging_error=message if output_path and len(completed_numbers) == len(self.chapters) else None,
                )
                self._finished_callback_called = True
                try:
                    self.on_finished(summary)
                except Exception:
                    pass

    def _chapter_requires_paragraph_boundary(self, chapter: Chapter) -> bool:
        if self.chapter_bgm_strategy != "chapter-based":
            return False
        override = self.chapter_bgm_overrides.get(str(getattr(chapter, "chapter_id", "") or ""), {})
        if not isinstance(override, dict) or not override:
            override = self.chapter_bgm_overrides.get(str(chapter.number), {})
        return bool(
            isinstance(override, dict)
            and str(override.get("rule") or "").casefold() == "custom"
            and str(override.get("start_offset") or "immediate").casefold() == "after_first_paragraph"
        )

    def _run_body(self, output_path: Path | None, title: str, author: str, cover: Path | None, metadata: dict[str, str]) -> None:
        # Keep this project-local directory as a reusable synthesis checkpoint.
        # Sound-design-only changes must be able to reassemble the book without
        # repeating expensive narration synthesis, and full-book mix preview
        # consumes the same saved chapter narration.
        self.audio_root.mkdir(parents=True, exist_ok=True)
        completed = 0
        self.failed = []
        self.failure_details = {}
        self._chunk_offsets = []
        self._chunk_work_offsets = []
        self._chapter_work_units = []
        self._completed_chapter_audio_seconds = {}
        offset = 0
        work_offset = 0
        for chapter in self.chapters:
            self._chunk_offsets.append(offset)
            self._chunk_work_offsets.append(work_offset)
            narration_text = prepare_for_narration(chapter.text).narration_text
            if hasattr(self.provider, "split_for_cast"):
                try:
                    raw_parts = self.provider.split_for_cast(
                        narration_text,
                        self.voice,
                        dialogue_assignments=getattr(chapter, "dialogue_assignments", []),
                    )
                except TypeError as exc:
                    if "dialogue_assignments" not in str(exc):
                        raise
                    raw_parts = self.provider.split_for_cast(narration_text, self.voice)
            else:
                raw_parts = [(chunk, self.voice) for chunk in split_text(narration_text)]
            from app.tts.pacing import split_for_pacing
            chapter_units: list[int] = []
            preserve_paragraph_boundaries = self._chapter_requires_paragraph_boundary(chapter)
            first_paragraph = re.split(r"\r?\n[ \t]*\r?\n+", narration_text, maxsplit=1)[0]
            first_paragraph_chars = len(" ".join(first_paragraph.split()))
            consumed_source_chars = 0
            for part, _part_voice in raw_parts:
                normalized_part = " ".join(str(part).split())
                consumed_source_chars += len(normalized_part) + (1 if consumed_source_chars else 0)
                preserve_this_part = bool(
                    preserve_paragraph_boundaries and consumed_source_chars >= first_paragraph_chars
                )
                for paced in split_for_pacing(
                    part,
                    max_chars=int(getattr(self.provider, "recommended_chunk_chars", 1400)),
                    max_sentences=int(getattr(self.provider, "recommended_chunk_sentences", 2)),
                    split_on_expression_change=bool(getattr(self.provider, "split_on_expression_change", False)),
                    force_paragraph_boundaries=preserve_this_part,
                ):
                    paced, rule_counts = apply_pronunciation_dictionary_with_counts(paced, self.pronunciation_dictionary)
                    for written, count in rule_counts.items():
                        self.pronunciation_rule_counts[written] = self.pronunciation_rule_counts.get(written, 0) + count
                    unit = max(1, len(paced))
                    chapter_units.append(unit)
                    offset += 1
                    work_offset += unit
            self._chapter_work_units.append(chapter_units)
        self._total_chunks = offset
        self._total_work_units = max(1, work_offset)
        generated_chapter_dirs: list[Path] = []
        completed_numbers: list[int] = []
        self._emit(0, len(self.chapters), 0, f"plan:{self._total_work_units}:0:{self._total_chunks}")
        if self.pronunciation_rule_counts:
            total_replacements = sum(self.pronunciation_rule_counts.values())
            self._emit(0, len(self.chapters), 0, f"pronunciation:{total_replacements}:{len(self.pronunciation_rule_counts)}")
        cancelled = False
        packaging_failed = False
        packaging_error = None

        for index, chapter in enumerate(self.chapters):
            if self._wait_if_paused(index + 1, len(self.chapters)):
                cancelled = True
                break
            if self.cancel_event.is_set():
                cancelled = True
                break
            try:
                chapter_offset = self._chunk_offsets[index] if index < len(self._chunk_offsets) else 0
                set_status = getattr(self.provider, "set_status_callback", None)
                if callable(set_status):
                    set_status(
                        lambda message, chapter_index=index: self._emit(
                            chapter_index + 1,
                            len(self.chapters),
                            0,
                            f"provider:{message}",
                        )
                    )
                self._emit(
                    index + 1,
                    len(self.chapters),
                    chapter_offset,
                    f"chunk-start:{chapter_offset + 1}/{max(1, self._total_chunks)}",
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
                    preserve_paragraph_boundaries=self._chapter_requires_paragraph_boundary(chapter),
                    checkpoint_callback=lambda _done, _total, chapter_index=index: self._wait_if_paused(
                        chapter_index + 1, len(self.chapters)
                    ),
                    on_chunk_timing=lambda completed_chunks, work_units, elapsed_seconds, chapter_index=index: self._chunk_timing(
                        chapter_index, completed_chunks, work_units, elapsed_seconds
                    ),
                )
                if self.cancel_event.is_set():
                    cancelled = True
                    break
                if result.chunks_completed != result.chunks_total:
                    raise RuntimeError("Chapter generation is incomplete.")
                completed += 1
                completed_numbers.append(chapter.number)
                self._completed_numbers = list(completed_numbers)
                generated_chapter_dirs.append(result.output_path)
                measured_chapter_seconds = self._measure_chapter_audio_seconds(result.output_path)
                self._completed_chapter_audio_seconds[int(chapter.number)] = measured_chapter_seconds
                measured_book_seconds = sum(self._completed_chapter_audio_seconds.values())
                chapter_units = self._chapter_work_units[index] if index < len(self._chapter_work_units) else []
                completed_units = sum(chapter_units[: result.chunks_completed])
                overall_work = (
                    (self._chunk_work_offsets[index] if index < len(self._chunk_work_offsets) else 0)
                    + completed_units
                )
                self._emit(
                    index + 1,
                    len(self.chapters),
                    overall_work,
                    (
                        f"chapter-complete:{result.chunks_completed}/{result.chunks_total}:"
                        f"{measured_chapter_seconds:.3f}:{measured_book_seconds:.3f}"
                    ),
                )
            except Exception as exc:
                if self.cancel_event.is_set():
                    cancelled = True
                    break
                self.failed.append(chapter.number)
                self.failure_details[chapter.number] = str(exc)
                self._emit(index + 1, len(self.chapters), 0, f"chapter-failed: {exc}")
                if getattr(self.provider, "stop_on_failure", False):
                    self._emit(index + 1, len(self.chapters), 0, "provider-unavailable")
                    break

                # A network-wide online TTS outage will fail every remaining
                # chapter too. Stop here instead of repeating the same DNS/
                # connection failure for the rest of the book.
                if exc.__class__.__name__ == "OnlineTTSNetworkError":
                    for remaining in self.chapters[index + 1:]:
                        self.failed.append(remaining.number)
                        self.failure_details[remaining.number] = (
                            "Skipped because the online voice service is unreachable."
                        )
                    break

        # Cancellation can arrive while the final chapter is rendering. Recheck
        # before starting the expensive full-book encode so a late cancel request
        # does not package a book after the user asked to stop.
        if self.cancel_event.is_set():
            cancelled = True
        if not cancelled and self._wait_if_paused(len(self.chapters), len(self.chapters)):
            cancelled = True

        final_output = None
        if not cancelled and not self.failed and completed == len(self.chapters) and output_path:
            try:
                self._emit(len(self.chapters), len(self.chapters), self._total_chunks, "m4b-packaging")
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
                    progress=lambda done, total, message: self._package_progress(done, total, message),
                    bitrate=self.bitrate,
                    narration_speed=self.narration_speed,
                    background_audio_path=self.background_audio_path,
                    background_audio_volume=self.background_audio_volume,
                    narration_volume=self.narration_volume,
                    cue_audio_volume=self.cue_audio_volume,
                    ambience_audio_path=self.ambience_audio_path,
                    ambience_audio_volume=self.ambience_audio_volume,
                    background_audio_fade_in=self.background_audio_fade_in,
                    background_audio_fade_out=self.background_audio_fade_out,
                    background_audio_mode=self.background_audio_mode,
                    auto_music_style=self.auto_music_style,
                    auto_music_variation=self.auto_music_variation,
                    chapter_transition_sound=self.chapter_transition_sound,
                    story_effects_enabled=self.story_effects_enabled,
                    story_effect_volume=self.story_effect_volume,
                    sound_cue_style=self.sound_cue_style,
                    opening_cue_path=self.opening_cue_path,
                    page_turn_cue_path=self.page_turn_cue_path,
                    ending_cue_path=self.ending_cue_path,
                    chapter_bgm_overrides=self.chapter_bgm_overrides,
                    chapter_bgm_strategy=self.chapter_bgm_strategy,
                )
                self._emit(len(self.chapters), len(self.chapters), 1, "m4b-complete")
                # Preserve per-chapter WAVs, manifests and signatures after a
                # successful package. Later mix previews and sound-design-only
                # reassembly must reuse this narration without a new TTS pass.
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
        self._finished_callback_called = True
        if self.on_finished:
            self.on_finished(summary)

    @staticmethod
    def _measure_chapter_audio_seconds(chapter_output: Path) -> float:
        """Measure committed PCM chunk durations from their WAV headers."""
        chunks_dir = Path(chapter_output) / "chunks"
        if not chunks_dir.is_dir():
            return 0.0
        total = 0.0
        for chunk_path in sorted(chunks_dir.glob("*.wav")):
            try:
                with wave.open(str(chunk_path), "rb") as wav_file:
                    total += wav_file.getnframes() / float(max(1, wav_file.getframerate()))
            except (OSError, wave.Error):
                continue
        return round(total, 3)

    def _package_progress(self, done: int, total: int, message: str) -> None:
        self._emit(
            len(self.chapters),
            len(self.chapters),
            self._total_work_units,
            f"m4b-package:{done}/{max(1, total)}:{message}",
        )

    def _clean_working_audio(self) -> None:
        """Explicit destructive cleanup; never called as part of successful export."""
        if self.audio_root.exists():
            for child in self.audio_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                elif child.is_file():
                    try:
                        child.unlink()
                    except OSError:
                        pass

    def _chunk_timing(
        self,
        chapter_index: int,
        completed_chunks: int,
        work_units: int,
        elapsed_seconds: float,
    ) -> None:
        """Publish the measured wall time of an actual TTS synthesis call."""
        chunk_offset = self._chunk_offsets[chapter_index] if chapter_index < len(self._chunk_offsets) else 0
        work_offset = self._chunk_work_offsets[chapter_index] if chapter_index < len(self._chunk_work_offsets) else 0
        units = self._chapter_work_units[chapter_index] if chapter_index < len(self._chapter_work_units) else []
        completed_work = sum(units[: max(0, min(completed_chunks, len(units)))])
        overall_work = work_offset + completed_work
        overall_chunk = chunk_offset + max(0, completed_chunks)
        self._emit(
            chapter_index + 1,
            len(self.chapters),
            overall_work,
            (
                f"chunk-timing:{max(1, int(work_units))}:{max(0.001, float(elapsed_seconds)):.6f}:"
                f"{overall_work}:{max(1, self._total_work_units)}:"
                f"{overall_chunk}:{max(1, self._total_chunks)}"
            ),
        )

    def _progress(self, chapter_index: int, chapter_total: int, done: int, total: int) -> None:
        chunk_offset = self._chunk_offsets[chapter_index] if chapter_index < len(self._chunk_offsets) else 0
        work_offset = self._chunk_work_offsets[chapter_index] if chapter_index < len(self._chunk_work_offsets) else 0
        units = self._chapter_work_units[chapter_index] if chapter_index < len(self._chapter_work_units) else []
        completed_work = sum(units[: max(0, min(done, len(units)))])
        overall_work = work_offset + completed_work
        overall_chunk = chunk_offset + done
        self._emit(
            chapter_index + 1,
            chapter_total,
            overall_work,
            f"chunk:{overall_chunk}/{max(1, self._total_chunks)}:{overall_work}/{max(1, self._total_work_units)}",
        )

    def _emit(self, chapter: int, total: int, done: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(chapter, total, done, message)

    @staticmethod
    def _safe_title(value: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "chapter"