import unittest

from app.chapters.detector import Chapter
from app.chapters.speaker_segmentation import (
    NARRATOR_ROLE,
    segment_chapter_speakers,
    segment_project_speakers,
)


class NarratorSegmentationTests(unittest.TestCase):
    def test_unquoted_paragraphs_are_narrator_and_quoted_unknown_dialogue_needs_review(self):
        text = (
            "Yesterday, his physical condition had been poor.\n\n"
            "“So then, since I'll be buying souvenirs, you're going to lie down?”\n\n"
            "Saying so, she stood smiling at the front door."
        )
        rows = segment_chapter_speakers(Chapter(1, "Prologue", text))
        self.assertEqual([row.kind for row in rows], [
            "narration", "needs_speaker_review", "narration"
        ])
        self.assertEqual(rows[0].speaker, NARRATOR_ROLE)
        self.assertIsNone(rows[1].speaker)
        self.assertEqual(rows[1].text, "“So then, since I'll be buying souvenirs, you're going to lie down?”")
        self.assertEqual(rows[2].text, "Saying so, she stood smiling at the front door.")

    def test_saved_character_assignment_overrides_quote_review_and_preserves_exact_source(self):
        text = 'Before the conversation. “Hello there.” After the conversation.'
        start = text.index("“Hello there.”")
        end = start + len("“Hello there.”")
        chapter = Chapter(1, "One", text, [{
            "start": start, "end": end, "text": text[start:end],
            "speaker": "Mira", "source": "manual",
        }])
        rows = segment_chapter_speakers(chapter)
        middle = next(row for row in rows if row.start == start)
        self.assertEqual(middle.kind, "character_dialogue")
        self.assertEqual(middle.speakers, ("Mira",))
        self.assertEqual(middle.text, text[start:end])
        self.assertEqual(middle.source, "manual")

    def test_unquoted_ai_and_manual_dialogue_assignments_are_not_sent_to_narrator(self):
        text = "Mira said: I will return. The sun set behind the hill."
        start = text.index("I will return.")
        end = start + len("I will return.")
        chapter = Chapter(1, "One", text, [{
            "start": start, "end": end, "text": text[start:end],
            "speaker": "Mira", "source": "ai", "confidence": 0.91,
        }])
        rows = segment_chapter_speakers(chapter)
        assigned = next(row for row in rows if row.start == start)
        narrator = next(row for row in rows if row.start > end)
        self.assertEqual(assigned.kind, "character_dialogue")
        self.assertEqual(assigned.speaker, "Mira")
        self.assertEqual(assigned.source, "ai")
        self.assertEqual(narrator.kind, "narration")
        self.assertEqual(narrator.speaker, NARRATOR_ROLE)

    def test_dash_style_dialogue_is_not_mistaken_for_narration(self):
        text = "He turned toward the door.\n—Leave now!\nThe room became quiet."
        rows = segment_chapter_speakers(Chapter(2, "Two", text))
        self.assertEqual([row.kind for row in rows], [
            "narration", "needs_speaker_review", "narration"
        ])
        self.assertEqual(next(row for row in rows if row.kind == "needs_speaker_review").text, "—Leave now!")

    def test_smart_single_and_japanese_quote_spans_require_speaker_review(self):
        text = "She hesitated. ‘I understand.’ 彼女は「わかった」と答えた。 Then she left."
        rows = segment_chapter_speakers(Chapter(3, "Three", text))
        review = [row for row in rows if row.kind == "needs_speaker_review"]
        self.assertEqual(len(review), 2)
        self.assertIn("‘I understand.’", [row.text for row in review])
        self.assertIn("「わかった」", [row.text for row in review])

    def test_narrator_is_a_reserved_speaker_not_a_character(self):
        text = '"A line."'
        chapter = Chapter(1, "One", text, [{
            "start": 0, "end": len(text), "text": text,
            "speaker": "Narrator", "source": "manual",
        }])
        rows = segment_chapter_speakers(chapter)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "narration")
        self.assertEqual(rows[0].speaker, "Narrator")

    def test_stale_or_invalid_assignments_do_not_hide_text_from_narrator(self):
        text = "The rain fell over the town."
        chapter = Chapter(1, "One", text, [
            {"start": 0, "end": len(text), "text": "old source text",
             "speaker": "Mira", "source": "manual"},
            {"start": -2, "end": 4, "speaker": "Mira"},
            {"start": 0, "end": len(text) + 4, "speaker": "Mira"},
        ])
        rows = segment_chapter_speakers(chapter)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "narration")
        self.assertEqual(rows[0].text, text)

    def test_conflicting_overlapping_saved_speakers_require_review(self):
        text = "“Do not go.”"
        chapter = Chapter(1, "One", text, [
            {"start": 0, "end": len(text), "text": text, "speaker": "Mira", "source": "manual"},
            {"start": 0, "end": len(text), "text": text, "speaker": "Rin", "source": "ai"},
        ])
        rows = segment_chapter_speakers(chapter)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "needs_speaker_review")
        self.assertTrue(rows[0].needs_review)

    def test_segmentation_is_deterministic_and_keeps_chapter_source_offsets(self):
        first = Chapter(1, "One", "Intro.\n\n“Hello.”\n\nConclusion.")
        second = Chapter(2, "Two", "Second chapter prose.")
        rows_a = segment_project_speakers([first, second])
        rows_b = segment_project_speakers([first, second])
        self.assertEqual(rows_a, rows_b)
        for row in rows_a:
            source = first.text if row.chapter_number == 1 else second.text
            self.assertEqual(source[row.start:row.end], row.text)


if __name__ == "__main__":
    unittest.main()
