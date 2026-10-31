"""Behavioral tests for the saved-project Character Studio dialogue inspector."""

import unittest

from app.chapters.character_inspector import build_character_assignment_inspector
from app.chapters.detector import Chapter


def _record(chapter, text, speaker, source, offset=0):
    start = chapter.text.index(text, offset)
    return {
        "start": start,
        "end": start + len(text),
        "text": text,
        "speaker": speaker,
        "speakers": [speaker],
        "source": source,
    }


class CharacterAssignmentInspectorTests(unittest.TestCase):
    def test_mixed_ai_manual_aliases_and_distinct_chapter_statistics(self):
        first = Chapter(1, "Opening", "Mira greets us. Miri answers. Ren agrees.")
        second = Chapter(2, "Finale", "Mira returns. The others cheer.")
        first.dialogue_assignments = [
            _record(first, "Mira greets us.", "Mira", "manual"),
            _record(first, "Miri answers.", "Miri", "ai"),
            _record(first, "Ren agrees.", "Ren", "manual"),
        ]
        second.dialogue_assignments = [
            _record(second, "Mira returns.", "Mira", "ai"),
        ]

        page = build_character_assignment_inspector(
            [first, second],
            {"name": "Mira", "aliases": ["Miri"], "voice_profile": "Mira Voice"},
            "Test Story",
        )

        self.assertEqual(page["story_name"], "Test Story")
        self.assertEqual(page["stats"]["assigned_voice"], "Mira Voice")
        self.assertEqual(page["stats"]["dialogue_lines"], 3)
        self.assertEqual(page["stats"]["chapters"], 2)
        self.assertEqual(page["stats"]["ai_assigned_percent"], 2 / 3 * 100)
        self.assertEqual(page["stats"]["ai_assigned_lines"], 2)
        self.assertEqual(page["stats"]["manual_assigned_lines"], 1)
        self.assertEqual([row["source_class"] for row in page["rows"]], ["manual", "ai", "ai"])
        self.assertEqual([row["source_label"] for row in page["rows"]], [
            "Manual assignment", "AI-analyzed assignment", "AI-analyzed assignment"
        ])

    def test_pagination_returns_all_lines_in_stable_thirty_row_pages(self):
        lines = [f"Line {index:02d}." for index in range(37)]
        source = " ".join(lines)
        chapter = Chapter(1, "Long chapter", source)
        cursor = 0
        assignments = []
        for text in lines:
            start = source.index(text, cursor)
            assignments.append({
                "start": start, "end": start + len(text), "text": text,
                "speaker": "Mira", "source": "manual",
            })
            cursor = start + len(text)
        chapter.dialogue_assignments = assignments
        character = {"name": "Mira", "voice_profile": "Mira Voice"}

        first = build_character_assignment_inspector([chapter], character, "Novel", 0, 30)
        second = build_character_assignment_inspector([chapter], character, "Novel", 30, 30)

        self.assertEqual(first["total"], 37)
        self.assertEqual(len(first["rows"]), 30)
        self.assertTrue(first["has_more"])
        self.assertEqual(second["offset"], 30)
        self.assertEqual(len(second["rows"]), 7)
        self.assertFalse(second["has_more"])
        self.assertEqual(
            [row["id"] for row in first["rows"] + second["rows"]],
            [f"1:{item['start']}:{item['end']}" for item in assignments],
        )
        self.assertEqual(first["stats"]["dialogue_lines"], 37)

    def test_zero_assignments_has_zero_counts_and_no_division_error(self):
        chapter = Chapter(1, "Empty", "No saved speaker assignments.")
        page = build_character_assignment_inspector(
            [chapter], {"name": "Mira", "voice_profile": "Mira Voice"}, "Novel"
        )

        self.assertEqual(page["total"], 0)
        self.assertEqual(page["rows"], [])
        self.assertEqual(page["stats"]["dialogue_lines"], 0)
        self.assertEqual(page["stats"]["chapters"], 0)
        self.assertEqual(page["stats"]["ai_assigned_percent"], 0)

    def test_unknown_legacy_source_is_not_misreported_as_manual_or_ai(self):
        chapter = Chapter(1, "Legacy", "Old saved line. AI line.")
        chapter.dialogue_assignments = [
            _record(chapter, "Old saved line.", "Mira", ""),
            _record(chapter, "AI line.", "Mira", "ai"),
        ]

        page = build_character_assignment_inspector(
            [chapter], {"name": "Mira"}, "Novel"
        )

        self.assertEqual(page["stats"]["dialogue_lines"], 2)
        self.assertEqual(page["stats"]["ai_assigned_lines"], 1)
        self.assertEqual(page["stats"]["ai_assigned_percent"], 50)
        self.assertEqual(
            [row["source_class"] for row in page["rows"]],
            ["unknown", "ai"],
        )

    def test_stale_source_spans_are_excluded_from_live_inspector(self):
        chapter = Chapter(1, "Edited", "The chapter text has changed.")
        chapter.dialogue_assignments = [{
            "start": 0, "end": 12, "text": "Old source line",
            "speaker": "Mira", "source": "manual",
        }]

        page = build_character_assignment_inspector(
            [chapter], {"name": "Mira"}, "Novel"
        )

        self.assertEqual(page["total"], 0)
        self.assertEqual(page["stats"]["dialogue_lines"], 0)


class CharacterAssignmentFrontendSyntaxTests(unittest.TestCase):
    def test_backend_adapter_passes_node_syntax_check(self):
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable on this runner.")
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        result = subprocess.run(
            [node, "--check", str(adapter)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CharacterAssignmentBridgeProjectIsolationTests(unittest.TestCase):
    class BridgeHarness:
        def __init__(self, project):
            self.project = project

        def _active_project(self):
            return self.project

    def test_character_inspector_reads_only_the_current_projects_saved_dialogue(self):
        import tempfile
        from pathlib import Path

        from app.core.project import Project
        from app.core.state import save_state
        from app.ui.premium_v2_host import PremiumV2Bridge

        project_values = [
            ("Book One", "First book's saved line."),
            ("Book Two", "Second book's saved line."),
        ]
        observed = []
        for title, line in project_values:
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                chapter = Chapter(1, "Chapter 1", line, dialogue_assignments=[{
                    "start": 0,
                    "end": len(line),
                    "text": line,
                    "speaker": "Mira",
                    "source": "manual",
                }])
                project = Project(title, folder, chapters=[chapter])
                project.save()
                save_state(folder, {"characters": [{
                    "name": "Mira",
                    "aliases": ["Miri"],
                    "voice_profile": "Mira Voice",
                }]})
                bridge = self.BridgeHarness(project)

                inspector = PremiumV2Bridge._character_dialogue_list(
                    bridge, {"name": "Mira", "offset": 0, "limit": 30}
                )
                cast = PremiumV2Bridge._character_list(bridge, {})

                self.assertEqual(inspector["story_name"], title)
                self.assertEqual(inspector["total"], 1)
                self.assertEqual(inspector["rows"][0]["text"], line)
                self.assertEqual(cast[0]["story_name"], title)
                self.assertEqual(cast[0]["assigned_dialogue_count"], 1)
                self.assertEqual(cast[0]["assigned_chapter_count"], 1)
                observed.append(inspector["rows"][0]["text"])

        self.assertEqual(observed, [value[1] for value in project_values])


class CharacterAssignmentFrontendContractTests(unittest.TestCase):
    def test_preview_profile_is_not_persisted_until_character_save(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("selectedAssignedPreviewProfile=$('assignedPreviewProfile').value || null", adapter)
        self.assertNotIn(
            "editCharacterVoice').onchange=act(async()=>{if(!window.ryuPremiumSelectedCharacter)return;await call('character.assign'",
            adapter,
        )
        self.assertIn("previewSavedProfile(profile, dialogue.text, c.name)", adapter)
        self.assertIn("resetAssignedInspectorProjectContext()", adapter)




if __name__ == "__main__":
    unittest.main()
