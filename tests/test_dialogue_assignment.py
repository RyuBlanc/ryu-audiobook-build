import unittest

from app.chapters.detector import Chapter
from app.chapters.dialogue import dialogue_segments, dialogue_segment_for_selection
from app.chapters.assignment_utils import assignment_speakers, normalize_assignment, build_book_character_registry


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


    def test_multi_speaker_assignment_round_trip(self):
        item = normalize_assignment(
            {
                "start": 0,
                "end": 8,
                "text": '"Hello."',
                "source": "manual",
            },
            ["Rias", "Akeno"],
            "chorus",
        )
        self.assertEqual(assignment_speakers(item), ["Rias", "Akeno"])
        self.assertEqual(item["speaker"], "Rias")
        self.assertEqual(item["multi_speaker_mode"], "chorus")

    def test_book_character_registry_includes_other_chapters_and_cast(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.core.state import save_state

        chapters = [
            Chapter(
                1,
                "One",
                '"Hello."',
                [{"start": 0, "end": 8, "text": '"Hello."', "speaker": "Kurenai", "source": "manual"}],
            ),
            Chapter(
                2,
                "Two",
                '"Hi."',
                [{"start": 0, "end": 5, "text": '"Hi."', "speaker": "Rias", "source": "manual"}],
            ),
        ]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            save_state(root, {"voice_cast": {"Akeno": "Anime Voice"}})
            registry = build_book_character_registry(chapters, root)
            self.assertIn("kurenai", registry)
            self.assertIn("akeno", registry)
            self.assertIn(1, registry["kurenai"]["chapters"])
            self.assertIn("saved voice cast", registry["akeno"]["sources"])

    def test_fast_assignment_respects_existing_exact_manual_speaker(self):
        text = '"I am here."'
        chapter = Chapter(
            1,
            "Test",
            text,
            [{"start": 0, "end": len(text), "text": text, "speaker": "Kurenai", "source": "manual"}],
        )
        segment = dialogue_segment_for_selection(chapter, 0, len(text))
        self.assertIsNotNone(segment)
        self.assertEqual(segment.suggested_speaker, "Kurenai")
        self.assertEqual(segment.confidence, 1.0)


    def test_project_scoped_confirmed_memory_improves_later_fast_speaker_suggestion(self):
        from tempfile import TemporaryDirectory
        from app.chapters.character_learning import record_project_speaker_assignment
        from app.core.state import save_state

        with TemporaryDirectory() as folder:
            root = Path(folder)
            save_state(root, {"series": "Slime series"})
            previous_text = (
                "Souei checked the eastern route from the gate. "
                "He looked at the river and said, “The eastern route is clear.” "
                "The commander waited for his report."
            )
            previous_start = previous_text.index("“")
            previous_end = previous_text.index("”", previous_start) + 1
            previous_chapter = Chapter(1, "The Oath", previous_text)
            record_project_speaker_assignment(root, previous_chapter, {
                "start": previous_start,
                "end": previous_end,
                "speaker": "Souei",
                "source": "manual",
            })

            next_text = (
                "Souei checked the eastern route from the gate. "
                "He looked at the river. “The eastern route is clear.” "
                "The commander waited for his report."
            )
            start = next_text.index("“")
            end = next_text.index("”", start) + 1
            next_chapter = Chapter(2, "The Report", next_text)
            segment = dialogue_segment_for_selection(
                next_chapter, start, end, project_folder=root
            )

            self.assertIsNotNone(segment)
            self.assertTrue(
                any(
                    name == "Souei" and "confirmed example" in evidence
                    for name, _confidence, evidence in segment.suggestions
                ),
                segment.suggestions,
            )
            # The memory informs the picker only; the source chapter is not
            # auto-assigned and the user's confirmation is still required.
            self.assertEqual(next_chapter.dialogue_assignments, [])



if __name__ == "__main__":
    unittest.main()
