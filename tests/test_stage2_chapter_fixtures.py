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
        self.assertEqual(chapters[1].text, "Chapter 3: Return\nThe story resumes here.")

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
        self.assertEqual(chapters[0].text, "Life.0 The Beginning\nA new story starts.")
        self.assertEqual(chapters[1].text, "Life.1 First Steps\nThe journey continues.")

    def test_named_sections_and_roman_chapter_headings_keep_boundaries(self):
        source = (
            "Prologue\n"
            "Rain crossed the old city as Mira approached the gate. She carried a sealed letter.\n\n"
            "Chapter IV: The Door\n"
            "The guards opened the door slowly. Mira stepped inside without looking back.\n\n"
            "Epilogue — After the Storm\n"
            "Years later, the city remembered the night the gates first opened."
        )
        chapters = detect_chapters(source)
        self.assertEqual(
            [chapter.title for chapter in chapters],
            ["Prologue", "Chapter IV: The Door", "Epilogue — After the Storm"],
        )
        self.assertIn("Rain crossed the old city", chapters[0].text)
        self.assertIn("The guards opened the door slowly", chapters[1].text)
        self.assertIn("Years later, the city remembered", chapters[2].text)
        self.assertNotIn("Epilogue — After the Storm", chapters[1].text)

    def test_compound_slash_title_and_part_heading_is_one_boundary(self):
        source = (
            "BLACK DOG/BIRTH\n"
            "Part 1\n"
            "The first passage begins with a clear event and continues through a complete scene.\n\n"
            "BLACK DOG/RETURN\n"
            "Part 2\n"
            "The second passage follows the earlier scene and moves the story toward its next conflict."
        )
        chapters = detect_chapters(source)
        self.assertEqual(
            [chapter.title for chapter in chapters],
            ["BLACK DOG/BIRTH: Part 1", "BLACK DOG/RETURN: Part 2"],
        )
        self.assertIn("The first passage begins", chapters[0].text)
        self.assertNotIn("Part 2", chapters[0].text)
        self.assertIn("The second passage follows", chapters[1].text)


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

    def test_part_only_roman_headings_are_detected_without_leaking_next_body(self):
        source = (
            "Part I: Arrival\n"
            "The first part remains intact.\n\n"
            "Part II: Departure\n"
            "The second part remains intact."
        )
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters], [
            "Part I: Arrival", "Part II: Departure"
        ])
        self.assertIn("The first part remains intact.", chapters[0].text)
        self.assertNotIn("Part II: Departure", chapters[0].text)
        self.assertIn("The second part remains intact.", chapters[1].text)

    def test_embedded_slash_titles_and_urls_are_not_structural_headings(self):
        source = (
            "The speaker discussed BLACK DOG/BIRTH before turning away.\\n"
            "Read https://example.com/BLACK/DOG for additional context.\n"
            "The paragraph continues as ordinary narrative."
        )
        chapters = detect_chapters(source)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Full Book")
        self.assertIn("BLACK DOG/BIRTH", chapters[0].text)
        self.assertIn("https://example.com/BLACK/DOG", chapters[0].text)


if __name__ == "__main__":
    unittest.main()
