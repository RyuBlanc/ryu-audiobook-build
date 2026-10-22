from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import wave

import imageio_ffmpeg

from app.tts.narration import apply_pronunciation_dictionary_with_counts, prepare_for_narration
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.base import TTSProvider
from app.tts.multivoice import synthesize_voice_set


@dataclass(frozen=True)
class PreviewResult:
    output_path: Path
    segments: int
    voices_used: tuple[str, ...]
    # Exact text represented by synthesized segments; used to align preview SFX.
    source_text: str = ""
    applied_rule_counts: dict[str, int] | None = None


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-2500:]
        raise RuntimeError(f"Preview audio processing failed. {detail}")


def _apply_speed(path: Path, speed: float) -> None:
    speed = max(0.5, min(2.0, float(speed)))
    if abs(speed - 1.0) < 0.001:
        return
    temp = path.with_suffix(".speed.wav")
    _run_ffmpeg([
        "-y", "-i", str(path),
        "-filter:a", f"atempo={speed:.3f}",
        "-c:a", "pcm_s16le",
        str(temp),
    ])
    temp.replace(path)


def _normalize(path: Path, output: Path) -> None:
    _run_ffmpeg([
        "-y", "-i", str(path),
        "-ar", "24000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output),
    ])


def _concat(inputs: list[Path], output: Path) -> None:
    list_file = output.with_suffix(".concat.txt")
    lines = []
    for item in inputs:
        escaped = str(item.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run_ffmpeg([
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:a", "pcm_s16le",
            str(output),
        ])
    finally:
        list_file.unlink(missing_ok=True)


def _preview_units(
    text: str,
    provider: TTSProvider,
    voice: str | None,
    pronunciation_dictionary: list[dict] | None,
    max_chars: int,
    dialogue_assignments=None,
    unit_rule_counts: list[dict[str, int]] | None = None,
) -> list[tuple[str, str | list[str] | None]]:
    narration = prepare_for_narration(text).narration_text

    if hasattr(provider, "split_for_cast"):
        try:
            raw = provider.split_for_cast(
                narration,
                voice,
                dialogue_assignments=dialogue_assignments,
            )
        except TypeError as exc:
            if "dialogue_assignments" not in str(exc):
                raise
            raw = provider.split_for_cast(narration, voice)
    else:
        raw = [(narration, voice)]

    units: list[tuple[str, str | list[str] | None]] = []
    used_chars = 0
    preview_unit_chars = 360
    preview_unit_sentences = 1
    # Short previews stay sentence-sized so a 20-second request does not
    # accidentally trigger a multi-minute synthesis unit.
    for segment, segment_voice in raw:
        for unit in split_for_pacing(
            segment,
            max_chars=preview_unit_chars,
            max_sentences=preview_unit_sentences,
        ):
            unit, rule_counts = apply_pronunciation_dictionary_with_counts(unit, pronunciation_dictionary)
            if unit_rule_counts is not None:
                unit_rule_counts.append(rule_counts)
            if used_chars >= max_chars:
                return units
            remaining = max_chars - used_chars
            if len(unit) > remaining and used_chars:
                # Never cut through a sentence merely to fill the preview.
                return units
            units.append((unit, segment_voice))
            used_chars += len(unit)
            if used_chars >= max_chars:
                return units
    return units


def build_voice_preview(
    text: str,
    provider: TTSProvider,
    voice: str | None,
    output_path: Path,
    pronunciation_dictionary: list[dict] | None = None,
    narration_speed: float = 0.90,
    pacing_profile: str = "natural",
    max_chars: int = 1400,
    dialogue_assignments=None,
    progress_callback=None,
    target_seconds: float | None = None,
) -> PreviewResult:
    if target_seconds is not None and float(target_seconds) > 0:
        # A character estimate is only a safety budget, not the preview's
        # stopping condition: fast local voices can render 1,400–1,800 characters
        # in about ten seconds. Capping source text to that default budget makes
        # a requested 30/60-second preview silently end too early.
        # Give the worker enough sentence-complete source for fast voices; the
        # measured WAV duration below remains the actual stopping condition.
        # Never read beyond the text the caller supplied.
        target_chars = int(float(target_seconds) * 240.0)
        effective_max_chars = min(
            len(text),
            max(int(max_chars), target_chars, 360),
        )
    else:
        effective_max_chars = int(max_chars)
    unit_rule_counts: list[dict[str, int]] = []
    applied_rule_counts: dict[str, int] = {}
    units = _preview_units(
        text,
        provider,
        voice,
        pronunciation_dictionary,
        max_chars=effective_max_chars,
        dialogue_assignments=dialogue_assignments,
        unit_rule_counts=unit_rule_counts,
    )
    if not units:
        raise ValueError("The selected chapter does not contain enough readable text for a preview.")

    total_units = len(units)

    def report(stage: str, current: int, total: int = total_units) -> None:
        if callable(progress_callback):
            try:
                progress_callback(stage, int(current), max(1, int(total)))
            except Exception:
                pass

    report("preparing", 0, total_units)
    target = max(0.0, float(target_seconds or 0.0))
    accumulated_seconds = 0.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    configure_narration = getattr(provider, "configure_narration", None)
    if callable(configure_narration):
        configure_narration(narration_speed, pacing_profile)
    provider_handles_controls = bool(getattr(provider, "handles_narration_controls", False))
    voices_used: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ryu-preview-") as temp_dir:
        root = Path(temp_dir)
        normalized: list[Path] = []

        generated_segments = 0
        generated_text: list[str] = []
        for index, (unit, unit_voice) in enumerate(units):
            report("synthesizing", index, total_units)
            raw_path = root / f"{index:03d}.wav"
            normalized_path = root / f"{index:03d}-normalized.wav"
            if isinstance(unit_voice, list):
                synthesize_voice_set(provider, unit, unit_voice, raw_path)
            else:
                provider.synthesize(unit, raw_path, unit_voice)
            if not provider_handles_controls:
                _apply_speed(raw_path, narration_speed)
                next_text = units[index + 1][0] if index + 1 < len(units) else None
                pause_ms = pause_after_ms(unit, pacing_profile, next_text=next_text)
                if pause_ms:
                    append_silence(raw_path, pause_ms)
            _normalize(raw_path, normalized_path)
            normalized.append(normalized_path)
            generated_text.append(unit)
            for written, count in (unit_rule_counts[index] if index < len(unit_rule_counts) else {}).items():
                applied_rule_counts[written] = applied_rule_counts.get(written, 0) + count
            generated_segments += 1
            if unit_voice:
                voices_used.append(str(unit_voice))
            try:
                with wave.open(str(normalized_path), "rb") as reader:
                    frames = reader.getnframes()
                    rate = max(1, reader.getframerate())
                    accumulated_seconds += frames / float(rate)
            except (OSError, wave.Error):
                pass
            report("synthesizing", index + 1, total_units)
            if target > 0 and accumulated_seconds >= target:
                break

        report("finalizing", 0, 1)
        _concat(normalized, output_path)
        report("finalizing", 1, 1)

    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise RuntimeError("The voice preview was not created correctly.")

    return PreviewResult(
        output_path=output_path,
        segments=generated_segments,
        voices_used=tuple(dict.fromkeys(voices_used)),
        source_text="\n".join(generated_text),
        applied_rule_counts=applied_rule_counts,
    )
