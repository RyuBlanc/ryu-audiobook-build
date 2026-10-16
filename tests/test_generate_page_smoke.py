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


class GeneratePageSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
