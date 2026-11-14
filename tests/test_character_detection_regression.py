import unittest

from app.chapters.characters import analyze_book
from app.chapters.detector import Chapter


class CharacterDetectionRegressionTests(unittest.TestCase):
    def test_explicit_speaker_labels_produce_character_candidates(self):
        chapter = Chapter(
            number=1,
            title="Chapter 1",
            text=(
                'Rias: 「Are you ready to go?」\n'
                'Issei: 「Yes, I am ready.」\n'
                'Rias: 「Then let us leave now.」\n'
                'Issei: 「I will follow you.」'
            ),
        )
        result = analyze_book([chapter])
        names = {character.name.casefold() for character in result.characters}
        self.assertIn("rias", names)
        self.assertIn("issei", names)
        self.assertGreaterEqual(result.dialogue_total, 4)
        self.assertGreaterEqual(
            sum(character.dialogue_count for character in result.characters), 2
        )


    def test_multilingual_and_canonically_equivalent_accented_speaker_labels_keep_identity(self):
        chapter = Chapter(
            number=1,
            title="Unicode speaker identity",
            text=(
                '美咲: 「おはよう。」\n'
                '美咲: 「ありがとう。」\n'
                '林晓: “我们走吧。”\n'
                '林晓: “谢谢你。”\n'
                '민수: “안녕하세요.”\n'
                '민수: “고마워.”\n'
                'Élodie: “Bonjour.”\n'
                'E\u0301lodie: “Merci.”'
            ),
        )
        result = analyze_book([chapter])
        import unicodedata
        by_key = {
            unicodedata.normalize("NFC", character.name).casefold(): character
            for character in result.characters
        }
        for name in ("美咲", "林晓", "민수", "Élodie"):
            with self.subTest(name=name):
                self.assertIn(name.casefold(), by_key)
                self.assertEqual(by_key[name.casefold()].dialogue_count, 2)
        self.assertEqual(result.dialogue_total, 8)
        self.assertEqual(result.unassigned_dialogue, 0)

    def test_dialogue_tags_produce_candidates_without_colon_labels(self):
        chapter = Chapter(
            number=1,
            title="Chapter 1",
            text=(
                '“We should leave now,” Rias said.\n'
                '“I agree,” Issei replied.\n'
                '“Stay close,” Rias warned.'
            ),
        )
        result = analyze_book([chapter])
        names = {character.name.casefold() for character in result.characters}
        self.assertIn("rias", names)
        self.assertIn("issei", names)
        self.assertEqual(result.dialogue_total, 3)


if __name__ == "__main__":
    unittest.main()
