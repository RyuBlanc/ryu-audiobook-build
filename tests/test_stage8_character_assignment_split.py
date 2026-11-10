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


class CharacterAssignmentDeleteTests(unittest.TestCase):
    class BridgeHarness:
        def __init__(self, project):
            self.project = project

        def _active_project(self):
            return self.project

        def _project_series_name(self, project, state):
            return project.title

        def _now(self):
            return "2026-11-07T12:00:00+00:00"

    def test_delete_refuses_to_orphan_saved_single_or_multi_speaker_assignments(self):
        from app.core.state import load_state, save_state

        source = "Mira speaks. Both characters answer."
        assignments = [
            {"start":0,"end":12,"text":"Mira speaks","speaker":"Mira","source":"manual"},
            {"start":13,"end":source.index(" answer"),"text":"Both characters","speaker":"Mira",
             "speakers":["Mira","Ren"],"multi_speaker_mode":"chorus","source":"ai"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = Project("Delete Cast Book", root, chapters=[
                Chapter(1,"Chapter 1",source,dialogue_assignments=assignments)
            ])
            project.save()
            original_state = {
                "characters":[
                    {"name":"Mira","aliases":["Miri"],"voice_profile":"Voice A"},
                    {"name":"Ren","aliases":["Ren Two"],"voice_profile":"Voice B"},
                ],
                "voice_cast":{"Mira":"Voice A","Ren":"Voice B"},
            }
            save_state(root,original_state)
            bridge = self.BridgeHarness(project)

            with self.assertRaisesRegex(ValueError,"Cannot delete.*saved dialogue assignments"):
                PremiumV2Bridge._character_delete(bridge,{"name":"Mira"})

            self.assertEqual(project.chapters[0].dialogue_assignments,assignments)
            saved = load_state(root)
            self.assertEqual(saved["characters"],original_state["characters"])
            self.assertEqual(saved["voice_cast"],original_state["voice_cast"])

    def test_delete_succeeds_after_character_has_no_saved_dialogue_references(self):
        from app.core.state import load_state, save_state

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = Project("Delete Cast Book",root,chapters=[
                Chapter(1,"Chapter 1","Narration only.",dialogue_assignments=[])
            ])
            project.save()
            save_state(root,{"characters":[{"name":"Mira"},{"name":"Ren"}]})
            bridge = self.BridgeHarness(project)

            result = PremiumV2Bridge._character_delete(bridge,{"name":"Mira"})

            self.assertTrue(result["deleted"])
            self.assertEqual([row["name"] for row in load_state(root)["characters"]],["Ren"])

    def test_delete_rejects_unknown_character_without_mutating_project(self):
        from app.core.state import load_state, save_state

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = Project("Delete Cast Book",root,chapters=[
                Chapter(1,"Chapter 1","Mira speaks.",dialogue_assignments=[
                    {"start":0,"end":12,"text":"Mira speaks","speaker":"Mira"}
                ])
            ])
            project.save()
            save_state(root,{"characters":[{"name":"Mira"}]})
            bridge = self.BridgeHarness(project)

            with self.assertRaisesRegex(ValueError,"no longer in the saved cast for that series"):
                PremiumV2Bridge._character_delete(bridge,{"name":"Missing"})
            self.assertEqual(len(project.chapters[0].dialogue_assignments),1)
            self.assertEqual(load_state(root)["characters"],[{"name":"Mira"}])


if __name__ == "__main__":
    unittest.main()
