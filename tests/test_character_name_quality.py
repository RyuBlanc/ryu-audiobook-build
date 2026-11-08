import unittest

from app.chapters.characters import is_likely_character_name


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


if __name__ == "__main__":
    unittest.main()
