"""Stage 4 pronunciation substitution regression tests."""
import unittest

from app.tts.narration import apply_pronunciation_dictionary, prepare_for_narration


class PronunciationDictionaryTests(unittest.TestCase):
    def test_longest_phrase_wins_for_overlapping_entries(self):
        text = "Dr. Mira Vale met Mira."
        dictionary = [
            {"written": "Mira", "spoken": "Mee-rah"},
            {"written": "Mira Vale", "spoken": "My-rah Vail"},
        ]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "Dr. My-rah Vail met Mee-rah.",
        )

    def test_spoken_replacement_is_not_reprocessed_by_later_rule(self):
        text = "NYC is busy."
        dictionary = [
            {"written": "NYC", "spoken": "New York"},
            {"written": "New York", "spoken": "N.Y."},
        ]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "New York is busy.",
        )

    def test_matching_is_case_insensitive_but_respects_word_boundaries(self):
        text = "ARIA met Aria. MARIA and ariax stayed."
        dictionary = [{"written": "aria", "spoken": "Ah-ree-ah"}]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "Ah-ree-ah met Ah-ree-ah. MARIA and ariax stayed.",
        )

    def test_disabled_and_invalid_entries_are_ignored(self):
        text = "Mira met Ren."
        dictionary = [
            {"written": "Mira", "spoken": "Mee-rah", "enabled": False},
            {"written": "", "spoken": "empty"},
            {"written": "Ren", "spoken": ""},
            None,
            {"written": "Ren", "spoken": "Wren"},
        ]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "Mira met Wren.",
        )

    def test_voice_studio_saved_field_names_are_applied(self):
        text = "Mira Vale met Ren."
        dictionary = [
            {"written_form": "Mira Vale", "spoken_form": "My-rah Vail", "enabled": True},
            {"written_form": "Ren", "spoken_form": "Wren", "enabled": True},
        ]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "My-rah Vail met Wren.",
        )

    def test_duplicate_written_forms_are_deterministic_and_first_entry_wins(self):
        text = "Mira met Mira."
        dictionary = [
            {"written_form": "Mira", "spoken_form": "Mee-rah"},
            {"written_form": "mira", "spoken_form": "My-rah"},
        ]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "Mee-rah met Mee-rah.",
        )

    def test_unicode_names_are_supported(self):
        text = "Éowyn met éOWYN."
        dictionary = [{"written": "Éowyn", "spoken": "Ay-oh-win"}]

        self.assertEqual(
            apply_pronunciation_dictionary(text, dictionary),
            "Ay-oh-win met Ay-oh-win.",
        )

    def test_prepare_for_narration_preserves_source_and_only_changes_narration_copy(self):
        source = "Mira said, “Meet me in NYC.”"
        result = prepare_for_narration(
            source,
            [
                {"written": "Mira", "spoken": "Mee-rah"},
                {"written": "NYC", "spoken": "New York City"},
            ],
        )

        self.assertEqual(result.source_text, source)
        self.assertIn("Mee-rah", result.narration_text)
        self.assertIn("New York City", result.narration_text)
        self.assertNotEqual(result.source_text, result.narration_text)


if __name__ == "__main__":
    unittest.main()
