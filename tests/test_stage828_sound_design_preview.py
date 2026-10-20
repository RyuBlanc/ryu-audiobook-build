"""Stage 8.2.8 sound-design full-book mix preview acceptance checks."""
from __future__ import annotations

import unittest
from pathlib import Path


class Stage828SoundDesignPreviewTests(unittest.TestCase):
    def test_full_book_mix_preview_is_registered_as_a_background_job(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        worker = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        self.assertIn('"sound.preview_book": self._sound_preview_book', source)
        self.assertIn('"sound.preview_book": True', source)
        self.assertIn('def _sound_preview_book(self, _payload: dict[str, Any])', source)
        self.assertIn("start_full_book_preview(self)", source)
        self.assertIn("def start_full_book_preview(host)", worker)
        self.assertIn('host._new_job(\n        "sound-design-book-preview"', worker)
        self.assertIn('name="RyuFullBookSoundPreview"', worker)

    def test_full_book_mix_preview_reuses_saved_narration_and_validates_all_chapters(self):
        source = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        self.assertIn('audio_root = project.folder / "working_audio"', source)
        self.assertIn('A full-book mix preview needs saved narration audio for every chapter.', source)
        self.assertIn('reuses_saved_narration', source)
        self.assertIn('chapter_dirs, output, title, author, cover, chapter_titles', source)

    def test_full_book_preview_uses_the_production_sound_design_assignments(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        for setting in (
            "background_audio_mode=", "background_audio_path=", "background_audio_volume=",
            "ambience_audio_path=", "ambience_audio_volume=", "chapter_transition_sound=",
            "opening_cue_path=", "page_turn_cue_path=", "scene_transition_cue_path=",
            "ending_cue_path=", "chapter_bgm_overrides=",
        ):
            self.assertIn(setting, source)

    def test_sound_design_preview_button_requests_full_book_mix_not_short_voice_preview(self):
        source = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        branch = source[source.index("soundButton.id === 'soundPreviewBook'"):]
        branch = branch[:branch.index("\n          }\n        } catch", 0)]
        self.assertIn("call('sound.preview_book')", branch)
        self.assertIn("full-book mix preview", branch.lower())
        self.assertNotIn("call('production.preview'", branch)


if __name__ == "__main__":
    unittest.main()
