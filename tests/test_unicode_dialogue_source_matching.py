import inspect
import unicodedata
import unittest

from app.ui.premium_v2_host import PremiumV2Bridge


class UnicodeDialogueSourceMatchingTests(unittest.TestCase):
    def test_ai_dialogue_matching_uses_unicode_aware_letters_and_digits(self):
        source = inspect.getsource(PremiumV2Bridge._character_worker)
        self.assertIn('unicodedata.normalize("NFKC", str(value or "")).casefold()', source)
        self.assertIn("character.isalnum()", source)
        self.assertNotIn('re.sub(r"[^0-9a-z]+"', source)

    def test_nfkc_casefold_normalization_preserves_non_latin_quote_text(self):
        def normalize(value):
            normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
            return "".join(character for character in normalized if character.isalnum())

        self.assertEqual(normalize("「こんにちは！」"), "こんにちは")
        self.assertEqual(normalize("你好，Ren！"), "你好ren")
        self.assertEqual(normalize("안녕하세요, 미라!"), "안녕하세요미라")
        self.assertEqual(normalize("“Hello, RÉN!”"), "hellorén")


if __name__ == "__main__":
    unittest.main()
