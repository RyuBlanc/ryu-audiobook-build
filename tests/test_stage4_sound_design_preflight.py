"""Stage 4 Step 2.4: inactive saved cues must not block narration or music generation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.audio.library import validate_saved_audio_paths


class SavedCuePreflightTests(unittest.TestCase):
    def test_disabled_transition_cues_are_not_validated_or_probed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            music = root / "book-music.wav"
            music.write_bytes(b"music")
            missing_cue = root / "deleted-opening-cue.wav"

            with patch("app.audio.library.probe_audio_duration_seconds", return_value=30.0) as probe:
                validate_saved_audio_paths({
                    "background_audio_mode": "manual",
                    "background_audio_enabled": True,
                    "chapter_bgm_strategy": "same",
                    "background_audio_path": str(music),
                    "chapter_transition_sound": False,
                    "opening_cue_path": str(missing_cue),
                    "page_turn_cue_path": str(missing_cue),
                    "ending_cue_path": str(missing_cue),
                })

            self.assertEqual(
                [call.args[0] for call in probe.call_args_list],
                [music],
                "Only active book music should be validated when transition cues are disabled.",
            )

    def test_enabled_transition_cue_still_fails_closed_when_saved_asset_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing_cue = root / "deleted-opening-cue.wav"

            with self.assertRaisesRegex(FileNotFoundError, "Saved opening cue is missing"):
                validate_saved_audio_paths({
                    "background_audio_mode": "manual",
                    "background_audio_enabled": True,
                    "chapter_bgm_strategy": "same",
                    "chapter_transition_sound": True,
                    "opening_cue_path": str(missing_cue),
                })


if __name__ == "__main__":
    unittest.main()
