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


    def test_indian_script_speaker_labels_with_combining_marks_keep_full_identity(self):
        import unicodedata

        chapter = Chapter(
            number=1,
            title="Indian script speaker identities",
            text=(
                'मीरा: “नमस्ते।”\n'
                'मीरा: “धन्यवाद।”\n'
                'महेंद्र सिंह: “आप कैसे हैं?”\n'
                'महेंद्र सिंह: “मैं ठीक हूँ।”\n'
                'கவிதா: “வணக்கம்।”\n'
                'கவிதா: “நன்றி।”\n'
                'లక్ష్మి: “నమస్కారం।”\n'
                'లక్ష్మి: “ధన్యవాదాలు।”\n'
                'রিয়া: “হ্যালো।”\n'
                'রিয়া: “ধন্যবাদ।”\n'
                'ગૌરી: “કેમ છો?”\n'
                'ગૌરી: “આભાર।”\n'
                'ਗੁਰਮੀਤ: “ਸਤ ਸ੍ਰੀ ਅਕਾਲ।”\n'
                'ਗੁਰਮੀਤ: “ਧੰਨਵਾਦ।”'
            ),
        )
        result = analyze_book([chapter])
        by_key = {
            unicodedata.normalize("NFC", character.name).casefold(): character
            for character in result.characters
        }
        expected = ("मीरा", "महेंद्र सिंह", "கவிதா", "లక్ష్మి", "রিয়া", "ગૌરી", "ਗੁਰਮੀਤ")
        for name in expected:
            with self.subTest(name=name):
                key = unicodedata.normalize("NFC", name).casefold()
                self.assertIn(key, by_key)
                self.assertEqual(by_key[key].dialogue_count, 2)
        self.assertEqual(result.dialogue_total, 14)
        self.assertEqual(result.unassigned_dialogue, 0)

    def test_indian_script_speech_tags_after_quotes_keep_combining_marks(self):
        chapter = Chapter(
            number=1,
            title="Indian script speech tags",
            text=(
                '“नमस्ते,” said मीरा.\n'
                '“வணக்கம்,” said கவிதா.\n'
                '“నమస్కారం,” said లక్ష్మి.\n'
                '“হ্যালো,” said রিয়া.\n'
                '“કેમ છો?” said ગૌરી.\n'
                '“ਸਤ ਸ੍ਰੀ ਅਕਾਲ,” said ਗੁਰਮੀਤ.'
            ),
        )
        result = analyze_book([chapter])
        names = {character.name for character in result.characters}
        self.assertEqual(
            names,
            {"मीरा", "கவிதா", "లక్ష్మి", "রিয়া", "ગૌરી", "ਗੁਰਮੀਤ"},
        )
        self.assertEqual(result.dialogue_total, 6)
        self.assertEqual(result.unassigned_dialogue, 0)

    def test_non_letter_symbols_are_not_absorbed_into_speaker_names(self):
        chapter = Chapter(
            number=1,
            title="Invalid decorated speaker label",
            text='मीरा😊: “नमस्ते।”',
        )
        result = analyze_book([chapter])
        self.assertEqual(result.characters, [])
        self.assertEqual(result.dialogue_total, 1)
        self.assertEqual(result.unassigned_dialogue, 1)

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
