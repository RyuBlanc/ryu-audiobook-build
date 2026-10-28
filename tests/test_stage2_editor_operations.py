"""Stage 2 editor-operation regression coverage.

These tests exercise the real editor model and guard the Premium V2 adapter against
replaying number-keyed undo history after structural edits renumber chapters.
"""
from pathlib import Path
import unittest

from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor


class Stage2ChapterOperationTests(unittest.TestCase):
    def test_rename_and_text_edit_preserve_review_skip_and_valid_assignments(self):
        text = "Mira said, Wait here."
        start = text.index("Wait here.")
        chapter = Chapter(
            1, "Opening", text,
            dialogue_assignments=[{
                "start": start, "end": start + len("Wait here."),
                "text": "Wait here.", "speaker": "Mira",
            }],
            review_status="reviewed", skip_for_generation=True,
        )
        editor = ChapterEditor([chapter])
        editor.rename(0, "  Manually corrected  ")
        editor.edit_text(0, "Mira said, Wait here. Ren answered, Go now.")

        saved = editor.chapters[0]
        self.assertEqual(saved.title, "Manually corrected")
        self.assertEqual(saved.review_status, "reviewed")
        self.assertTrue(saved.skip_for_generation)
        self.assertEqual(len(saved.dialogue_assignments), 1)
        assignment = saved.dialogue_assignments[0]
        self.assertEqual(saved.text[assignment["start"]:assignment["end"]], assignment["text"])
        self.assertEqual(assignment["speaker"], "Mira")

    def test_delete_renumbers_remaining_chapters_without_reordering_text(self):
        editor = ChapterEditor([
            Chapter(1, "One", "first body"),
            Chapter(2, "Two", "second body"),
            Chapter(3, "Three", "third body"),
        ])
        editor.delete(1)
        self.assertEqual([(c.number, c.title, c.text) for c in editor.chapters], [
            (1, "One", "first body"), (2, "Three", "third body")
        ])

    def test_move_changes_order_but_keeps_chapter_payload_attached(self):
        editor = ChapterEditor([
            Chapter(1, "One", "first body", review_status="reviewed", skip_for_generation=True),
            Chapter(2, "Two", "second body", review_status="needs_review", skip_for_generation=False),
        ])
        editor.move(0, 1)
        self.assertEqual([(c.number, c.title, c.text) for c in editor.chapters], [
            (1, "Two", "second body"), (2, "One", "first body")
        ])
        self.assertEqual(editor.chapters[1].review_status, "reviewed")
        self.assertTrue(editor.chapters[1].skip_for_generation)

    def test_merge_and_split_keep_exact_text_and_safe_assignment_offsets(self):
        first_text = "Opening passage.\n\nMira said, Wait here."
        second_text = "Ren replied, Go now.\n\nClosing passage."
        assignment = "Wait here."
        editor = ChapterEditor([
            Chapter(1, "Opening", first_text, dialogue_assignments=[{
                "start": first_text.index(assignment),
                "end": first_text.index(assignment) + len(assignment),
                "text": assignment, "speaker": "Mira",
            }]),
            Chapter(2, "Return", second_text),
        ])
        editor.merge_with_next(0)
        merged = editor.chapters[0]
        self.assertIn(first_text, merged.text)
        self.assertIn(second_text, merged.text)
        self.assertEqual(len(merged.dialogue_assignments), 1)
        item = merged.dialogue_assignments[0]
        self.assertEqual(merged.text[item["start"]:item["end"]], assignment)

        editor.split(0, 1, "Dialogue")
        self.assertEqual(len(editor.chapters), 2)
        for chapter in editor.chapters:
            for item in chapter.dialogue_assignments:
                self.assertEqual(chapter.text[item["start"]:item["end"]], item["text"])
        joined = "\n\n".join(c.text for c in editor.chapters)
        self.assertIn("Opening passage.", joined)
        self.assertIn("Wait here.", joined)
        self.assertIn("Go now.", joined)
        self.assertIn("Closing passage.", joined)

    def test_invalid_split_does_not_mutate_chapter_collection(self):
        chapter = Chapter(1, "Only", "one paragraph")
        editor = ChapterEditor([chapter])
        before = [(c.number, c.title, c.text) for c in editor.chapters]
        with self.assertRaisesRegex(ValueError, "between paragraphs"):
            editor.split(0, 0, "New")
        self.assertEqual([(c.number, c.title, c.text) for c in editor.chapters], before)

    def test_adapter_clears_number_keyed_undo_history_after_each_structural_operation(self):
        adapter_path = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter_path.read_text(encoding="utf-8")
        self.assertIn("function clearChapterHistory()", source)
        self.assertIn("chapterUndoStacks.clear();", source)
        self.assertIn("chapterRedoStacks.clear();", source)

        # A successful structural mutation invalidates stale per-number history.
        expected_calls = (
            "await call('chapter.delete', {number});\n        clearChapterHistory();",
            "const result = await call('chapter.redetect', {selected_number:selectedBefore});\n            clearChapterHistory();",
            "const created = await call('chapter.add', {title: title.trim() || 'Chapter ' + (chapters.length + 1), text: ''});\n            clearChapterHistory();",
            "await call('chapter.reorder', {number, new_number: destination});\n            clearChapterHistory();",
            "await call('chapter.merge', {number});\n            clearChapterHistory();",
            "const result = await call('chapter.split',{number:c.number,title:$('chapterTitle')?.textContent||c.title,text,split_at:splitAt});\n      clearChapterHistory();",
        )
        for expected in expected_calls:
            with self.subTest(operation=expected.splitlines()[0]):
                self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
