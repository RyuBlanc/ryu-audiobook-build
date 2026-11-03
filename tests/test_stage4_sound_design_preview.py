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



    def test_selected_chapter_preview_uses_selected_stable_chapter_bgm_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_root = root / "app"
            (app_root / "Previews").mkdir(parents=True)
            source = root / "preview.wav"
            source.write_bytes(b"narration" * 256)
            track = self._asset(root, "chapter-two.wav")
            project = SimpleNamespace(chapters=[
                SimpleNamespace(number=1, title="One", text="Opening", skip_for_generation=False),
                SimpleNamespace(number=2, title="Two", text="Middle", skip_for_generation=False),
            ])
            state = {
                "_preview_chapter_number": 2, "_preview_chapter_title": "Two",
                "_preview_chapter_id": "stable-chapter-two",
                "background_audio_mode": "manual", "background_audio_enabled": True,
                "chapter_bgm_strategy": "chapter-based",
                "chapter_bgm_overrides": {
                    "stable-chapter-two": {"rule": "custom", "path": str(track), "volume": 0.25}
                },
                "background_audio_path": str(self._asset(root, "book-default.wav")),
                "chapter_transition_sound": False,
            }
            calls = []
            def fake_mix(src, path, output, volume, **kwargs):
                calls.append((str(path), volume))
                Path(output).write_bytes(b"mixed chapter" * 256)
                return Path(output)
            bridge = SimpleNamespace(_active_project=lambda: project)
            with patch.object(premium_v2_host, "app_root", return_value=app_root), \
                 patch("app.audio.library.validate_saved_audio_paths"), \
                 patch("app.audio.assembler._duration_ms", return_value=10000), \
                 patch("app.audio.assembler._mix_chapter_bgm", side_effect=fake_mix):
                output = premium_v2_host.PremiumV2Bridge._render_sound_design_preview(bridge, source, "selected-two", state)
            self.assertTrue(output.is_file())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], str(track))
            self.assertEqual(calls[0][1], 0.25)
            self.assertEqual(state["_preview_sound_configuration"]["chapter_number"], 2)
            self.assertEqual(state["_preview_sound_configuration"]["chapter_bgm_strategy"], "chapter-based")

    def test_automatic_chapter_preview_selects_real_library_music_from_chapter_recipe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_root = root / "app"
            (app_root / "Previews").mkdir(parents=True)
            source = root / "preview.wav"
            source.write_bytes(b"narration" * 256)
            track = self._asset(root, "auto-library-track.wav")
            project = SimpleNamespace(chapters=[
                SimpleNamespace(number=4, title="Mystery", text="A mystery in the forest.", skip_for_generation=False)
            ])
            state = {
                "_preview_chapter_number": 4, "_preview_chapter_title": "Mystery",
                "background_audio_mode": "auto", "background_audio_enabled": True,
                "chapter_bgm_strategy": "same", "auto_music_style": "mystery",
                "auto_music_track_path": "", "chapter_transition_sound": False,
            }
            selected = []
            def resolve(mood, selected_track=None, seed_text=""):
                selected.append((mood, selected_track, seed_text))
                return track
            def fake_mix(src, path, output, volume, **kwargs):
                Path(output).write_bytes(b"auto mixed" * 256)
                return Path(output)
            bridge = SimpleNamespace(_active_project=lambda: project)
            with patch.object(premium_v2_host, "app_root", return_value=app_root), \
                 patch("app.audio.library.validate_saved_audio_paths"), \
                 patch("app.audio.library.resolve_music_track", side_effect=resolve), \
                 patch("app.audio.assembler._duration_ms", return_value=10000), \
                 patch("app.audio.assembler._mix_chapter_bgm", side_effect=fake_mix):
                output = premium_v2_host.PremiumV2Bridge._render_sound_design_preview(bridge, source, "selected-auto", state)
            self.assertTrue(output.is_file())
            self.assertEqual(len(selected), 1)
            self.assertIn("Mystery", selected[0][2])



    def test_voice_only_wav_preview_is_encoded_to_m4a_not_copied_with_wrong_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            app_root=root/"app"
            (app_root/"Previews").mkdir(parents=True)
            source=root/"narration.wav"
            source.write_bytes(b"narration fixture"*256)
            output_written=[]
            commands=[]
            def fake_run(args):
                command=[str(item) for item in args]
                commands.append(command)
                Path(command[-1]).write_bytes(b"encoded AAC M4A fixture"*256)
                output_written.append(Path(command[-1]))
            bridge=SimpleNamespace()
            state={
                "background_audio_mode":"off",
                "background_audio_enabled":False,
                "chapter_transition_sound":False,
                "_preview_chapter_number":1,
                "_preview_chapter_title":"Chapter 1",
            }
            with patch.object(premium_v2_host,"app_root",return_value=app_root), \
                 patch("app.audio.library.validate_saved_audio_paths"), \
                 patch("app.audio.assembler._duration_ms",return_value=10000), \
                 patch("app.audio.assembler._run",side_effect=fake_run):
                result=premium_v2_host.PremiumV2Bridge._render_sound_design_preview(
                    bridge,source,"voice-only-wav",state
                )
            expected=app_root/"Previews"/"sound_mix_preview_voice-only-wav.m4a"
            self.assertEqual(result,expected)
            self.assertEqual(output_written,[expected])
            self.assertEqual(len(commands),1)
            self.assertEqual(commands[0][commands[0].index("-c:a")+1],"aac")
            self.assertEqual(commands[0][-1],str(expected))



    def test_production_sound_design_preview_never_deletes_original_imported_cue_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            opening=self._asset(root,"library/cues/opening.wav")
            ending=self._asset(root,"library/cues/ending.wav")
            opening_before=opening.read_bytes()
            ending_before=ending.read_bytes()
            self._render(root,{
                "background_audio_mode":"manual",
                "background_audio_enabled":True,
                "chapter_transition_sound":True,
                "opening_cue_path":str(opening),
                "ending_cue_path":str(ending),
                "sound_cue_volume":0.25,
            })
            self.assertTrue(opening.is_file(),"Preview cleanup must not delete the imported opening cue.")
            self.assertTrue(ending.is_file(),"Preview cleanup must not delete the imported ending cue.")
            self.assertEqual(opening.read_bytes(),opening_before)
            self.assertEqual(ending.read_bytes(),ending_before)


if __name__ == "__main__":
    unittest.main()
