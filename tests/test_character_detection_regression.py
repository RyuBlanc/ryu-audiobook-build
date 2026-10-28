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


    def test_first_person_self_identification_is_preserved_as_narrating_character(self):
        chapter = Chapter(
            number=1,
            title="The Beginning",
            text=(
                "My name is Rias Gremory. I was walking through the courtyard. "
                "I heard footsteps behind me."
            ),
        )
        result = analyze_book([chapter])
        narrator = next(
            (character for character in result.characters
             if character.name.casefold() == "rias gremory"),
            None,
        )
        self.assertIsNotNone(narrator)
        self.assertEqual(narrator.role, "Narrating Character")

    def test_common_sentence_initial_words_are_not_misclassified_as_characters(self):
        chapter = Chapter(
            number=1,
            title="False Positive Guard",
            text=(
                "Wait, I thought this was the wrong road. "
                "Magic was everywhere in that strange room. "
                "Honestly, I did not know what to say. "
                "Later, the rain stopped."
            ),
        )
        result = analyze_book([chapter])
        names = {character.name.casefold() for character in result.characters}
        self.assertTrue(names.isdisjoint({"wait", "magic", "honestly", "later"}))



if __name__ == "__main__":
    unittest.main()
