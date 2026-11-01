"""Focused regressions for requested voice-preview duration.

These tests use a deterministic local WAV provider so duration-budget behavior
is checked without depending on a network TTS service or model.
"""
import math
import tempfile
import unittest
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


class TestPreviewDurationAcceptance(unittest.TestCase):
    def test_qwen_voice_design_preview_batches_two_sentences_and_keeps_target_duration(self):
        class BatchedQwenPreviewProvider:
            qwen_mode = "design-preview"
            recommended_preview_batch_size = 2
            handles_narration_controls = False

            def __init__(self):
                self.batch_calls = []
                self.single_calls = []

            def synthesize_batch(self, items):
                self.batch_calls.append([text for text, _path in items])
                for _text, path in items:
                    _write_tone(Path(path), 0.30)
                return [Path(path) for _text, path in items]

            def synthesize(self, text, output_path, voice=None):
                self.single_calls.append(text)
                _write_tone(Path(output_path), 0.30)

        source_text = (
            "Rias opened the door and smiled at the visitor. "
            "Akeno followed her and spoke in a calm voice. "
            "The hallway became quiet as they waited."
        )
        provider = BatchedQwenPreviewProvider()

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "qwen-batched-preview.wav"
            with patch("app.tts.preview._normalize", side_effect=_copy_normalized), patch(
                "app.tts.preview._concat", side_effect=_concat_wavs
            ):
                result = build_voice_preview(
                    source_text, provider, "design-preview", output,
                    narration_speed=1.0, pacing_profile="off",
                    max_chars=1400, target_seconds=0.60,
                )
            with wave.open(str(result.output_path), "rb") as wav:
                actual_seconds = wav.getnframes() / float(wav.getframerate())

        self.assertEqual(len(provider.batch_calls), 1)
        self.assertEqual(len(provider.batch_calls[0]), 2)
        self.assertEqual(provider.single_calls, [])
        self.assertEqual(result.segments, 2)
        self.assertEqual(result.source_text.splitlines(), provider.batch_calls[0])
        self.assertGreaterEqual(actual_seconds, 0.60)
        self.assertLess(actual_seconds, 0.61)

    def test_qwen_voice_design_preview_batch_oom_falls_back_to_serial_synthesis(self):
        class OomQwenPreviewProvider:
            qwen_mode = "design-preview"
            recommended_preview_batch_size = 2
            handles_narration_controls = False

            def __init__(self):
                self.batch_calls = 0
                self.single_calls = []

            def synthesize_batch(self, items):
                self.batch_calls += 1
                raise RuntimeError("Qwen batch exceeded available GPU memory.")

            def synthesize(self, text, output_path, voice=None):
                self.single_calls.append(text)
                _write_tone(Path(output_path), 0.30)

        source_text = (
            "Rias opened the door and smiled at the visitor. "
            "Akeno followed her and spoke in a calm voice. "
            "The hallway became quiet as they waited."
        )
        provider = OomQwenPreviewProvider()

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "qwen-oom-fallback-preview.wav"
            with patch("app.tts.preview._normalize", side_effect=_copy_normalized), patch(
                "app.tts.preview._concat", side_effect=_concat_wavs
            ):
                result = build_voice_preview(
                    source_text, provider, "design-preview", output,
                    narration_speed=1.0, pacing_profile="off",
                    max_chars=1400, target_seconds=0.60,
                )
            with wave.open(str(result.output_path), "rb") as wav:
                actual_seconds = wav.getnframes() / float(wav.getframerate())

        self.assertEqual(provider.batch_calls, 1)
        self.assertEqual(len(provider.single_calls), 2)
        self.assertEqual(result.segments, 2)
        self.assertEqual(result.source_text.splitlines(), provider.single_calls)
        self.assertGreaterEqual(actual_seconds, 0.60)
        self.assertLess(actual_seconds, 0.61)

    def test_supported_preview_durations_meet_requested_audio_budget(self):
        class FastLocalProvider:
            def __init__(self):
                self.calls = 0

            def synthesize(self, text, output_path, voice=None):
                self.calls += 1
                _write_tone(Path(output_path), 0.30)

        # Deliberately exceed the longest duration's expected source budget.
        # The previous fixed 1,400-character budget produced only ~10 seconds
        # for fast local voices, even when a longer preview was requested.
        text = " ".join(
            f"Sentence {number} contains enough words for the preview duration test."
            for number in range(1, 320)
        )

        with tempfile.TemporaryDirectory() as temp:
            for requested_seconds in (10, 30, 60, 90):
                with self.subTest(requested_seconds=requested_seconds):
                    output = Path(temp) / f"preview-{requested_seconds}-seconds.wav"
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
                            target_seconds=float(requested_seconds),
                        )

                    with wave.open(str(result.output_path), "rb") as wav:
                        actual_seconds = wav.getnframes() / float(wav.getframerate())

                    self.assertGreaterEqual(actual_seconds, requested_seconds)
                    # Each synthetic unit is 0.30s, so the stopping condition
                    # may overshoot by at most one generated segment.
                    self.assertLess(actual_seconds, requested_seconds + 0.31)
                    self.assertEqual(provider.calls, result.segments)
                    self.assertGreater(result.segments, requested_seconds)
                    self.assertEqual(result.output_path, output)
