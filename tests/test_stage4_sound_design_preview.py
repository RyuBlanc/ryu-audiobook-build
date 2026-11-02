"""Stage 4 Step 2.2: short Sound Design preview must obey saved BGM strategy and Voice Only."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ui import premium_v2_host


class SoundDesignPreviewConfigurationTests(unittest.TestCase):
    def _render(self, root: Path, state: dict) -> tuple[list[list[str]], list[tuple[str, str]]]:
        app_root = root / "app"
        preview_root = app_root / "Previews"
        preview_root.mkdir(parents=True)
        source = root / "narration.wav"
        source.write_bytes(b"narration fixture")

        runs: list[list[str]] = []
        concatenations: list[tuple[str, str]] = []

        def fake_run(command):
            args = [str(item) for item in command]
            runs.append(args)
            Path(args[-1]).write_bytes(b"rendered preview" * 200)

        def fake_concat(first, second, output, _bitrate):
            concatenations.append((str(first), str(second)))
            Path(output).write_bytes(b"cue plus narration" * 200)

        with patch.object(premium_v2_host, "app_root", return_value=app_root), \
             patch("app.audio.library.validate_saved_audio_paths"), \
             patch("app.audio.assembler._run", side_effect=fake_run), \
             patch("app.audio.assembler._concat_audio_files", side_effect=fake_concat), \
             patch("app.audio.assembler._duration_ms", return_value=10_000):
            premium_v2_host.PremiumV2Bridge._render_sound_design_preview(
                SimpleNamespace(), source, "stage-4-sound-preview", state
            )
        return runs, concatenations

    def _asset(self, root: Path, name: str) -> Path:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio asset fixture")
        return path.resolve()

    def test_voice_only_override_suppresses_saved_music_and_opening_cue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default_track = self._asset(root, "default-bed.wav")
            opening_cue = self._asset(root, "opening-cue.wav")
            runs, concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": False,
                "background_audio_path": str(default_track),
                "chapter_transition_sound": True,
                "opening_cue_path": str(opening_cue),
            })

        flattened = [item for command in runs for item in command]
        self.assertFalse(any(str(default_track) == item for item in flattened))
        self.assertEqual(concatenations, [])

    def test_chapter_based_strategy_never_falls_back_to_book_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default_track = self._asset(root, "book-default.wav")
            runs, _concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_strategy": "custom",
                "chapter_bgm_overrides": {},
                "background_audio_path": str(default_track),
                "chapter_transition_sound": False,
            })

        flattened = [item for command in runs for item in command]
        self.assertFalse(any(str(default_track) == item for item in flattened))

    def test_legacy_default_override_is_silent_under_chapter_based_strategy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default_track = self._asset(root, "book-default.wav")
            runs, _concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_strategy": "chapter-based",
                "chapter_bgm_overrides": {"1": {"rule": "default"}},
                "background_audio_path": str(default_track),
                "chapter_transition_sound": False,
            })

        flattened = [item for command in runs for item in command]
        self.assertFalse(any(str(default_track) == item for item in flattened))

    def test_chapter_based_custom_override_uses_selected_chapter_track_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default_track = self._asset(root, "book-default.wav")
            chapter_track = self._asset(root, "chapter-one.wav")
            runs, _concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_strategy": "custom",
                "chapter_bgm_overrides": {
                    "1": {"rule": "custom", "path": str(chapter_track), "volume": 0.2}
                },
                "background_audio_path": str(default_track),
                "chapter_transition_sound": False,
            })

        flattened = [item for command in runs for item in command]
        self.assertTrue(any(str(chapter_track) == item for item in flattened))
        self.assertFalse(any(str(default_track) == item for item in flattened))

    def test_same_bgm_strategy_still_uses_saved_book_track(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default_track = self._asset(root, "book-default.wav")
            runs, _concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_strategy": "same",
                "background_audio_path": str(default_track),
                "chapter_transition_sound": False,
            })

        flattened = [item for command in runs for item in command]
        self.assertTrue(any(str(default_track) == item for item in flattened))

    def test_unchecked_chapter_transition_setting_does_not_insert_opening_cue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            opening_cue = self._asset(root, "opening-cue.wav")
            _runs, concatenations = self._render(root, {
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_transition_sound": False,
                "opening_cue_path": str(opening_cue),
            })

        self.assertEqual(concatenations, [])


if __name__ == "__main__":
    unittest.main()
