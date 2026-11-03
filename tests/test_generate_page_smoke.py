from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

# Qt must use its headless platform in CI. Set this before importing PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app.audio.sound_design as sound_design
from app.audio.sound_design import MOOD_ORDER, THEMES, music_variation_info
from app.chapters.detector import Chapter
from app.ui.generation_page import GenerationPage
from app.ui.voice_page import PREVIEW_DURATION_OPTIONS
from app.ui.workflow import _import_book_icon
from app.version import BUILD_NUMBER, full_version


class GeneratePageSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_build_label_comes_from_bundled_build_metadata(self) -> None:
        self.assertEqual(full_version(), f"v0.3.7 • Build {BUILD_NUMBER}")

    def test_import_controls_use_the_audiobook_mark(self) -> None:
        icon = _import_book_icon()
        self.assertFalse(icon.isNull(), "Import controls must not fall back to a generic plus icon.")

    def test_voice_preview_still_supports_up_to_one_minute(self) -> None:
        self.assertEqual(PREVIEW_DURATION_OPTIONS, (10, 20, 30, 45, 60))
        self.assertEqual(PREVIEW_DURATION_OPTIONS.index(30), 2)  # 30 seconds remains the default.

    def test_mood_catalogue_constant_is_available(self) -> None:
        self.assertEqual(MOOD_ORDER, tuple(THEMES))
        # Simulate a frozen/legacy loader missing this module global, which
        # matches the user's reported NameError without needing the full EXE.
        with patch.object(sound_design, "MOOD_ORDER", None):
            info = music_variation_info("fantasy", 0)
        self.assertEqual(info["mood"], "fantasy")
        self.assertGreaterEqual(info["id"], 1)

    def test_generate_page_constructs_and_refreshes_for_navigation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ryu-generate-page-smoke-") as temp:
            root = Path(temp)
            project_folder = root / "sample-project"
            project_folder.mkdir()
            chapter = Chapter(1, "Smoke Test Chapter", "A short sample chapter for the Generate page.")

            page = GenerationPage(
                chapters=[chapter],
                audio_root=root / "working",
                project_folder=project_folder,
                project_title="Generate Page Smoke Test",
            )
            try:
                self.assertEqual(page.title.text(), "Generate Page Smoke Test")
                # Keep the full narration preview controls present and independent
                # from full-book generation.
                self.assertIn("Preview", page.preview_button.text())
                self.assertIn("Play", page.preview_play_button.text())
                self.assertIn("Stop", page.preview_stop_button.text())
                self.assertEqual(page.preview_loading.maximum(), 100)
                self.assertEqual(
                    [page.audio_bitrate.itemData(i) for i in range(page.audio_bitrate.count())],
                    [128, 160, 192, 224, 256, 288, 320],
                )
                self.assertTrue(page.chapter_transition_sound.isChecked())
                self.assertTrue(page.story_effects_enabled.isChecked())
                # These are the same refresh operations the sidebar performs
                # when the Generate section is selected for an open book.
                page._refresh_voice_profiles()
                page._load_voice_cast_summary()
                page.refresh_chapter_sources()
                self.app.processEvents()
            finally:
                page.close()
                page.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
