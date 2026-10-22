"""Failure-path regression tests for import publication."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.chapters.detector import Chapter
from app.core.project import create_project, list_projects


class ImportPublicationFailureTests(unittest.TestCase):
    def test_missing_source_is_rejected_without_creating_a_partial_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            missing_source = Path(temp) / "missing.txt"

            with mock.patch("app.core.project.library_root", return_value=root):
                with self.assertRaisesRegex(FileNotFoundError, "Import source does not exist"):
                    create_project("Invalid Import", missing_source, [Chapter(1, "Chapter 1", "Text")])

                self.assertFalse(root.exists())
                self.assertEqual(list_projects(), [])


if __name__ == "__main__":
    unittest.main()
