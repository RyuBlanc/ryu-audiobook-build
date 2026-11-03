"""Stage 4 Step 2.4: inactive saved cues must not block narration or music generation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.audio.library import validate_saved_audio_paths
from app.core.state import load_state


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


    def test_legacy_saved_cues_remain_active_when_transition_switch_key_is_absent(self):
        import json
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            root = Path(temp)
            cue = root / "legacy-opening.wav"
            cue.write_bytes(b"legacy cue")
            cue.with_name(cue.name + ".license.json").write_text(
                json.dumps({"role": "cue", "category": "opening"}),
                encoding="utf-8",
            )
            with patch("app.audio.library.probe_audio_duration_seconds", return_value=3.0) as probe:
                validate_saved_audio_paths({
                    "background_audio_mode": "manual",
                    "background_audio_enabled": True,
                    "opening_cue_path": str(cue),
                })
            self.assertEqual([call.args[0] for call in probe.call_args_list], [cue])




    def test_fresh_and_legacy_project_state_defaults_master_bgm_to_eighteen_percent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fresh_project = root / "fresh-project"
            self.assertEqual(load_state(fresh_project)["background_audio_volume"], 0.18)

            legacy_project = root / "legacy-project"
            legacy_project.mkdir()
            (legacy_project / "state.json").write_text(
                '{"title": "Legacy project"}',
                encoding="utf-8",
            )
            self.assertEqual(load_state(legacy_project)["background_audio_volume"], 0.18)

if __name__ == "__main__":
    unittest.main()
