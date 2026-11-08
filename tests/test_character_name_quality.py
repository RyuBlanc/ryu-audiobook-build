import unittest

from app.chapters.characters import is_likely_character_name, character_detection_exclusion_keys


class CharacterNameQualityTests(unittest.TestCase):
    def test_common_capitalized_prose_and_description_phrases_are_not_cast_members(self):
        for value in (
            "SILVER HAIRED", "Silver-Haired", "Letting", "Hearing Tobio's",
            "Astonished Tobio", "The School",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_likely_character_name(value))

    def test_valid_names_and_explicit_user_or_speaker_evidence_are_preserved(self):
        self.assertTrue(is_likely_character_name("Ikuse Tobio"))
        self.assertTrue(is_likely_character_name("Tobio"))
        self.assertTrue(is_likely_character_name("Ono Anna"))
        self.assertTrue(is_likely_character_name("Hearing", explicit=True))
        self.assertTrue(is_likely_character_name("Silver-Haired", trusted=True))


    def test_persisted_detection_exclusions_are_series_scoped_and_assignment_can_restore(self):
        exclusions = [
            {"name": "Silver-Haired", "aliases": ["The Silver Knight"], "series": "Series A"},
            {"name": "The School", "aliases": [], "series": "Series B"},
            {"name": "Mira", "aliases": ["Miri"], "series": "Series A"},
        ]
        excluded = character_detection_exclusion_keys(exclusions, "Series A")
        self.assertEqual(excluded, {"silver-haired", "the silver knight", "mira", "miri"})
        self.assertEqual(character_detection_exclusion_keys(exclusions, "Series B"), {"the school"})
        # A saved manual dialogue assignment is stronger evidence than a prior
        # dismissal and deliberately makes that identity eligible again.
        restored = character_detection_exclusion_keys(exclusions, "Series A", protected_names={"Miri"})
        self.assertEqual(restored, {"silver-haired", "the silver knight", "mira"})

    def test_detection_exclusions_reject_malformed_entries_and_do_not_cross_series(self):
        exclusions = [
            None,
            {"name": "", "series": "Series A"},
            {"name": "Tobio", "series": "Series A"},
            {"name": "Ren", "series": "Series B"},
            {"name": "Mira", "series": ""},
        ]
        self.assertEqual(character_detection_exclusion_keys(exclusions, "Series A"), {"tobio"})


if __name__ == "__main__":
    unittest.main()
