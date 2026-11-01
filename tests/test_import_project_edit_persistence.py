"""Persistence regression tests for manually edited imported chapters."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.chapters.detector import Chapter
from app.core.project import Project, create_project


class ImportProjectEditPersistenceTests(unittest.TestCase):
    def test_manual_chapter_edits_order_assignments_and_review_state_survive_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            source = Path(temp) / "source.txt"
            source.write_text("Original source text.", encoding="utf-8")
            chapters = [
                Chapter(1, "Chapter 1", "First imported body."),
                Chapter(2, "Chapter 2", "Second imported body."),
            ]

            with mock.patch("app.core.project.library_root", return_value=root):
                created = create_project("Persistence Test", source, chapters)
                edited = Project.load(created.folder)

                # Simulate user edits in the chapter editor, including reordering.
                edited.chapters[0].title = "Renamed opening"
                edited.chapters[0].text = "Corrected opening text."
                edited.chapters[0].review_status = "reviewed"
                edited.chapters[0].skip_for_generation = True
                edited.chapters[0].dialogue_assignments = [
                    {"text": "Wait here.", "speaker": "Mira", "start": 0, "end": 11}
                ]
                edited.chapters.reverse()
                edited.save()

                reopened = Project.load(created.folder)

            self.assertEqual([chapter.title for chapter in reopened.chapters],
                             ["Chapter 2", "Renamed opening"])
            self.assertEqual([chapter.number for chapter in reopened.chapters], [1, 2])
            opening = reopened.chapters[1]
            self.assertEqual(opening.text, "Corrected opening text.")
            self.assertEqual(opening.review_status, "reviewed")
            self.assertTrue(opening.skip_for_generation)
            self.assertEqual(opening.dialogue_assignments, [
                {"text": "Wait here.", "speaker": "Mira", "start": 0, "end": 11}
            ])


if __name__ == "__main__":
    unittest.main()
