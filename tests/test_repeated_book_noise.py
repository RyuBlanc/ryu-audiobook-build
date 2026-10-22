"""Regression tests for repeated ebook boilerplate cleanup."""

import unittest

from app.documents.parser import clean_import_noise, detect_repeated_book_noise


class RepeatedBookNoiseTests(unittest.TestCase):
    def test_repeated_boilerplate_is_detected_and_removed_without_losing_narrative(self):
        chapter_texts = [
            "The prince entered the hall.\nDownload\nThe guards bowed.",
            "The queen opened the letter.\nDownload\nThe candles flickered.",
            "The messenger waited outside.\nDownload\nThe doors opened.",
        ]

        repeated = detect_repeated_book_noise(chapter_texts)
        self.assertTrue(repeated)

        cleaned, removed = clean_import_noise(chapter_texts[0], set(repeated))
        self.assertIn("The prince entered the hall.", cleaned)
        self.assertIn("The guards bowed.", cleaned)
        self.assertTrue(removed)


if __name__ == "__main__":
    unittest.main()
