"""Deterministic Stage 2 fixtures for chapter segmentation and project persistence."""
from pathlib import Path
import tempfile
import unittest

from app.chapters.detector import Chapter, detect_chapters
from app.core.project import Project


class ChapterDetectionFixtureTests(unittest.TestCase):
    def test_preamble_attaches_to_first_chapter_and_empty_heading_keeps_boundary(self):
        source = (
            "Opening note before chapter one.\n\n"
            "Chapter 1: Arrival\n"
            "The story begins here.\n\n"
            "Chapter 2: Empty on purpose\n\n"
            "Chapter 3: Return\n"
            "The story resumes here."
        )
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters],
                         ["Chapter 1: Arrival", "Chapter 3: Return"])
        self.assertIn("Opening note before chapter one.", chapters[0].text)
        self.assertIn("The story begins here.", chapters[0].text)
        self.assertNotIn("Chapter 2: Empty on purpose", chapters[0].text)
        self.assertNotIn("Chapter 3: Return", chapters[0].text)
        self.assertEqual(chapters[1].text, "The story resumes here.")

    def test_plain_text_without_recognized_headings_falls_back_to_full_book(self):
        source = "A first paragraph.\n\nA second paragraph without chapter markers."
        chapters = detect_chapters(source)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Full Book")
        self.assertEqual(chapters[0].text, source)

    def test_life_dot_number_heading_is_recognized(self):
        source = "Life.0 The Beginning\nA new story starts.\n\nLife.1 First Steps\nThe journey continues."
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters],
                         ["Life.0 The Beginning", "Life.1 First Steps"])
        self.assertEqual(chapters[0].text, "A new story starts.")
        self.assertEqual(chapters[1].text, "The journey continues.")

    def test_saved_chapter_edits_and_metadata_survive_project_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "project"
            chapter = Chapter(
                number=1,
                title="Manually corrected title",
                text="Manually corrected text that must not be replaced.",
                dialogue_assignments=[{"start": 0, "end": 16, "text": "Manually corrected",
                                       "speakers": ["Rias Gremory"]}],
                review_status="reviewed",
                skip_for_generation=True,
            )
            project = Project("Fixture Book", folder, None, [chapter])
            project.save()
            loaded = Project.load(folder)
            self.assertEqual(loaded.chapters[0].title, chapter.title)
            self.assertEqual(loaded.chapters[0].text, chapter.text)
            self.assertEqual(loaded.chapters[0].review_status, "reviewed")
            self.assertTrue(loaded.chapters[0].skip_for_generation)
            self.assertEqual(loaded.chapters[0].dialogue_assignments, chapter.dialogue_assignments)


if __name__ == "__main__":
    unittest.main()
