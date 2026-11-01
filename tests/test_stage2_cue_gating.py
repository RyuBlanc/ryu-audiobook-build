"""Stage 2 regression tests for global music/cue disable behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.audio import assembler


class Stage2CueGatingTests(unittest.TestCase):
    def _assemble_with_audio_mode(self, mode: str):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        chapter_dirs = [root / "001_Opening", root / "002_Next"]
        for directory in chapter_dirs:
            directory.mkdir()
        narration_files = [root / "chapter-one.m4a", root / "chapter-two.m4a"]
        for path in narration_files:
            path.write_bytes(b"N" * 2048)
        cue = root / "configured-cue.wav"
        cue.write_bytes(b"C" * 2048)
        resolved_cues: list[tuple[str, str | None]] = []
        joined_cues: list[tuple[str, str]] = []

        def resolve_cue(_temp_dir, kind, _style, _variation, _mood, selected):
            resolved_cues.append((kind, str(selected) if selected else None))
            return cue

        def join_audio(first, second, output, _bitrate):
            joined_cues.append((str(first), str(second)))
            Path(output).write_bytes(b"J" * 2048)
            return Path(output)

        def fake_ffmpeg(args):
            destination = Path(args[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"F" * 2048)

        with (
            patch.object(assembler, "assemble_chapter", side_effect=narration_files),
            patch.object(assembler, "_duration_ms", return_value=10_000),
            patch.object(assembler, "_run", side_effect=fake_ffmpeg),
            patch.object(assembler, "_resolve_cue_audio", side_effect=resolve_cue),
            patch.object(assembler, "_concat_audio_files", side_effect=join_audio),
            patch.object(
                assembler.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
            ),
            patch.object(assembler, "_probe_audio_bitrate_kbps", return_value=192),
            patch.object(assembler, "ffmpeg_path", return_value="ffmpeg-test"),
        ):
            assembler.assemble_m4b(
                chapter_dirs,
                root / "output.m4b",
                "Cue gating test",
                chapter_titles=["Opening", "Next"],
                background_audio_mode=mode,
                chapter_transition_sound=True,
                opening_cue_path=cue,
                page_turn_cue_path=cue,
                ending_cue_path=cue,
            )

        return resolved_cues, joined_cues

    def test_global_off_excludes_opening_next_chapter_and_closing_cues(self):
        resolved_cues, joined_cues = self._assemble_with_audio_mode("off")

        self.assertEqual(
            resolved_cues,
            [],
            "Voice Only/BGM Off must not resolve or insert configured book cues.",
        )
        self.assertEqual(
            joined_cues,
            [],
            "Voice Only/BGM Off must not concatenate opening, next-chapter, or closing clips.",
        )

    def test_manual_mode_keeps_configured_opening_next_chapter_and_closing_cues(self):
        resolved_cues, joined_cues = self._assemble_with_audio_mode("manual")

        self.assertEqual([kind for kind, _path in resolved_cues], ["opening", "page", "ending"])
        self.assertEqual(len(joined_cues), 3)


if __name__ == "__main__":
    unittest.main()
