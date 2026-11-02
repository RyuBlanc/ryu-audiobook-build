"""Stage 4 Step 4.1 — production must pass the complete saved project configuration."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ui import premium_v2_host as host


class EffectiveGenerationConfigurationTests(unittest.TestCase):
    def test_production_generate_forwards_saved_audio_settings_and_all_project_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_folder = root / "project"
            project_folder.mkdir()
            output_root = root / "outputs"
            output_root.mkdir()
            output = output_root / "Complete Configuration.m4b"

            music = root / "book-bgm.wav"
            ambience = root / "ambience.wav"
            chapter_music = root / "chapter-one.wav"
            opening = root / "opening.wav"
            next_chapter = root / "next-chapter.wav"
            closing = root / "closing.wav"
            cover = root / "cover.jpg"
            for path in (music, ambience, chapter_music, opening, next_chapter, closing, cover):
                path.write_bytes(b"test asset")

            chapter = SimpleNamespace(
                number=1, title="Opening", text="Mira enters the room.",
                skip_for_generation=False,
            )
            project = SimpleNamespace(
                folder=project_folder, title="Complete Configuration",
                chapters=[chapter],
            )
            profile = SimpleNamespace(name="Saved Narrator", voice_id="narrator-main")
            manager = Mock()
            pronunciation_rules = [
                {"written_form": "Mira", "spoken_form": "Mee-rah", "enabled": True}
            ]
            state = {
                "author": "Saved Author",
                "publisher": "Saved Publisher",
                "series": "Dragon Chronicles",
                "series_number": "4",
                "language": "ja-JP",
                "year": "2026",
                "genre": "Fantasy",
                "description": "Saved project description must reach the final M4B.",
                "cover_path": str(cover),
                "audio_bitrate": 192,
                "narration_speed": 0.95,
                "pacing_profile": "natural",
                "pronunciation_enabled": True,
                "background_audio_enabled": True,
                "background_audio_mode": "manual",
                "background_audio_path": str(music),
                "background_audio_volume": 0.31,
                "narration_audio_volume": 0.84,
                "sound_cue_volume": 0.23,
                "ambience_audio_path": str(ambience),
                "ambience_audio_volume": 0.14,
                "background_audio_fade_in": 4,
                "background_audio_fade_out": 7,
                "chapter_transition_sound": True,
                "opening_cue_path": str(opening),
                "page_turn_cue_path": str(next_chapter),
                "ending_cue_path": str(closing),
                "sound_cue_style": "library",
                "story_effects_enabled": True,
                "story_effect_volume": 0.17,
                "auto_music_style": "fantasy",
                "auto_music_track_path": str(music),
                "chapter_bgm_strategy": "chapter-based",
                "chapter_bgm_overrides": {
                    "1": {
                        "rule": "custom",
                        "path": str(chapter_music),
                        "volume": 0.27,
                        "start_offset": "after_first_paragraph",
                        "end_behavior": "fade_before_end",
                    }
                },
                "characters": [],
            }
            bridge = SimpleNamespace(
                _assert_no_active_model_lifecycle=Mock(),
                _assert_no_active_audio_synthesis=Mock(),
                close_preview_provider_cache=Mock(),
                _active_project=Mock(return_value=project),
                _resolve_narrator_for_generation=Mock(
                    return_value=(profile, {"source": "project_override", "profile_name": profile.name})
                ),
                _project_series_name=Mock(return_value="Dragon Chronicles"),
                _new_job=Mock(return_value="step4-config-job"),
                _now=Mock(return_value="2026-11-02T17:00:00+05:30"),
                _generation_progress=Mock(),
                _generation_finished=Mock(),
                _job_update=Mock(),
                _jobs_lock=threading.RLock(),
                _generators={},
                settings=SimpleNamespace(value=lambda _key, default=None: default),
            )

            with patch.object(host, "load_state", return_value=state), \
                 patch.object(host, "save_state"), \
                 patch.object(host, "provider_from_profile", return_value=(object(), "narrator-main")), \
                 patch.object(host, "load_profiles", return_value=[]), \
                 patch.object(host, "_effective_pronunciation_dictionary", return_value=pronunciation_rules), \
                 patch.object(host, "audiobooks_root", return_value=output_root), \
                 patch("app.audio.library.validate_saved_audio_paths"), \
                 patch.object(host, "GenerationManager", return_value=manager) as manager_factory:
                result = host.PremiumV2Bridge._production_generate_book(
                    bridge, {"output_path": str(output)}
                )

            self.assertEqual(result["state"], "running")
            kwargs = manager_factory.call_args.kwargs
            self.assertEqual(kwargs["pronunciation_dictionary"], pronunciation_rules)
            self.assertEqual(kwargs["narration_speed"], 0.95)
            self.assertEqual(kwargs["pacing_profile"], "natural")
            self.assertEqual(kwargs["bitrate"], 192)
            self.assertEqual(kwargs["background_audio_mode"], "manual")
            self.assertIsNone(kwargs["background_audio_path"])
            self.assertEqual(kwargs["background_audio_volume"], 0.31)
            self.assertEqual(kwargs["narration_volume"], 0.84)
            self.assertEqual(kwargs["cue_audio_volume"], 0.23)
            self.assertEqual(kwargs["ambience_audio_path"], ambience)
            self.assertEqual(kwargs["ambience_audio_volume"], 0.14)
            self.assertEqual(kwargs["background_audio_fade_in"], 4.0)
            self.assertEqual(kwargs["background_audio_fade_out"], 7.0)
            self.assertTrue(kwargs["chapter_transition_sound"])
            self.assertEqual(kwargs["opening_cue_path"], opening)
            self.assertEqual(kwargs["page_turn_cue_path"], next_chapter)
            self.assertEqual(kwargs["ending_cue_path"], closing)
            self.assertEqual(kwargs["sound_cue_style"], "library")
            self.assertTrue(kwargs["story_effects_enabled"])
            self.assertEqual(kwargs["story_effect_volume"], 0.17)
            self.assertEqual(kwargs["auto_music_style"], "fantasy")
            self.assertEqual(kwargs["auto_music_variation"], str(music))
            self.assertEqual(kwargs["chapter_bgm_strategy"], "chapter-based")
            self.assertEqual(
                kwargs["chapter_bgm_overrides"],
                state["chapter_bgm_overrides"],
            )
            self.assertEqual(
                kwargs["metadata"],
                {
                    "title": "Complete Configuration",
                    "author": "Saved Author",
                    "narrator": "Saved Narrator",
                    "publisher": "Saved Publisher",
                    "series": "Dragon Chronicles",
                    "series_number": "4",
                    "language": "ja-JP",
                    "year": "2026",
                    "genre": "Fantasy",
                    "description": "Saved project description must reach the final M4B.",
                },
            )
            manager.start.assert_called_once()
            start_args = manager.start.call_args
            self.assertEqual(start_args.args[0], output)
            self.assertEqual(start_args.args[1], "Complete Configuration")
            self.assertEqual(start_args.args[2], "Saved Author")
            self.assertEqual(start_args.args[3], cover)


if __name__ == "__main__":
    unittest.main()
