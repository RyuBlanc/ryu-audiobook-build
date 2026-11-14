import unittest

from app.core.character_identity import character_identity_key, parse_character_identity_key


class CharacterIdentityUnicodeTests(unittest.TestCase):
    def test_composed_and_decomposed_accented_names_share_a_stable_key(self):
        composed = character_identity_key("Élodie", "Café Series")
        decomposed = character_identity_key("E\u0301lodie", "Cafe\u0301 Series")
        self.assertEqual(composed, decomposed)
        self.assertEqual(
            parse_character_identity_key(decomposed),
            ("café series", "élodie"),
        )


if __name__ == "__main__":
    unittest.main()
