"""Regression coverage for import integrity and safe project publication."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.chapters.detector import Chapter, detect_chapters
from app.core.project import Project, create_project, list_projects
from app.documents.parser import extract_text, clean_import_noise, pdf_extraction_quality_warning


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

    def test_docx_import_preserves_paragraphs_and_table_story_text(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "story.docx"
            document = Document()
            document.add_paragraph("Chapter 1: Arrival")
            document.add_paragraph("The first paragraph survives.")
            table = document.add_table(rows=1, cols=1)
            table.cell(0, 0).text = "Story text stored in a table survives."
            document.add_paragraph("The final paragraph survives.")
            document.save(source)

            book = extract_text(source)

            self.assertIn("The first paragraph survives.", book.text)
            self.assertIn("Story text stored in a table survives.", book.text)
            self.assertIn("The final paragraph survives.", book.text)
            self.assertLess(book.text.index("The first paragraph survives."),
                            book.text.index("Story text stored in a table survives."))
            self.assertLess(book.text.index("Story text stored in a table survives."),
                            book.text.index("The final paragraph survives."))

    def test_epub_import_follows_spine_reading_order(self):
        from ebooklib import epub

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "story.epub"
            book = epub.EpubBook()
            book.set_identifier("import-integrity-test")
            book.set_title("Reading order test")
            book.set_language("en")
            chapter_two = epub.EpubHtml(title="Second", file_name="second.xhtml", lang="en")
            chapter_two.content = "<html><body><p>Second chapter content.</p></body></html>"
            chapter_one = epub.EpubHtml(title="First", file_name="first.xhtml", lang="en")
            chapter_one.content = "<html><body><p>First chapter content.</p></body></html>"
            book.add_item(chapter_one)
            book.add_item(chapter_two)
            book.spine = [chapter_two, chapter_one]
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            epub.write_epub(str(source), book)

            extracted = extract_text(source).text

            self.assertLess(extracted.index("Second chapter content."),
                            extracted.index("First chapter content."))

    def test_sparse_long_pdf_extraction_is_blocked_with_actionable_diagnostic(self):
        warning = pdf_extraction_quality_warning(page_count=80, word_count=120)
        self.assertIsNotNone(warning)
        self.assertIn("OCR", warning)
        self.assertIn("partial audiobook", warning)
        self.assertIsNone(pdf_extraction_quality_warning(page_count=2, word_count=120))

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
        source = "She handed him the report.\n\nReport\n\nThe meeting continued."
        cleaned, removed = clean_import_noise(source)

        self.assertIn("Report", cleaned)
        self.assertIn("The meeting continued.", cleaned)
        self.assertNotIn("Report", removed)

    def test_import_worker_applies_noise_cleanup_and_reports_removed_count(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("detect_repeated_book_noise([chapter.text for chapter in chapters])", source)
        self.assertIn("chapter.text, removed = clean_import_noise(chapter.text, repeated_noise)", source)
        self.assertIn('"removed_noise_count": len(removed_noise)', source)

    def test_cleanup_preserves_urls_unicode_punctuation_and_dialogue_not_matching_watermarks(self):
        from app.documents.parser import clean_import_noise

        source = (
            "The character opened https://example.com/path to read the letter.\n"
            "“I said, report it!” she shouted.\n"
            "世界はまだ終わっていない。\n"
            "The hero kept walking—slowly, carefully.\n"
            "The next paragraph stays separate."
        )
        cleaned, removed = clean_import_noise(source)

        self.assertIn("https://example.com/path", cleaned)
        self.assertIn("“I said, report it!” she shouted.", cleaned)
        self.assertIn("世界はまだ終わっていない。", cleaned)
        self.assertIn("walking—slowly, carefully.", cleaned)
        self.assertIn("The next paragraph stays separate.", cleaned)
        self.assertEqual(removed, [])

    def test_reflow_joins_hyphenated_line_wrap_without_losing_paragraph_or_heading_boundaries(self):
        from app.documents.parser import reflow_source_text

        source = (
            "Chapter 1: Arrival\n"
            "The inter-\n"
            "national train slowed near the station.\n\n"
            "“Stay here,” she said.\n"
            "“I will.”\n\n"
            "Chapter 2: Departure\n"
            "The next part begins."
        )
        result = reflow_source_text(source)

        self.assertIn("Chapter 1: Arrival\nThe international train slowed near the station.", result)
        self.assertIn("“Stay here,” she said.\n“ I will.”".replace("“ ", "“"), result)
        self.assertIn("Chapter 2: Departure\nThe next part begins.", result)
        self.assertNotIn("Arrival The", result)
        self.assertNotIn("Chapter 1: Arrival Chapter 2: Departure", result)

    def test_chapter_detection_supports_roman_numerals_prologue_and_epilogue(self):
        source = (
            "Prologue\nA beginning before the main story.\n"
            "Chapter IV: The Trial\nThe trial starts.\n"
            "Epilogue\nThe story closes."
        )
        chapters = detect_chapters(source)

        self.assertEqual([chapter.title for chapter in chapters],
                         ["Prologue", "Chapter IV: The Trial", "Epilogue"])
        self.assertIn("A beginning before the main story.", chapters[0].text)
        self.assertIn("The trial starts.", chapters[1].text)
        self.assertIn("The story closes.", chapters[2].text)

    def test_chapter_detection_preserves_preamble_and_books_without_headings(self):
        preamble_source = (
            "Translator note: names follow the original spelling.\n"
            "Chapter 1: First\nThe first chapter begins."
        )
        chapters = detect_chapters(preamble_source)
        self.assertEqual(len(chapters), 1)
        self.assertIn("Translator note: names follow the original spelling.", chapters[0].text)
        self.assertIn("The first chapter begins.", chapters[0].text)

        unheaded = detect_chapters("A complete opening.\n\nA complete ending.")
        self.assertEqual(len(unheaded), 1)
        self.assertEqual(unheaded[0].title, "Full Book")
        self.assertIn("A complete opening.", unheaded[0].text)
        self.assertIn("A complete ending.", unheaded[0].text)

    def test_chapter_detection_does_not_treat_dialogue_like_chapter_text_as_heading(self):
        source = (
            "Chapter 1: Arrival\n"
            "Chapter 2: You cannot go in there, she said, turning away.\n"
            "She reached for the door."
        )
        chapters = detect_chapters(source)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Chapter 1: Arrival")
        self.assertIn("Chapter 2: You cannot go in there, she said, turning away.", chapters[0].text)
        self.assertIn("She reached for the door.", chapters[0].text)

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

    def test_library_listing_hides_in_progress_import_staging_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            staging = root / ".import-staging-test"
            staging.mkdir(parents=True)
            (staging / "project.json").write_text('{"title":"Not published"}', encoding="utf-8")

            with mock.patch("app.core.project.library_root", return_value=root):
                self.assertEqual(list_projects(), [])

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
