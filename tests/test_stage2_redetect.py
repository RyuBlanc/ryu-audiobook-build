"""Stage 2 regression coverage for safe chapter re-detection."""
import unittest

from app.chapters.detector import Chapter
from app.chapters.redetect import redetect_chapters_preserving_edits


class SafeChapterRedetectionTests(unittest.TestCase):
    def test_exact_boundaries_keep_manual_titles_review_state_skip_and_assignments(self):
        first_text = "Chapter 1: Arrival\nMira said hello to the guard."
        second_text = "Chapter 2: Return\nMira returned safely to the village."
        assignment_text = "Mira said hello"
        start = first_text.index(assignment_text)
        chapters = [
            Chapter(
                1, "My Edited Arrival Title", first_text,
                dialogue_assignments=[{
                    "start": start, "end": start + len(assignment_text),
                    "text": assignment_text, "speakers": ["Mira"], "source": "manual",
                }],
                review_status="reviewed",
                skip_for_generation=False,
            ),
            Chapter(
                2, "My Edited Return Title", second_text,
                review_status="reviewed",
                skip_for_generation=True,
            ),
        ]

        detected, result = redetect_chapters_preserving_edits(chapters)

        self.assertEqual([item.text for item in detected], [first_text, second_text])
        self.assertEqual([item.title for item in detected], ["My Edited Arrival Title", "My Edited Return Title"])
        self.assertEqual([item.review_status for item in detected], ["reviewed", "reviewed"])
        self.assertEqual([item.skip_for_generation for item in detected], [False, True])
        self.assertEqual(detected[0].dialogue_assignments[0]["text"], assignment_text)
        self.assertEqual(detected[0].dialogue_assignments[0]["start"], start)
        self.assertEqual(result["preserved_dialogue_assignment_count"], 1)
        self.assertEqual(result["dropped_dialogue_assignment_count"], 0)
        self.assertTrue(result["text_preserved"])

    def test_redetection_splits_edited_text_and_remaps_each_assignment(self):
        source = (
            "Chapter 1: Arrival\nMira said hello to the guard.\n\n"
            "Chapter 2: Return\nMira returned safely to the village."
        )
        assignment_a = "Mira said hello"
        assignment_b = "Mira returned"
        chapters = [Chapter(
            1, "My Whole Book Edit", source,
            dialogue_assignments=[
                {"start": source.index(assignment_a), "end": source.index(assignment_a) + len(assignment_a),
                 "text": assignment_a, "speakers": ["Mira"]},
                {"start": source.index(assignment_b), "end": source.index(assignment_b) + len(assignment_b),
                 "text": assignment_b, "speakers": ["Mira"]},
            ],
            review_status="reviewed",
            skip_for_generation=False,
        )]

        detected, result = redetect_chapters_preserving_edits(chapters)

        self.assertEqual(len(detected), 2)
        self.assertEqual("".join(item.text + "\n\n" for item in detected).strip(), source)
        self.assertEqual([item.review_status for item in detected], ["needs_review", "needs_review"])
        self.assertTrue(all(len(item.dialogue_assignments) == 1 for item in detected))
        self.assertEqual(result["preserved_dialogue_assignment_count"], 2)
        self.assertEqual(result["review_reset_count"], 2)

    def test_skipped_source_text_never_becomes_included_after_split(self):
        source = "Chapter 1: Arrival\nMira spoke softly.\n\nChapter 2: Return\nMira came home."
        detected, result = redetect_chapters_preserving_edits([
            Chapter(1, "Whole book", source, skip_for_generation=True)
        ])
        self.assertEqual(len(detected), 2)
        self.assertTrue(all(ch.skip_for_generation for ch in detected))
        self.assertEqual(result["skipped_chapter_count"], 2)

    def test_text_would_be_removed_or_rewritten_aborts_without_mutating_input(self):
        source = "Chapter 1: Arrival\nMira spoke softly.\nPage 12\n\nChapter 2: Return\nMira came home."
        original = Chapter(1, "Manual Book Title", source, review_status="reviewed")
        before = (original.title, original.text, original.review_status)
        with self.assertRaisesRegex(ValueError, "No changes were saved"):
            redetect_chapters_preserving_edits([original])
        self.assertEqual((original.title, original.text, original.review_status), before)

    def test_unrecognized_headings_do_not_collapse_existing_manual_boundaries(self):
        chapters = [
            Chapter(1, "Manual Part One", "First edited passage remains unchanged."),
            Chapter(2, "Manual Part Two", "Second edited passage remains unchanged."),
        ]
        before = [(ch.title, ch.text) for ch in chapters]
        with self.assertRaisesRegex(ValueError, "manual chapter boundaries"):
            redetect_chapters_preserving_edits(chapters)
        self.assertEqual([(ch.title, ch.text) for ch in chapters], before)

    def test_empty_chapter_prevents_lossy_redetection(self):
        chapters = [
            Chapter(1, "Chapter 1", "Chapter 1: Filled\nThe story starts."),
            Chapter(2, "Empty editor draft", ""),
        ]
        with self.assertRaisesRegex(ValueError, "chapter is empty"):
            redetect_chapters_preserving_edits(chapters)
        self.assertEqual(chapters[1].text, "")


if __name__ == "__main__":
    unittest.main()
