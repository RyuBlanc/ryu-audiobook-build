"""Real FFmpeg/M4B integration checks for Stage 4 Step 2 sound design."""
from __future__ import annotations

from array import array
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

from app.audio import assembler


class Stage4SoundDesignAudioIntegrationTests(unittest.TestCase):
    sample_rate = 44_100

    @classmethod
    def _write_tone(cls, path: Path, frequency: float, duration: float, amplitude: float = 0.12) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        samples = array(
            "h",
            (
                int(amplitude * 32767 * math.sin(2.0 * math.pi * frequency * index / cls.sample_rate))
                for index in range(round(cls.sample_rate * duration))
            ),
        )
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(cls.sample_rate)
            output.writeframes(samples.tobytes())
        return path

    @classmethod
    def _make_chapters(cls, root: Path, count: int, duration: float = 1.2) -> list[Path]:
        chapters = []
        for number in range(1, count + 1):
            chapter_dir = root / f"{number:03d}_Chapter{number}"
            cls._write_tone(chapter_dir / "chunks" / "0001.wav", 1000, duration)
            chapters.append(chapter_dir)
        return chapters

    @classmethod
    def _decode(cls, source: Path, destination: Path) -> tuple[array, int]:
        result = subprocess.run(
            [
                assembler.ffmpeg_path(), "-y", "-i", str(source),
                "-map", "0:a:0", "-ac", "1", "-ar", str(cls.sample_rate),
                "-c:a", "pcm_s16le", str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0 or not destination.is_file():
            raise AssertionError(
                "Could not decode the rendered M4B for audio integration checks: "
                + str(result.stderr or result.stdout)[-2000:]
            )
        with wave.open(str(destination), "rb") as decoded:
            samples = array("h")
            samples.frombytes(decoded.readframes(decoded.getnframes()))
            return samples, decoded.getframerate()

    @staticmethod
    def _tone_energy(samples: array, sample_rate: int, start_seconds: float, frequency: float) -> float:
        start = max(0, int(start_seconds * sample_rate))
        end = min(len(samples), start + int(0.10 * sample_rate))
        segment = samples[start:end]
        if len(segment) < int(0.08 * sample_rate):
            raise AssertionError(f"Audio is too short to inspect the {frequency} Hz segment.")
        coefficient = 2.0 * math.cos(2.0 * math.pi * frequency / sample_rate)
        previous = 0.0
        previous_previous = 0.0
        for value in segment:
            current = float(value) + coefficient * previous - previous_previous
            previous_previous, previous = previous, current
        return (
            previous_previous * previous_previous
            + previous * previous
            - coefficient * previous * previous_previous
        )

    def _assert_tone(self, samples: array, rate: int, at: float, target: float, alternatives: tuple[float, ...]) -> None:
        target_energy = self._tone_energy(samples, rate, at, target)
        other_energy = max(self._tone_energy(samples, rate, at, value) for value in alternatives)
        self.assertGreater(
            target_energy,
            other_energy * 4.0,
            f"Expected the {target} Hz audio layer near {at:.2f}s; "
            f"target energy={target_energy:.1f}, competing energy={other_energy:.1f}.",
        )

    def test_rendered_m4b_places_each_fixed_cue_at_its_chapter_boundary_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapters = self._make_chapters(root / "chapters", 3)
            opening = self._write_tone(root / "opening.wav", 400, 0.8, 0.7)
            next_chapter = self._write_tone(root / "next.wav", 600, 0.8, 0.7)
            closing = self._write_tone(root / "closing.wav", 800, 0.8, 0.7)
            output = root / "cue-sequence.m4b"

            rendered = assembler.assemble_m4b(
                chapters,
                output,
                "Cue sequence acceptance",
                chapter_titles=["One", "Two", "Three"],
                bitrate=192,
                background_audio_mode="manual",
                chapter_transition_sound=True,
                cue_audio_volume=0.50,
                opening_cue_path=opening,
                page_turn_cue_path=next_chapter,
                ending_cue_path=closing,
            )

            self.assertAlmostEqual(assembler._duration_ms(rendered) / 1000.0, 6.8, delta=0.5)
            decoded, rate = self._decode(rendered, root / "cue-sequence.wav")
            # Opening; chapter 1; Next Chapter; chapter 2; Next Chapter; chapter 3; Closing.
            expected_segments = [
                (0.40, 400),
                (1.40, 1000),
                (2.40, 600),
                (3.40, 1000),
                (4.40, 600),
                (5.40, 1000),
                (6.40, 800),
            ]
            for at, frequency in expected_segments:
                alternatives = tuple(value for value in (400, 600, 800, 1000) if value != frequency)
                self._assert_tone(decoded, rate, at, frequency, alternatives)

    def test_voice_only_m4b_omits_saved_bgm_and_all_fixed_cues(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapters = self._make_chapters(root / "chapters", 3)
            book_music = self._write_tone(root / "book-music.wav", 220, 1.0, 0.7)
            opening = self._write_tone(root / "opening.wav", 400, 0.8, 0.7)
            next_chapter = self._write_tone(root / "next.wav", 600, 0.8, 0.7)
            closing = self._write_tone(root / "closing.wav", 800, 0.8, 0.7)

            rendered = assembler.assemble_m4b(
                chapters,
                root / "voice-only.m4b",
                "Voice Only acceptance",
                chapter_titles=["One", "Two", "Three"],
                bitrate=192,
                background_audio_mode="off",
                background_audio_path=book_music,
                chapter_transition_sound=True,
                opening_cue_path=opening,
                page_turn_cue_path=next_chapter,
                ending_cue_path=closing,
            )

            self.assertAlmostEqual(assembler._duration_ms(rendered) / 1000.0, 3.6, delta=0.3)
            decoded, rate = self._decode(rendered, root / "voice-only.wav")
            self._assert_tone(decoded, rate, 0.60, 1000, (220, 400, 600, 800))
            self._assert_tone(decoded, rate, 1.80, 1000, (220, 400, 600, 800))
            self._assert_tone(decoded, rate, 3.00, 1000, (220, 400, 600, 800))

    def test_same_and_chapter_based_bgm_render_the_selected_strategy_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapters = self._make_chapters(root / "chapters", 2)
            book_music = self._write_tone(root / "book-default.wav", 220, 1.0, 0.8)
            chapter_music = self._write_tone(root / "chapter-one.wav", 330, 1.0, 0.8)

            same = assembler.assemble_m4b(
                chapters,
                root / "same-bgm.m4b",
                "Same BGM acceptance",
                chapter_titles=["One", "Two"],
                bitrate=192,
                background_audio_mode="manual",
                background_audio_path=book_music,
                background_audio_volume=0.50,
                background_audio_fade_in=0,
                background_audio_fade_out=0,
                chapter_bgm_strategy="same",
            )
            same_audio, rate = self._decode(same, root / "same-bgm.wav")
            for at in (0.60, 1.80):
                self.assertGreater(
                    self._tone_energy(same_audio, rate, at, 220),
                    self._tone_energy(same_audio, rate, at, 1000) * 0.02,
                    "Same BGM must render the saved book-default track throughout the book.",
                )

            chapter_based = assembler.assemble_m4b(
                chapters,
                root / "chapter-based.m4b",
                "Chapter-Based BGM acceptance",
                chapter_titles=["One", "Two"],
                bitrate=192,
                background_audio_mode="manual",
                background_audio_path=book_music,
                background_audio_volume=0.50,
                background_audio_fade_in=0,
                background_audio_fade_out=0,
                chapter_bgm_strategy="chapter-based",
                chapter_bgm_overrides={
                    "1": {
                        "rule": "custom",
                        "path": str(chapter_music),
                        "volume": 0.50,
                        "start_offset": "immediate",
                        "end_behavior": "stop_immediately",
                    },
                    "2": {"rule": "none"},
                },
            )
            chapter_audio, rate = self._decode(chapter_based, root / "chapter-based.wav")
            chapter_one_music = self._tone_energy(chapter_audio, rate, 0.60, 330)
            chapter_one_default = self._tone_energy(chapter_audio, rate, 0.60, 220)
            self.assertGreater(
                chapter_one_music,
                chapter_one_default * 4.0,
                "Chapter 1 must use its explicitly assigned track, not book-default BGM.",
            )
            chapter_two_voice = self._tone_energy(chapter_audio, rate, 1.80, 1000)
            self.assertLess(
                self._tone_energy(chapter_audio, rate, 1.80, 220),
                chapter_two_voice * 0.02,
                "An unassigned Chapter-Based chapter must not fall back to book-default BGM.",
            )
            self.assertLess(
                self._tone_energy(chapter_audio, rate, 1.80, 330),
                chapter_two_voice * 0.02,
                "A chapter-specific track must not leak into an unassigned chapter.",
            )


if __name__ == "__main__":
    unittest.main()
