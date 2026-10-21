"""Stage 6 production preflight regressions for empty chapter handling."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager


class GenerationEmptyChapterPreflightTests(unittest.TestCase):
    def _manager(self, chapters, root):
        return GenerationManager(
            provider=object(),
            voice="narrator",
            chapters=chapters,
            project_audio_root=Path(root),
        )

    def test_empty_chapter_list_is_rejected_before_worker_start(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = self._manager([], temp)
            with patch("app.tts.manager.Thread") as thread_factory:
                with self.assertRaisesRegex(ValueError, "No chapters are available"):
                    manager.start(output_path=Path(temp) / "book.m4b")
            thread_factory.assert_not_called()

    def test_all_empty_book_is_rejected_with_recovery_guidance(self):
        chapters = [
            Chapter(1, "Opening", ""),
            Chapter(2, "Chapter Two", "  \n\t"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            manager = self._manager(chapters, temp)
            with patch("app.tts.manager.Thread") as thread_factory:
                with self.assertRaisesRegex(ValueError, "All chapters are empty"):
                    manager.start(output_path=Path(temp) / "book.m4b")
            thread_factory.assert_not_called()

    def test_mixed_empty_and_nonempty_book_names_empty_chapter_and_blocks_all_work(self):
        chapters = [
            Chapter(1, "Opening", "The story begins."),
            Chapter(2, "Missing Text", " \n "),
            Chapter(3, "Ending", "The story ends."),
        ]
        with tempfile.TemporaryDirectory() as temp:
            manager = self._manager(chapters, temp)
            with patch("app.tts.manager.Thread") as thread_factory:
                with self.assertRaisesRegex(ValueError, r"chapter\(s\) 2 are empty"):
                    manager.start(output_path=Path(temp) / "book.m4b")
            thread_factory.assert_not_called()

    def test_valid_nonempty_chapters_are_not_rejected_by_preflight(self):
        chapters = [Chapter(1, "Opening", "The story begins.")]
        with tempfile.TemporaryDirectory() as temp:
            manager = self._manager(chapters, temp)
            with patch("app.tts.manager.Thread") as thread_factory:
                manager.start(output_path=Path(temp) / "book.m4b")
            thread_factory.assert_called_once()
            thread_factory.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
