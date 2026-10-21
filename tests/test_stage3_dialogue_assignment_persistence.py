"""Stage 3 tests for explicit, source-backed dialogue speaker assignments."""
from pathlib import Path
import unittest
from app.chapters.detector import Chapter
from app.chapters.assignment_utils import assign_dialogue_to_chapters


class DialogueAssignmentPersistenceTests(unittest.TestCase):
    def test_explicit_assignment_saves_original_offsets_and_manual_evidence(self):
        text = 'Narration first.\n\n“Rimuru, the eastern route is clear.”'
        chapter = Chapter(1, "Arrival", text)
        result = assign_dialogue_to_chapters([chapter], "“Rimuru, the eastern route is clear.”", ["Souei"])
        item = chapter.dialogue_assignments[0]
        self.assertTrue(result["saved"])
        self.assertEqual(result["chapter_number"], 1)
        self.assertEqual(text[item["start"]:item["end"]], item["text"])
        self.assertEqual(item["source"], "manual")
        self.assertEqual(item["confidence"], 1.0)
        self.assertEqual(item["speaker"], "Souei")
        self.assertEqual(item["speakers"], ["Souei"])

    def test_whitespace_wrapping_is_tolerated_without_corrupting_offsets(self):
        text = '“The eastern route is clear,\n but the river is rising.”'
        chapter = Chapter(1, "River", text)
        assign_dialogue_to_chapters([chapter], "“The eastern route is clear, but the river is rising.”", ["Souei"])
        item = chapter.dialogue_assignments[0]
        self.assertEqual(text[item["start"]:item["end"]], item["text"])
        self.assertEqual(item["text"], text)

    def test_stale_or_prototype_only_dialogue_is_rejected_without_mutation(self):
        chapter = Chapter(1, "Real", "This is the actual imported story.")
        with self.assertRaisesRegex(ValueError, "not found"):
            assign_dialogue_to_chapters([chapter], "“The eastern route is clear.”", ["Souei"])
        self.assertEqual(chapter.dialogue_assignments, [])

    def test_repeated_dialogue_requires_a_specific_chapter_or_unique_passage(self):
        chapters = [Chapter(1, "One", "“I understand.”"), Chapter(2, "Two", "Later, she said “I understand.”")]
        with self.assertRaisesRegex(ValueError, "appears more than once"):
            assign_dialogue_to_chapters(chapters, "“I understand.”", ["Rias"])
        self.assertEqual(chapters[0].dialogue_assignments, [])
        self.assertEqual(chapters[1].dialogue_assignments, [])
        result = assign_dialogue_to_chapters(chapters, "“I understand.”", ["Rias"], chapter_number=2)
        self.assertEqual(result["chapter_number"], 2)

    def test_reassignment_replaces_exact_span_but_rejects_overlaps(self):
        chapter = Chapter(1, "One", "“I understand.”")
        assign_dialogue_to_chapters([chapter], "“I understand.”", ["Rias"])
        assign_dialogue_to_chapters([chapter], "“I understand.”", ["Akeno"])
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Akeno")
        chapter.dialogue_assignments.append({"start": 1, "end": 5, "text": "I un", "speaker": "Rias", "source": "manual"})
        with self.assertRaisesRegex(ValueError, "overlaps"):
            assign_dialogue_to_chapters([chapter], "“I understand.”", ["Rias"])

    def test_multi_speaker_assignments_keep_legacy_and_new_fields(self):
        chapter = Chapter(1, "One", "“We stand together.”")
        assign_dialogue_to_chapters([chapter], "“We stand together.”", ["Rimuru", "Benimaru"], mode="chorus")
        item = chapter.dialogue_assignments[0]
        self.assertEqual(item["speaker"], "Rimuru")
        self.assertEqual(item["speakers"], ["Rimuru", "Benimaru"])
        self.assertEqual(item["multi_speaker_mode"], "chorus")



    def test_dialogue_review_uses_saved_chapter_passages_and_scopes_duplicate_quotes(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function renderDialogueReview()", adapter)
        self.assertIn("const source = String(chapter.text || '')", adapter)
        self.assertIn("chapter.dialogue_assignments || []", adapter)
        self.assertIn("data-chapter-number", adapter)
        self.assertIn("chapter_number:window.ryuPremiumPendingDialogueChapter", adapter)
        self.assertIn("dialogue passages assigned", adapter)
        self.assertIn("data-dialogue-id", adapter)
        html = (Path(__file__).resolve().parents[1] / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.assertIn("The eastern route is clear…", html)  # approved visual baseline remains untouched


if __name__ == "__main__":
    unittest.main()
