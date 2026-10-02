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


    def test_speaker_suggestions_include_evidence_and_do_not_randomly_switch_dialogue(self):
        chapter = Chapter(
            1,
            "Test",
            'Sarah looked at Michael. "Where are you going?" Michael asked. '
            '"I need some air," Sarah replied.',
        )
        segments = dialogue_segments(chapter)
        self.assertTrue(segments[0].start < segments[0].end)
        self.assertTrue(segments[0].suggestions)
        self.assertEqual(segments[0].suggestions[0][0], "Michael")
        self.assertIn("speaker name", segments[0].suggestions[0][2].lower())

    def test_manual_assignment_is_used_as_exact_dialogue_evidence(self):
        text = '"Come with me."\n\n"Okay."'
        chapter = Chapter(
            1,
            "Test",
            text,
            [{"start": 0, "end": 15, "text": '"Come with me."', "speaker": "Sarah", "source": "manual"}],
        )
        segments = dialogue_segments(chapter)
        self.assertEqual(segments[0].suggested_speaker, "Sarah")
        self.assertEqual(segments[0].suggestions[0][0], "Sarah")
        self.assertEqual(segments[0].suggestions[0][1], 1.0)

    def test_editing_chapter_text_remaps_unchanged_dialogue_assignment(self):
        from app.chapters.editor import ChapterEditor

        chapter = Chapter(
            1,
            "Test",
            '"Hello, Sarah."',
            [{"start": 0, "end": 15, "text": '"Hello, Sarah."', "speaker": "Michael", "source": "manual"}],
        )
        editor = ChapterEditor([chapter])
        editor.edit_text(0, 'Narration intro.\n\n"Hello, Sarah."')
        assignment = editor.chapters[0].dialogue_assignments[0]
        self.assertEqual(assignment["speaker"], "Michael")
        self.assertEqual(editor.chapters[0].text[assignment["start"]:assignment["end"]], '"Hello, Sarah."')

    def test_editing_dialogue_drops_stale_assignment_instead_of_retargeting(self):
        from app.chapters.editor import ChapterEditor

        chapter = Chapter(
            1,
            "Test",
            '"Hello."',
            [{"start": 0, "end": 8, "text": '"Hello."', "speaker": "Sarah", "source": "manual"}],
        )
        editor = ChapterEditor([chapter])
        editor.edit_text(0, '"Goodbye."')
        self.assertEqual(editor.chapters[0].dialogue_assignments, [])

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
