from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile

import imageio_ffmpeg

from app.tts.narration import prepare_for_narration
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.base import TTSProvider


@dataclass(frozen=True)
class PreviewResult:
    output_path: Path
    segments: int
    voices_used: tuple[str, ...]


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
) -> list[tuple[str, str | None]]:
    narration = prepare_for_narration(
        text,
        pronunciation_dictionary=pronunciation_dictionary,
    ).narration_text

    if hasattr(provider, "split_for_cast"):
        raw = provider.split_for_cast(narration, voice)
    else:
        raw = [(narration, voice)]

    units: list[tuple[str, str | None]] = []
    used_chars = 0
    for segment, segment_voice in raw:
        for unit in split_for_pacing(segment, max_chars=900, max_sentences=2):
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
) -> PreviewResult:
    units = _preview_units(
        text,
        provider,
        voice,
        pronunciation_dictionary,
        max_chars=max_chars,
    )
    if not units:
        raise ValueError("The selected chapter does not contain enough readable text for a preview.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    configure_narration = getattr(provider, "configure_narration", None)
    if callable(configure_narration):
        configure_narration(narration_speed, pacing_profile)
    provider_handles_controls = bool(getattr(provider, "handles_narration_controls", False))
    voices_used: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ryu-preview-") as temp_dir:
        root = Path(temp_dir)
        normalized: list[Path] = []

        for index, (unit, unit_voice) in enumerate(units):
            raw_path = root / f"{index:03d}.wav"
            normalized_path = root / f"{index:03d}-normalized.wav"
            provider.synthesize(unit, raw_path, unit_voice)
            if not provider_handles_controls:
                _apply_speed(raw_path, narration_speed)
                pause_ms = pause_after_ms(unit, pacing_profile)
                if pause_ms:
                    append_silence(raw_path, pause_ms)
            _normalize(raw_path, normalized_path)
            normalized.append(normalized_path)
            if unit_voice:
                voices_used.append(str(unit_voice))

        _concat(normalized, output_path)

    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise RuntimeError("The voice preview was not created correctly.")

    return PreviewResult(
        output_path=output_path,
        segments=len(units),
        voices_used=tuple(dict.fromkeys(voices_used)),
    )
