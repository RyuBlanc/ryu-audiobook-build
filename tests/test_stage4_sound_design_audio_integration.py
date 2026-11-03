"""Real FFmpeg/M4B integration checks for Stage 4 Step 2 sound design."""
from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch
from types import SimpleNamespace

from app.audio import assembler
from app.ui import full_book_preview


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

    def test_full_book_preview_matches_final_assembly_for_all_three_sound_scenarios(self):
        class PreviewHost:
            def __init__(self):
                self._preview_cancel_events = {}
                self._jobs_lock = threading.RLock()
                self.updates = []

            def _job_update(self, job_id, **changes):
                self.updates.append((job_id, changes))
                return changes

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book_music = self._write_tone(root / "book-music.wav", 220, 1.0, 0.65)
            chapter_music = self._write_tone(root / "chapter-one.wav", 330, 1.0, 0.65)
            opening = self._write_tone(root / "opening.wav", 400, 0.2, 0.65)
            next_chapter = self._write_tone(root / "next.wav", 600, 0.2, 0.65)
            closing = self._write_tone(root / "closing.wav", 800, 0.2, 0.65)

            scenarios = (
                ("same-bgm", "manual", "same", True),
                ("chapter-based", "manual", "chapter-based", True),
                ("voice-only", "off", "same", False),
            )
            comparison_frequencies = (220, 330, 400, 600, 800, 1000)
            config_keys = (
                "metadata", "bitrate", "narration_speed",
                "background_audio_path", "background_audio_volume",
                "narration_volume", "cue_audio_volume",
                "ambience_audio_path", "ambience_audio_volume",
                "background_audio_fade_in", "background_audio_fade_out",
                "background_audio_mode", "auto_music_style", "auto_music_variation",
                "chapter_transition_sound", "story_effects_enabled",
                "story_effect_volume", "sound_cue_style", "opening_cue_path",
                "page_turn_cue_path", "ending_cue_path", "chapter_bgm_overrides",
                "chapter_bgm_strategy",
            )

            def spectral_signature(samples: array, rate: int, at: float) -> tuple[float, ...]:
                energies = [
                    self._tone_energy(samples, rate, at, frequency)
                    for frequency in comparison_frequencies
                ]
                total = sum(energies)
                if total <= 0:
                    raise AssertionError(f"No measurable audio energy near {at:.2f}s.")
                return tuple(value / total for value in energies)

            for name, mode, strategy, cues_enabled in scenarios:
                with self.subTest(scenario=name):
                    chapter_root = root / name / "working_audio"
                    chapter_dirs = []
                    chapter_titles = []
                    chapter_ids = ("parity-opening", "parity-ending")
                    for number, (title, chapter_id) in enumerate(
                        zip(("Opening", "Ending"), chapter_ids), start=1
                    ):
                        chapter_dir = chapter_root / f"{number:03d}_{title}"
                        self._write_tone(
                            chapter_dir / "chunks" / "00001.wav", 1000, 1.2, 0.14
                        )
                        narration = {
                            "chapter": number, "chapter_id": chapter_id,
                            "title": title, "narration_text": f"{title} narration.",
                        }
                        (chapter_dir / "narration.json").write_text(
                            json.dumps(narration), encoding="utf-8"
                        )
                        (chapter_dir / "chunk_manifest.json").write_text(
                            json.dumps({"chunks": [{
                                "file": "00001.wav", "text": narration["narration_text"]
                            }]}),
                            encoding="utf-8",
                        )
                        chapter_dirs.append(chapter_dir)
                        chapter_titles.append(title)

                    overrides = (
                        {
                            chapter_ids[0]: {
                                "rule": "custom", "path": str(chapter_music),
                                "volume": 0.35, "start_offset": "immediate",
                                "end_behavior": "stop_immediately",
                            },
                            chapter_ids[1]: {"rule": "none"},
                        }
                        if strategy == "chapter-based" else {}
                    )
                    state = {
                        "title": f"Parity {name}", "author": "Ryu Parity Test",
                        "narrator": "Saved Narrator", "language": "en",
                        "genre": "Fantasy", "audio_bitrate": 192,
                        "narration_speed": 1.0,
                        "background_audio_mode": mode,
                        "background_audio_enabled": mode != "off",
                        "background_audio_path": str(book_music),
                        "background_audio_volume": 0.35,
                        "narration_audio_volume": 0.85,
                        "sound_cue_volume": 0.30,
                        "background_audio_fade_in": 0,
                        "background_audio_fade_out": 0,
                        "ambience_audio_volume": 0,
                        "chapter_transition_sound": cues_enabled,
                        "opening_cue_path": str(opening),
                        "page_turn_cue_path": str(next_chapter),
                        "ending_cue_path": str(closing),
                        "sound_cue_style": "library",
                        "story_effects_enabled": False,
                        "story_effect_volume": 0.18,
                        "auto_music_style": "auto", "auto_music_track_path": "",
                        "chapter_bgm_strategy": strategy,
                        "chapter_bgm_overrides": overrides,
                    }
                    metadata = {
                        "title": state["title"], "author": state["author"],
                        "narrator": state["narrator"], "language": "en",
                        "genre": "Fantasy",
                    }
                    preview_output = root / f"{name}-preview.m4b"
                    final_output = root / f"{name}-final.m4b"
                    host = PreviewHost()
                    preview_calls = []
                    real_assemble = assembler.assemble_m4b

                    def capture_preview_assembly(*args, **kwargs):
                        preview_calls.append((args, dict(kwargs)))
                        return real_assemble(*args, **kwargs)

                    with patch.object(
                        assembler, "assemble_m4b", side_effect=capture_preview_assembly
                    ):
                        full_book_preview._render_full_book_preview(
                            host, f"preview-{name}",
                            SimpleNamespace(folder=chapter_root.parent),
                            chapter_dirs, chapter_titles, preview_output,
                            state["title"], state["author"], metadata, 192, state,
                            threading.Event(),
                        )
                    completed = next(
                        row for job_id, row in host.updates
                        if job_id == f"preview-{name}" and row.get("state") == "completed"
                    )
                    self.assertTrue(preview_output.is_file())
                    self.assertEqual(completed["result"]["chapter_count"], 2)
                    self.assertEqual(len(preview_calls), 1)

                    sound_enabled = mode != "off"
                    final_kwargs = {
                        "chapter_titles": chapter_titles, "metadata": metadata, "bitrate": 192,
                        "narration_speed": 1.0,
                        "background_audio_path": book_music if sound_enabled else None,
                        "background_audio_volume": 0.35,
                        "narration_volume": 0.85, "cue_audio_volume": 0.30,
                        "ambience_audio_path": None, "ambience_audio_volume": 0,
                        "background_audio_fade_in": 0, "background_audio_fade_out": 0,
                        "background_audio_mode": mode,
                        "auto_music_style": "auto", "auto_music_variation": None,
                        "chapter_transition_sound": cues_enabled,
                        "story_effects_enabled": False, "story_effect_volume": 0.18,
                        "sound_cue_style": "library",
                        "opening_cue_path": opening if cues_enabled else None,
                        "page_turn_cue_path": next_chapter if cues_enabled else None,
                        "ending_cue_path": closing if cues_enabled else None,
                        "chapter_bgm_overrides": overrides if sound_enabled else {},
                        "chapter_bgm_strategy": strategy,
                    }
                    preview_kwargs = preview_calls[0][1]
                    preview_configuration = {
                        key: preview_kwargs.get(key) for key in config_keys
                    }
                    final_configuration = {
                        key: final_kwargs.get(key) for key in config_keys
                    }
                    self.assertEqual(
                        preview_configuration, final_configuration,
                        f"{name}: saved preview configuration must match final assembly exactly",
                    )

                    rendered = assembler.assemble_m4b(
                        chapter_dirs, final_output, state["title"], state["author"],
                        **final_kwargs,
                    )
                    self.assertEqual(rendered, final_output)

                    preview_audio, preview_rate = self._decode(
                        preview_output, root / f"{name}-preview.wav"
                    )
                    final_audio, final_rate = self._decode(
                        final_output, root / f"{name}-final.wav"
                    )
                    self.assertEqual(preview_rate, final_rate)
                    self.assertEqual(len(preview_audio), len(final_audio))
                    self.assertGreater(len(final_audio), self.sample_rate)

                    anchors = (
                        (0.10, 0.60, 1.50, 2.10, 2.90)
                        if cues_enabled else (0.60, 1.80)
                    )
                    for at in anchors:
                        preview_signature = spectral_signature(preview_audio, preview_rate, at)
                        final_signature = spectral_signature(final_audio, final_rate, at)
                        spectral_distance = sum(
                            abs(left - right)
                            for left, right in zip(preview_signature, final_signature)
                        ) / 2.0
                        self.assertLess(
                            spectral_distance, 0.04,
                            f"{name}: decoded preview/final sound layers diverge near {at:.2f}s",
                        )

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
