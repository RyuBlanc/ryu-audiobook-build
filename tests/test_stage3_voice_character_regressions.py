"""Stage 3 regression tests for voice cast analysis and dialogue assignment."""

import unittest

from app.chapters.assignment_utils import (
    assignment_speakers,
    assign_dialogue_to_chapters,
    normalize_assignment,
    unassign_dialogue_from_chapters,
)
from app.chapters.characters import analyze_book
from app.chapters.detector import Chapter


class Stage3DialogueAssignmentTests(unittest.TestCase):
    def test_legacy_single_speaker_assignment_remains_readable(self):
        self.assertEqual(assignment_speakers({"speaker": "Mira"}), ["Mira"])
        self.assertEqual(assignment_speakers({"speakers": ["Mira", "Ren"], "speaker": "Mira"}),
                         ["Mira", "Ren"])

    def test_multi_speaker_assignment_persists_legacy_compatible_shape(self):
        chapter = Chapter(1, "Chapter 1", 'Mira said, “We should leave now.”')
        result = assign_dialogue_to_chapters(
            [chapter], "We should leave now.", ["Mira", "Ren"], chapter_number=1, mode="chorus"
        )

        self.assertTrue(result["saved"])
        self.assertEqual(result["speakers"], ["Mira", "Ren"])
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Mira")
        self.assertEqual(chapter.dialogue_assignments[0]["speakers"], ["Mira", "Ren"])
        self.assertEqual(chapter.dialogue_assignments[0]["multi_speaker_mode"], "chorus")
        self.assertEqual(chapter.dialogue_assignments[0]["confidence"], 1.0)

    def test_ambiguous_dialogue_is_rejected_without_mutating_assignments(self):
        chapter = Chapter(1, "Chapter 1", '“Come back.” Then she called, “Come back.”')
        before = list(chapter.dialogue_assignments)

        with self.assertRaisesRegex(ValueError, "appears more than once"):
            assign_dialogue_to_chapters([chapter], "Come back.", ["Mira"])

        self.assertEqual(chapter.dialogue_assignments, before)

    def test_stale_source_span_cannot_remove_a_saved_assignment(self):
        chapter = Chapter(1, "Chapter 1", "The saved text has changed.")
        chapter.dialogue_assignments = [
            {"start": 0, "end": 11, "text": "Wait for me.", "speaker": "Mira"}
        ]

        with self.assertRaisesRegex(ValueError, "chapter text changed"):
            unassign_dialogue_from_chapters(
                [chapter], 1, 0, 11, "Wait for me."
            )

        self.assertEqual(len(chapter.dialogue_assignments), 1)

    def test_exact_unassignment_removes_only_the_matching_assignment(self):
        text = "Mira said, “Wait here.” Ren answered, “I will.”"
        chapter = Chapter(1, "Chapter 1", text)
        first = text.index("Wait here.")
        chapter.dialogue_assignments = [
            {"start": first, "end": first + len("Wait here."), "text": "Wait here.", "speaker": "Mira"},
            {"start": text.index("I will."), "end": text.index("I will.") + len("I will."),
             "text": "I will.", "speaker": "Ren"},
        ]

        result = unassign_dialogue_from_chapters(
            [chapter], 1, first, first + len("Wait here."), "Wait here."
        )

        self.assertTrue(result["removed"])
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Ren")

    def test_normalizing_empty_speaker_list_removes_stale_assignment_fields(self):
        item = {"text": "Hello.", "speaker": "Old", "speakers": ["Old"], "multi_speaker_mode": "chorus"}
        normalized = normalize_assignment(item, [])

        self.assertEqual(normalized, {"text": "Hello."})
        self.assertEqual(item["speaker"], "Old", "normalization must not mutate its input")


class Stage3CharacterAnalysisTests(unittest.TestCase):
    def test_manual_assignments_remain_character_candidates_during_reanalysis(self):
        chapter = Chapter(
            1,
            "Chapter 1",
            '“Wait for me,” she said. “I am coming,” he replied.',
            dialogue_assignments=[
                {"start": 0, "end": 15, "text": "Wait for me.", "speaker": "Mira"},
                {"start": 16, "end": 35, "text": "I am coming.", "speakers": ["Ren", "Mira"]},
            ],
        )

        result = analyze_book([chapter])
        names = {character.name.casefold() for character in result.characters}

        self.assertIn("mira", names)
        self.assertIn("ren", names)
        self.assertGreaterEqual(result.dialogue_total, 2)


if __name__ == "__main__":
    unittest.main()
