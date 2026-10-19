"""Focused regressions for requested voice-preview duration.

These tests use a deterministic local WAV provider so the duration-budget
behavior can be checked without depending on a network TTS service or model.
"""
import math
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from app.tts.preview import build_voice_preview


def _write_tone(path: Path, seconds: float = 0.30) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 8000
    frames = max(1, int(rate * seconds))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        pcm = bytearray()
        for i in range(frames):
            sample = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            pcm.extend(sample.to_bytes(2, "little", signed=True))
        wav.writeframes(bytes(pcm))


def _copy_normalized(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def _concat_wavs(paths: list[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]
    for path in paths[1:]:
        with wave.open(str(path), "rb") as wav:
            if wav.getparams()[:3] != params[:3]:
                raise AssertionError("Preview segment WAV parameters changed unexpectedly")
            frames.append(wav.readframes(wav.getnframes()))
    with wave.open(str(destination), "wb") as output:
        output.setparams(params)
        for chunk in frames:
            output.writeframes(chunk)


class PreviewDurationAcceptanceTests:
    def test_requested_30_second_preview_does_not_stop_at_default_character_budget(self):
        class FastLocalProvider:
            def __init__(self):
                self.calls = 0

            def synthesize(self, text, output_path, voice=None):
                self.calls += 1
                _write_tone(Path(output_path), 0.30)

        # Longer than the old default 1,400-character cap. At 0.30 seconds
        # per sentence, that old cap produces roughly ten seconds of audio;
        # the requested 30-second budget must allow enough source text.
        text = " ".join(
            f"Sentence {number} contains enough words for the preview duration test."
            for number in range(1, 220)
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "preview-30-seconds.wav"
            provider = FastLocalProvider()
            with patch("app.tts.preview._normalize", side_effect=_copy_normalized), patch(
                "app.tts.preview._concat", side_effect=_concat_wavs
            ):
                result = build_voice_preview(
                    text,
                    provider,
                    "Narrator",
                    output,
                    narration_speed=1.0,
                    pacing_profile="off",
                    max_chars=1400,
                    target_seconds=30.0,
                )

            with wave.open(str(result.output_path), "rb") as wav:
                actual_seconds = wav.getnframes() / float(wav.getframerate())

            self.assertGreaterEqual(actual_seconds, 30.0)
            self.assertLess(actual_seconds, 31.0)
            self.assertEqual(provider.calls, result.segments)
            self.assertGreater(result.segments, 35)
            self.assertEqual(result.output_path, output)
