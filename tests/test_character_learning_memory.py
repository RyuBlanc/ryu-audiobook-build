"""Regression tests for source-grounded, series-scoped speaker learning."""
from pathlib import Path
import tempfile
import unittest

from app.chapters.character_learning import (
    load_learning_examples,
    prepare_learning_index,
    rank_speaker_suggestions,
    record_assignment_feedback,
    remove_assignment_feedback,
    source_grounded_speaker_for_continuity,
)
from app.chapters.characters import _is_plausible_name


class CharacterLearningMemoryTests(unittest.TestCase):
    def test_only_explicit_confirmations_are_persisted_and_series_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "learning.json"
            source = "Rimuru Tempest considered the plan.\\nRimuru Tempest said, “We should leave before sunrise.” She smiled."
            start = source.index("“")
            end = source.index("”", start) + 1
            result = record_assignment_feedback(
                series="Slime series", speaker="Rimuru Tempest", aliases=["Rimuru", "Great Rimuru"],
                chapter_text=source, start=start, end=end, source_text=source[start:end],
                chapter_title="The Oath", path=store,
            )
            self.assertTrue(result["saved"])
            examples = load_learning_examples("Slime series", path=store)
            self.assertEqual(len(examples), 1)
            self.assertEqual(examples[0]["speaker"], "Rimuru Tempest")
            self.assertEqual(load_learning_examples("Different series", path=store), [])

    def test_feedback_refuses_stale_or_inaccurate_source_spans(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "learning.json"
            source = "Souei said, “The eastern route is clear.”"
            start = source.index("“")
            end = source.index("”", start) + 1
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                record_assignment_feedback(
                    series="Slime", speaker="Souei", chapter_text=source,
                    start=start, end=end, source_text="“The western route is clear.”", path=store,
                )
            self.assertEqual(load_learning_examples("Slime", path=store), [])

    def test_explicit_before_and_after_speech_tags_rank_known_characters_high(self):
        cast = [
            {"name": "Rimuru Tempest", "aliases": ["Rimuru", "Great Rimuru"]},
            {"name": "Souei", "aliases": ["Shadow"]},
        ]
        before = "Rimuru Tempest said, “We should leave before sunrise.”"
        start = before.index("“")
        end = before.index("”", start) + 1
        ranked = rank_speaker_suggestions(
            chapter_text=before, start=start, end=end, known_characters=cast
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["name"], "Rimuru Tempest")
        self.assertGreaterEqual(ranked[0]["confidence"], 0.90)

        after = "“The eastern route is clear,” Souei replied."
        start = after.index("“")
        end = after.index("”", start) + 1
        ranked_after = rank_speaker_suggestions(
            chapter_text=after, start=start, end=end, known_characters=cast
        )
        self.assertTrue(ranked_after)
        self.assertEqual(ranked_after[0]["name"], "Souei")

    def test_detected_alias_is_returned_as_canonical_saved_character(self):
        source = 'Rimuru said, “We should leave before sunrise.”'
        start = source.index("“")
        end = source.index("”", start) + 1
        ranked = rank_speaker_suggestions(
            chapter_text=source, start=start, end=end,
            detected=[{"name": "Rimuru", "confidence": 0.96, "evidence": "Detected name"}],
            known_characters=[{"name": "Rimuru Tempest", "aliases": ["Rimuru", "Great Rimuru"]}],
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["name"], "Rimuru Tempest")
        self.assertGreaterEqual(ranked[0]["confidence"], 0.90)

    def test_pronoun_speech_tag_continues_the_last_confirmed_speaker(self):
        source = '“The gate is closed.” He replied.'
        start = source.index("“")
        end = source.index("”", start) + 1
        ranked = rank_speaker_suggestions(
            chapter_text=source, start=start, end=end,
            known_characters=[{"name": "Souei", "aliases": ["Shadow"]}],
            last_speaker="Souei",
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["name"], "Souei")
        self.assertIn("Pronoun speech tag", ranked[0]["evidence"])

    def test_unconfirmed_high_confidence_guess_does_not_become_speaker_anchor(self):
        # Similarity/learning scores may be useful suggestions, but they are not
        # explicit source proof and must not cascade into later pronoun guesses.
        learned_match = [{
            "name": "Souei", "confidence": 0.97,
            "evidence": "Matches a confirmed example for Souei (context similarity 99%).",
        }]
        self.assertEqual(source_grounded_speaker_for_continuity(learned_match), "")

        saved_cast_fallback = [{
            "name": "Souei", "confidence": 0.90,
            "evidence": "Saved character in this series; no strong local speech evidence yet.",
        }]
        self.assertEqual(source_grounded_speaker_for_continuity(saved_cast_fallback), "")

    def test_direct_name_and_speech_tag_can_anchor_pronoun_continuity(self):
        direct = [{
            "name": "Souei", "confidence": 0.97,
            "evidence": "Explicit character name and speech tag found next to this passage.",
        }]
        self.assertEqual(source_grounded_speaker_for_continuity(direct), "Souei")
        self.assertEqual(source_grounded_speaker_for_continuity([]), "")

    def test_confirmed_examples_improve_later_context_ranking_and_are_removed_on_unassign(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "learning.json"
            source = (
                "Souei checked the eastern route from the gate. "
                "He looked at the river and said, “The eastern route is clear.” "
                "The commander waited for his report."
            )
            start = source.index("“")
            end = source.index("”", start) + 1
            record_assignment_feedback(
                series="Slime series", speaker="Souei", aliases=["Shadow"],
                chapter_text=source, start=start, end=end, source_text=source[start:end],
                chapter_title="The Oath", path=store,
            )
            examples = load_learning_examples("Slime series", path=store)
            self.assertEqual(len(examples), 1)
            ranked = rank_speaker_suggestions(
                chapter_text=source, start=start, end=end,
                known_characters=[{"name": "Souei", "aliases": ["Shadow"], "series": "Slime series"}],
                learning_examples=examples,
            )
            self.assertEqual(ranked[0]["name"], "Souei")
            result = remove_assignment_feedback(
                series="Slime series", chapter_text=source, start=start, end=end,
                source_text=source[start:end], path=store,
            )
            self.assertTrue(result["removed"])
            self.assertEqual(load_learning_examples("Slime series", path=store), [])

    def test_confirmed_learning_does_not_leak_between_series_with_same_character_name(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "learning.json"
            source = 'Rimuru Tempest checked the gate. “The northern gate is clear.” He waited.'
            start = source.index("“")
            end = source.index("”", start) + 1
            record_assignment_feedback(
                series="Slime series", speaker="Rimuru Tempest",
                chapter_text=source, start=start, end=end, source_text=source[start:end],
                chapter_title="The Oath", path=store,
            )
            examples = load_learning_examples("Slime series", path=store)
            ranked = rank_speaker_suggestions(
                chapter_text=source, start=start, end=end,
                known_characters=[
                    {"name": "Rimuru Tempest", "series": "Slime series"},
                    {"name": "Rimuru Tempest", "series": "High School DxD"},
                ],
                learning_examples=examples,
            )
            self.assertEqual([row["series"] for row in ranked], ["Slime series"])
            self.assertIn("confirmed example", ranked[0]["evidence"])

    def test_pronoun_continuity_does_not_boost_the_same_name_in_another_series(self):
        source = "“The gate is closed.” He replied."
        start = source.index("“")
        end = source.index("”", start) + 1
        ranked = rank_speaker_suggestions(
            chapter_text=source, start=start, end=end,
            known_characters=[
                {"name": "Souei", "series": "Slime series"},
                {"name": "Souei", "series": "Other series"},
            ],
            last_speaker="Souei",
            last_speaker_series="Slime series",
        )
        self.assertTrue(ranked)
        self.assertEqual([row["series"] for row in ranked], ["Slime series"])
        self.assertIn("Pronoun speech tag", ranked[0]["evidence"])


    def test_learning_index_is_keyed_by_series_and_canonical_speaker(self):
        rows = [
            {"series": "Slime series", "speaker": "Souei", "context": "slime example"},
            {"series": "Other series", "speaker": "Souei", "context": "other example"},
            {"series": "Slime series", "speaker": "Rimuru Tempest", "context": "rimuru example"},
        ]
        index = prepare_learning_index(rows)
        self.assertEqual(index[("slime series", "souei")], [rows[0]])
        self.assertEqual(index[("other series", "souei")], [rows[1]])
        self.assertEqual(index[("slime series", "rimuru tempest")], [rows[2]])
        self.assertNotIn(("unrelated series", "souei"), index)

    def test_scoped_learning_index_does_not_promote_same_name_from_another_series(self):
        source = '“The gate is closed.” He replied.'
        start = source.index("“")
        end = source.index("”", start) + 1
        examples = [
            {"series": "Slime series", "speaker": "Souei",
             "normalized_dialogue": "the gate is closed",
             "context": "Souei guarded the eastern gate. The gate is closed. He replied."}
        ]
        index = prepare_learning_index(examples)
        ranked = rank_speaker_suggestions(
            chapter_text=source, start=start, end=end,
            known_characters=[{"name": "Souei", "series": "Other series"}],
            learning_examples=index,
        )
        self.assertEqual(ranked, [])

    def test_sentence_initial_english_words_are_not_accepted_as_character_names(self):
        for word in ("Having", "Well", "Right", "Already", "Magic", "Speaking", "Feeling", "Let", "Two"):
            self.assertFalse(_is_plausible_name(word), word)
        self.assertTrue(_is_plausible_name("Souei"))
        self.assertTrue(_is_plausible_name("Rimuru Tempest"))
        self.assertTrue(_is_plausible_name("綾小路清隆"))


if __name__ == "__main__":
    unittest.main()
