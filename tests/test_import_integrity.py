"""Regression coverage for import integrity and safe project publication."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.chapters.detector import Chapter, detect_chapters
from app.core.project import Project, create_project
from app.documents.parser import extract_text, clean_import_noise


class ImportIntegrityTests(unittest.TestCase):
    def test_txt_import_strips_bom_and_preserves_story_content(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "story.txt"
            source.write_bytes(
                b"\xef\xbb\xbfChapter 1: Arrival\n"
                b"The hero walked toward the door.\n\n"
                b"Chapter 2: Departure\nShe followed him."
            )

            book = extract_text(source)
            chapters = detect_chapters(book.text)

            self.assertTrue(book.text.startswith("Chapter 1: Arrival"))
            self.assertIn("The hero walked toward the door.", book.text)
            self.assertIn("She followed him.", book.text)
            self.assertEqual([chapter.title for chapter in chapters], [
                "Chapter 1: Arrival", "Chapter 2: Departure"
            ])
            self.assertIn("The hero walked toward the door.", chapters[0].text)
            self.assertIn("She followed him.", chapters[1].text)

    def test_chapter_detection_does_not_leak_next_heading_into_previous_body(self):
        source = (
            "Chapter 1: First\n"
            "First chapter text ends here.\n\n"
            "Chapter 2: Second\n"
            "Second chapter text ends here."
        )
        chapters = detect_chapters(source)

        self.assertEqual(len(chapters), 2)
        self.assertNotIn("Chapter 2: Second", chapters[0].text)
        self.assertNotIn("Second chapter text", chapters[0].text)
        self.assertIn("First chapter text ends here.", chapters[0].text)
        self.assertIn("Second chapter text ends here.", chapters[1].text)

    def test_noise_cleanup_removes_known_watermark_without_dropping_story(self):
        source = (
            "The story mentions a report in the ordinary narration.\n"
            "41\nReport\nwww.asianovel.com\n"
            "The next paragraph remains intact."
        )
        cleaned, removed = clean_import_noise(source)

        self.assertNotIn("www.asianovel.com", cleaned)
        self.assertIn("The story mentions a report in the ordinary narration.", cleaned)
        self.assertIn("The next paragraph remains intact.", cleaned)
        self.assertIn("Report", removed)

    def test_standalone_report_word_is_preserved_without_watermark_context(self):
        source = "She handed him the report.\\n\\nReport\\n\\nThe meeting continued."
        cleaned, removed = clean_import_noise(source)

        self.assertIn("Report", cleaned)
        self.assertIn("The meeting continued.", cleaned)
        self.assertNotIn("Report", removed)

    def test_import_worker_applies_noise_cleanup_and_reports_removed_count(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("detect_repeated_book_noise([chapter.text for chapter in chapters])", source)
        self.assertIn("chapter.text, removed = clean_import_noise(chapter.text, repeated_noise)", source)
        self.assertIn('"removed_noise_count": len(removed_noise)', source)

    def test_project_creation_round_trip_preserves_review_and_skip_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("A complete source book.", encoding="utf-8")
            chapter = Chapter(
                number=1,
                title="Chapter 1",
                text="A complete chapter.",
                review_status="reviewed",
                skip_for_generation=True,
            )

            with mock.patch("app.core.project.library_root", return_value=root):
                project = create_project("Test Book", source, [chapter])
                loaded = Project.load(project.folder)

            self.assertEqual(loaded.title, "Test Book")
            self.assertTrue(loaded.source_path.is_file())
            self.assertEqual(loaded.chapters[0].review_status, "reviewed")
            self.assertTrue(loaded.chapters[0].skip_for_generation)
            self.assertEqual(loaded.chapters[0].text, "A complete chapter.")

    def test_failed_source_copy_leaves_no_partial_project_in_library(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("A complete source book.", encoding="utf-8")

            with mock.patch("app.core.project.library_root", return_value=root):
                with mock.patch("app.core.project.shutil.copy2", side_effect=OSError("simulated copy failure")):
                    with self.assertRaisesRegex(OSError, "simulated copy failure"):
                        create_project("Broken Import", source, [Chapter(1, "Chapter 1", "Text")])

            self.assertTrue(root.exists())
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
