"""Stage 2 regressions for mutually exclusive book-wide and chapter BGM."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.audio import assembler


class Stage2BgmStrategyTests(unittest.TestCase):
    def _assemble(self, strategy: str, overrides: dict[str, dict]):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapter_dir = root / "001_Opening"
            chapter_dir.mkdir()
            narration = root / "chapter-narration.m4a"
            narration.write_bytes(b"fixture narration")
            default_track = root / "book-default.wav"
            default_track.write_bytes(b"fixture book-wide BGM")
            chapter_track = root / "chapter-custom.wav"
            chapter_track.write_bytes(b"fixture chapter BGM")
            commands: list[list[str]] = []

            def fake_ffmpeg(args):
                command = [str(value) for value in args]
                commands.append(command)
                destination = Path(command[-1])
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"F" * 2048)

            with (
                patch.object(assembler, "assemble_chapter", return_value=narration),
                patch.object(assembler, "_duration_ms", return_value=10_000),
                patch.object(assembler, "_run", side_effect=fake_ffmpeg),
                patch.object(
                    assembler.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
                ),
                patch.object(assembler, "_probe_audio_bitrate_kbps", return_value=192),
                patch.object(assembler, "ffmpeg_path", return_value="ffmpeg-test"),
            ):
                assembler.assemble_m4b(
                    [chapter_dir],
                    root / "output.m4b",
                    "Stage 2 test book",
                    chapter_titles=["Opening"],
                    background_audio_path=default_track,
                    background_audio_volume=0.18,
                    background_audio_mode="manual",
                    chapter_bgm_overrides=overrides,
                    chapter_bgm_strategy=strategy,
                )
            return commands, str(default_track), str(chapter_track)

    @staticmethod
    def _command_mentions(commands: list[list[str]], path: str) -> bool:
        return any(path in command for command in commands)

    def test_chapter_based_with_no_assignments_never_falls_back_to_book_default(self):
        commands, default_track, _chapter_track = self._assemble("custom", {})

        self.assertFalse(
            self._command_mentions(commands, default_track),
            "Chapter-based BGM must be silent for unassigned chapters; it must not mix the book default.",
        )

    def test_generation_manager_keeps_explicit_saved_strategy_with_preserved_assignments(self):
        from app.tts.manager import GenerationManager

        same = GenerationManager(
            provider=object(), voice="narrator", chapters=[], project_audio_root=Path("."),
            chapter_bgm_overrides={"1": {"rule": "custom", "path": "preserved"}},
            chapter_bgm_strategy="same",
        )
        chapter = GenerationManager(
            provider=object(), voice="narrator", chapters=[], project_audio_root=Path("."),
            chapter_bgm_overrides={},
            chapter_bgm_strategy="custom",
        )
        self.assertEqual(same.chapter_bgm_strategy, "same")
        self.assertEqual(chapter.chapter_bgm_strategy, "chapter-based")

    def test_same_bgm_ignores_stale_chapter_overrides(self):
        overrides = {
            "1": {
                "rule": "custom",
                "path": None,
                "volume": 0.25,
                "start_offset": "immediate",
                "end_behavior": "fade_before_end",
            }
        }
        # A stale or migrated override must not replace the selected book-wide track.
        commands, default_track, chapter_track = self._assemble("same", overrides)

        self.assertTrue(
            self._command_mentions(commands, default_track),
            "Same BGM must use the selected book-wide track.",
        )
        self.assertFalse(
            self._command_mentions(commands, chapter_track),
            "Same BGM must not add chapter-specific music.",
        )

    def test_chapter_based_uses_only_the_explicitly_assigned_chapter_track(self):
        with tempfile.TemporaryDirectory() as temporary:
            custom_track = Path(temporary) / "specific-chapter.wav"
            custom_track.write_bytes(b"fixture chapter BGM")
            # Save this track in an isolated fixture to ensure the real mixer sees an existing file.
            with patch.object(assembler, "_chapter_number_for_bgm", return_value=1):
                commands, default_track, _ = self._assemble(
                    "custom",
                    {
                        "1": {
                            "rule": "custom",
                            "path": str(custom_track),
                            "volume": 0.25,
                            "start_offset": "immediate",
                            "end_behavior": "fade_before_end",
                        }
                    },
                )

        self.assertFalse(
            self._command_mentions(commands, default_track),
            "Chapter-based BGM must never mix the book-default bed.",
        )
        self.assertTrue(
            self._command_mentions(commands, str(custom_track)),
            "The selected chapter track must be the only BGM track mixed for that chapter.",
        )


if __name__ == "__main__":
    unittest.main()
