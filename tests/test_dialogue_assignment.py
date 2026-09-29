import unittest

from app.chapters.detector import Chapter
from app.chapters.dialogue import dialogue_segments


class DialogueAssignmentTests(unittest.TestCase):
    def test_dialogue_segments_suggest_named_speaker(self):
        chapter = Chapter(
            1,
            "Test",
            'Sarah looked at Michael. "Where are you going?" Michael asked.\n\n"I need some air," Sarah replied.',
        )
        segments = dialogue_segments(chapter)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].suggested_speaker, "Michael")
        self.assertGreaterEqual(segments[0].confidence, 0.9)
        self.assertEqual(segments[1].suggested_speaker, "Sarah")

    def test_chapter_manual_assignments_round_trip_as_dataclass_data(self):
        chapter = Chapter(
            1,
            "Test",
            '"Hello."',
            [{"start": 0, "end": 7, "text": '"Hello."', "speaker": "Sarah", "source": "manual"}],
        )
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Sarah")
        self.assertEqual(chapter.dialogue_assignments[0]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
