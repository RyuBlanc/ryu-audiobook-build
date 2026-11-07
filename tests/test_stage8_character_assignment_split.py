from pathlib import Path
import tempfile
import unittest

from app.chapters.detector import Chapter
from app.core.project import Project
from app.ui.premium_v2_host import PremiumV2Bridge


class CharacterAssignmentChapterSplitTests(unittest.TestCase):
    class BridgeHarness:
        def __init__(self, project):
            self.project = project
            self.marked = None

        def _active_project(self):
            return self.project

        def _mark_project_edited(self, project, chapter_number):
            self.marked = (project, chapter_number)

    def test_split_preserves_and_rebases_only_assignments_wholly_inside_each_side(self):
        source = 'Mira said, “Hello there.”\\n\\nRen replied, “Goodbye now.”'
        first_text = "Hello there."
        second_text = "Goodbye now."
        first_start = source.index(first_text)
        second_start = source.index(second_text)
        split_at = source.index("Ren replied")
        crossing_start = split_at - 2
        assignments = [
            {"start": first_start, "end": first_start + len(first_text),
             "text": first_text, "speaker": "Mira", "source": "manual"},
            {"start": second_start, "end": second_start + len(second_text),
             "text": second_text, "speaker": "Ren", "source": "ai"},
            {"start": crossing_start, "end": split_at + 5,
             "text": source[crossing_start:split_at + 5], "speaker": "Mira", "source": "manual"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapter = Chapter(1, "Chapter 1", source, dialogue_assignments=assignments)
            project = Project("Split Book", root, chapters=[chapter])
            project.save()
            bridge = self.BridgeHarness(project)

            result = PremiumV2Bridge._chapter_split(bridge, {
                "number": 1, "split_at": split_at, "text": source,
                "title": "Chapter 1", "new_title": "Chapter 2",
            })

            self.assertTrue(result["saved"])
            self.assertEqual(len(project.chapters), 2)
            left, right = project.chapters
            self.assertEqual(left.dialogue_assignments, [assignments[0]])
            expected_right = dict(assignments[1])
            expected_right["start"] -= split_at
            expected_right["end"] -= split_at
            self.assertEqual(right.dialogue_assignments, [expected_right])
            self.assertEqual(right.text, source[split_at:].lstrip())
            self.assertEqual(bridge.marked, (project, 2))

    def test_split_invalidates_old_offsets_when_editor_text_differs_from_saved_source(self):
        source = 'Mira said, “Hello there.”\\n\\nRen replied, “Goodbye now.”'
        assignment_text = "Hello there."
        start = source.index(assignment_text)
        assignments = [{
            "start": start, "end": start + len(assignment_text),
            "text": assignment_text, "speaker": "Mira", "source": "manual",
        }]
        edited = source.replace("Mira said", "Mira quietly said")
        split_at = edited.index("Ren replied")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = Project("Edited Split Book", root, chapters=[
                Chapter(1, "Chapter 1", source, dialogue_assignments=assignments)
            ])
            project.save()
            bridge = self.BridgeHarness(project)

            PremiumV2Bridge._chapter_split(bridge, {
                "number": 1, "split_at": split_at, "text": edited,
                "title": "Chapter 1", "new_title": "Chapter 2",
            })

            self.assertEqual(project.chapters[0].dialogue_assignments, [])
            self.assertEqual(project.chapters[1].dialogue_assignments, [])


if __name__ == "__main__":
    unittest.main()
