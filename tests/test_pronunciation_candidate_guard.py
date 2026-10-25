"""Regression tests for pronunciation candidates grounded in actual character names."""
import unittest

from app.ai.robust import _fallback_pronunciations, _safe_merge
from app.tts.pronunciation_suggester import (
    is_likely_character_name_candidate,
    suggest_names_from_text,
)


class PronunciationCandidateGuardTests(unittest.TestCase):
    def test_capitalized_prose_and_titles_are_not_name_pronunciation_candidates(self):
        for phrase in (
            "Having", "Well", "Right", "Already", "Magic", "Speaking",
            "Feeling", "Let", "Two", "The Oath", "The Other World",
            "Dog God of the Fallen", "Kuoh Academy",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(is_likely_character_name_candidate(phrase), phrase)

    def test_confirmed_or_plausible_character_names_are_allowed(self):
        self.assertTrue(is_likely_character_name_candidate("Himejima Hanezu"))
        self.assertTrue(is_likely_character_name_candidate("Jin Natsume"))
        self.assertTrue(is_likely_character_name_candidate("Azazel", known_names={"Azazel"}))
        self.assertTrue(is_likely_character_name_candidate("リアス", script="Katakana"))

    def test_text_extractor_does_not_treat_random_capitalization_as_names(self):
        source = (
            "Having left the room, Jin Natsume spoke to Himejima Hanezu. "
            "The Oath was old. The Other World had fallen."
        )
        names = {name.casefold() for name in suggest_names_from_text(source)}
        self.assertIn("jin natsume", names)
        self.assertIn("himejima hanezu", names)
        self.assertNotIn("having", names)
        self.assertNotIn("the oath", names)
        self.assertNotIn("the other world", names)
        self.assertNotIn("dog god of the fallen", names)

    def test_ai_english_words_do_not_become_pronunciation_rules_when_mislabeled_japanese(self):
        out = {
            "characters": [], "pronunciation": [], "dialogue": [],
            "scenes": [], "continuity_notes": [],
        }
        data = {
            "characters": [
                {"name": "Having", "confidence": 0.99},
                {"name": "The Oath", "confidence": 0.97},
                {"name": "Himejima Hanezu", "confidence": 0.96},
                {"name": "リアス", "confidence": 0.95},
            ],
            "pronunciation": [
                {"written": "Having", "spoken": "Hah-ving", "source_language": "Japanese", "script": "Latin", "confidence": 0.99},
                {"written": "The Oath", "spoken": "Thee Oh-ahth", "source_language": "Japanese", "script": "Latin", "confidence": 0.99},
                {"written": "Himejima Hanezu", "spoken": "Hee-meh-jee-mah Hah-neh-zoo", "source_language": "Japanese", "script": "Latin", "confidence": 0.96},
                {"written": "リアス", "spoken": "Riasu", "source_language": "Japanese", "script": "Katakana", "confidence": 0.95},
            ],
        }
        source = "Having finished the chapter, Himejima Hanezu replied. The Oath was old. リアス arrived."
        _safe_merge(None, out, data, set(), source_text=source)
        saved_characters = {row["name"] for row in out["characters"]}
        saved_rules = {row["written"] for row in out["pronunciation"]}
        self.assertNotIn("Having", saved_characters)
        self.assertNotIn("The Oath", saved_characters)
        self.assertIn("Himejima Hanezu", saved_characters)
        self.assertIn("リアス", saved_characters)
        self.assertNotIn("Having", saved_rules)
        self.assertNotIn("The Oath", saved_rules)
        self.assertIn("Himejima Hanezu", saved_rules)
        self.assertIn("リアス", saved_rules)

    def test_fallback_pronunciation_uses_detected_cast_not_every_capitalized_word(self):
        result = {
            "characters": [
                {"name": "Having", "aliases": []},
                {"name": "Jin Natsume", "aliases": ["Jin"]},
            ],
            "pronunciation": [],
        }
        source = "Having walked away. Jin Natsume said hello. Jin waved."
        _fallback_pronunciations(source, result)
        rules = {row["written"] for row in result["pronunciation"]}
        self.assertNotIn("Having", rules)
        self.assertIn("Jin Natsume", rules)
        self.assertNotIn("Jin", rules)


if __name__ == "__main__":
    unittest.main()
