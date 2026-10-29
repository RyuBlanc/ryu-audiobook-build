"""Cross-stage regressions for cast assignment integrity during chapter editing."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.project import Project
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.ui.premium_v2_host import PremiumV2Bridge


class CrossStageChapterAssignmentIntegrityTests(unittest.TestCase):
    def test_merge_preserves_and_offsets_assignments_from_both_chapters(self):
        left_text = "Mira said, Wait here."
        right_text = "Ren answered, Go now."
        left_line = "Wait here."
        right_line = "Go now."
        left = Chapter(1, "Opening", left_text, dialogue_assignments=[{
            "start": left_text.index(left_line), "end": left_text.index(left_line) + len(left_line),
            "text": left_line, "speaker": "Mira", "source": "manual",
        }])
        right = Chapter(2, "Return", right_text, dialogue_assignments=[{
            "start": right_text.index(right_line), "end": right_text.index(right_line) + len(right_line),
            "text": right_line, "speaker": "Ren", "speakers": ["Ren", "Mira"],
            "multi_speaker_mode": "chorus", "confidence": 1.0, "source": "manual",
        }])

        editor = ChapterEditor([left, right])
        editor.merge_with_next(0)

        merged = editor.chapters[0]
        self.assertEqual(len(editor.chapters), 1)
        self.assertEqual(len(merged.dialogue_assignments), 2)
        for item in merged.dialogue_assignments:
            self.assertEqual(merged.text[item["start"]:item["end"]], item["text"])
        by_text = {item["text"]: item for item in merged.dialogue_assignments}
        self.assertEqual(by_text[left_line]["speaker"], "Mira")
        self.assertEqual(by_text[right_line]["speaker"], "Ren")
        self.assertEqual(by_text[right_line]["speakers"], ["Ren", "Mira"])
        self.assertEqual(by_text[right_line]["multi_speaker_mode"], "chorus")
        self.assertEqual(by_text[right_line]["confidence"], 1.0)

    def test_paragraph_split_moves_assignments_and_preserves_multispeaker_metadata(self):
        text = "Intro paragraph.\n\nMira said, Wait here.\n\nFinal paragraph."
        first_line = "Intro paragraph."
        dialogue = "Wait here."
        second_start = text.index(dialogue)
        chapter = Chapter(1, "Full Chapter", text, dialogue_assignments=[{
            "start": text.index(first_line), "end": text.index(first_line) + len(first_line),
            "text": first_line, "speaker": "Narrator",
        }, {
            "start": second_start, "end": second_start + len(dialogue),
            "text": dialogue, "speaker": "Mira", "speakers": ["Mira", "Ren"],
            "multi_speaker_mode": "chorus", "confidence": 0.95,
        }])

        editor = ChapterEditor([chapter])
        editor.split(0, 1, "Dialogue")

        first, second = editor.chapters
        self.assertEqual(first.number, 1)
        self.assertEqual(second.number, 2)
        self.assertEqual([item["text"] for item in first.dialogue_assignments], [first_line])
        self.assertEqual([item["text"] for item in second.dialogue_assignments], [dialogue])
        item = second.dialogue_assignments[0]
        self.assertEqual(second.text[item["start"]:item["end"]], dialogue)
        self.assertEqual(item["speakers"], ["Mira", "Ren"])
        self.assertEqual(item["multi_speaker_mode"], "chorus")
        self.assertEqual(item["confidence"], 0.95)

    def test_split_at_heading_selection_keeps_assignments_with_their_text(self):
        heading = "Chapter 2: Return"
        text = f"Opening line.\n{heading}\nMira said, Wait here.\nClosing line."
        opening = "Opening line."
        dialogue = "Wait here."
        chapter = Chapter(1, "Book", text, dialogue_assignments=[{
            "start": text.index(opening), "end": text.index(opening) + len(opening),
            "text": opening, "speaker": "Narrator",
        }, {
            "start": text.index(dialogue), "end": text.index(dialogue) + len(dialogue),
            "text": dialogue, "speaker": "Mira",
        }])

        editor = ChapterEditor([chapter])
        start = text.index(heading)
        editor.split_at_selection(0, start, start + len(heading), "Return")

        first, second = editor.chapters
        self.assertEqual(first.text, opening)
        self.assertIn(dialogue, second.text)
        self.assertEqual([item["text"] for item in first.dialogue_assignments], [opening])
        self.assertEqual([item["text"] for item in second.dialogue_assignments], [dialogue])
        item = second.dialogue_assignments[0]
        self.assertEqual(second.text[item["start"]:item["end"]], dialogue)

    def test_split_and_merge_assignment_offsets_survive_project_save_reload(self):
        text = "Opening paragraph.\n\nMira said, Wait here.\n\nClosing paragraph."
        opening = "Opening paragraph."
        dialogue = "Wait here."
        chapter = Chapter(1, "Full Book", text, dialogue_assignments=[
            {"start": text.index(opening), "end": text.index(opening) + len(opening),
             "text": opening, "speaker": "Narrator"},
            {"start": text.index(dialogue), "end": text.index(dialogue) + len(dialogue),
             "text": dialogue, "speaker": "Mira", "speakers": ["Mira", "Ren"],
             "multi_speaker_mode": "chorus", "confidence": 0.9},
        ])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "project"
            editor = ChapterEditor([chapter])
            editor.split(0, 1, "Dialogue")
            Project("Compatibility Book", folder, None, editor.chapters).save()
            reopened = Project.load(folder)
            self.assertEqual([item["text"] for item in reopened.chapters[0].dialogue_assignments], [opening])
            self.assertEqual([item["text"] for item in reopened.chapters[1].dialogue_assignments], [dialogue])
            right_item = reopened.chapters[1].dialogue_assignments[0]
            self.assertEqual(reopened.chapters[1].text[right_item["start"]:right_item["end"]], dialogue)
            self.assertEqual(right_item["speakers"], ["Mira", "Ren"])
            ChapterEditor(reopened.chapters).merge_with_next(0)
            Project("Compatibility Book", folder, None, reopened.chapters).save()
            merged = Project.load(folder).chapters[0]
            self.assertEqual({item["text"] for item in merged.dialogue_assignments}, {opening, dialogue})
            for item in merged.dialogue_assignments:
                self.assertEqual(merged.text[item["start"]:item["end"]], item["text"])
            merged_dialogue = next(item for item in merged.dialogue_assignments if item["text"] == dialogue)
            self.assertEqual(merged_dialogue["multi_speaker_mode"], "chorus")
            self.assertEqual(merged_dialogue["confidence"], 0.9)

    def test_text_edit_keeps_multi_speaker_fields_but_drops_stale_spans(self):
        old = "Mira said, Wait here."
        line = "Wait here."
        chapter = Chapter(1, "Scene", old, dialogue_assignments=[{
            "start": old.index(line), "end": old.index(line) + len(line),
            "text": line, "speaker": "Mira", "speakers": ["Mira", "Ren"],
            "multi_speaker_mode": "chorus", "confidence": 0.8,
        }])
        editor = ChapterEditor([chapter])
        editor.edit_text(0, "Mira said, Wait here. Ren replied, Go now.")

        item = editor.chapters[0].dialogue_assignments[0]
        self.assertEqual(editor.chapters[0].text[item["start"]:item["end"]], line)
        self.assertEqual(item["speakers"], ["Mira", "Ren"])
        self.assertEqual(item["multi_speaker_mode"], "chorus")
        self.assertEqual(item["confidence"], 0.8)



class PremiumV2BridgeSplitAssignmentIntegrityTests(unittest.TestCase):
    def _split(self, project, payload):
        bridge = object.__new__(PremiumV2Bridge)
        with (
            patch.object(PremiumV2Bridge, "_active_project", return_value=project),
            patch.object(PremiumV2Bridge, "_mark_project_edited") as mark_edited,
        ):
            result = bridge._chapter_split(payload)
        return result, mark_edited

    def test_bridge_split_moves_assignments_with_text_and_remaps_offsets(self):
        text = "Mira said, Wait here.\\n\\nRen answered, Go now."
        left_line = "Wait here."
        right_line = "Go now."
        left_assignment = {
            "start": text.index(left_line),
            "end": text.index(left_line) + len(left_line),
            "text": left_line,
            "speaker": "Mira",
            "source": "manual",
        }
        right_assignment = {
            "start": text.index(right_line),
            "end": text.index(right_line) + len(right_line),
            "text": right_line,
            "speaker": "Ren",
            "speakers": ["Ren", "Mira"],
            "multi_speaker_mode": "chorus",
            "confidence": 1.0,
            "source": "manual",
        }
        chapter = Chapter(1, "Scene", text, dialogue_assignments=[
            left_assignment, right_assignment,
        ])
        project = SimpleNamespace(chapters=[chapter], save=Mock())
        split_at = text.index("Ren answered")

        result, mark_edited = self._split(project, {
            "number": 1,
            "split_at": split_at,
            "text": text,
            "title": "Scene",
            "new_title": "Scene Continued",
        })

        self.assertEqual(len(project.chapters), 2)
        left, right = project.chapters
        self.assertEqual(left.text, "Mira said, Wait here.")
        self.assertEqual(right.text, "Ren answered, Go now.")
        self.assertEqual(left.dialogue_assignments, [left_assignment])
        self.assertEqual(len(right.dialogue_assignments), 1)
        moved = right.dialogue_assignments[0]
        self.assertEqual(right.text[moved["start"]:moved["end"]], right_line)
        self.assertEqual(moved["start"], right.text.index(right_line))
        self.assertEqual(moved["end"], moved["start"] + len(right_line))
        self.assertEqual(moved["speaker"], "Ren")
        self.assertEqual(moved["speakers"], ["Ren", "Mira"])
        self.assertEqual(moved["multi_speaker_mode"], "chorus")
        self.assertEqual(moved["confidence"], 1.0)
        self.assertEqual(result["new_number"], 2)
        project.save.assert_called_once_with()
        mark_edited.assert_called_once_with(project, 2)

    def test_bridge_split_rejects_assignment_crossing_split_boundary_without_mutating_project(self):
        text = "Mira said, Wait here.\\n\\nRen answered, Go now."
        start = text.index("Wait here.")
        end = text.index("Go now.") + len("Go now.")
        crossing = {
            "start": start,
            "end": end,
            "text": text[start:end],
            "speakers": ["Mira", "Ren"],
            "multi_speaker_mode": "chorus",
            "source": "manual",
        }
        chapter = Chapter(1, "Scene", text, dialogue_assignments=[crossing.copy()])
        project = SimpleNamespace(chapters=[chapter], save=Mock())
        original_text = chapter.text
        original_assignments = [item.copy() for item in chapter.dialogue_assignments]

        bridge = object.__new__(PremiumV2Bridge)
        with (
            patch.object(PremiumV2Bridge, "_active_project", return_value=project),
            patch.object(PremiumV2Bridge, "_mark_project_edited") as mark_edited,
            self.assertRaisesRegex(ValueError, "assignment.*crosses the split boundary"),
        ):
            bridge._chapter_split({
                "number": 1,
                "split_at": text.index("Ren answered"),
                "text": text,
                "title": "Scene",
                "new_title": "Scene Continued",
            })

        self.assertEqual(len(project.chapters), 1)
        self.assertEqual(project.chapters[0].text, original_text)
        self.assertEqual(project.chapters[0].dialogue_assignments, original_assignments)
        project.save.assert_not_called()
        mark_edited.assert_not_called()




if __name__ == "__main__":
    unittest.main()
