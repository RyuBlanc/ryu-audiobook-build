"""Behavioral Stage 3 regression tests for character state and chapter offsets."""

import tempfile
import unittest
from pathlib import Path

from app.chapters.detector import Chapter
from app.core.project import Project
from app.core.state import load_state, save_state
from app.ui.premium_v2_host import PremiumV2Bridge


class _BridgeHarness:
    def __init__(self, project):
        self.project = project
        self.job_updates = []

    def _active_project(self):
        return self.project

    def _find_profile(self, name):
        return {"name": name} if name in {"Mira Voice", "Ren Voice"} else None

    def _now(self):
        return "2026-10-28T00:00:00Z"

    def _job_update(self, *args, **kwargs):
        self.job_updates.append((args, kwargs))


class Stage3CharacterMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.project = Project("Stage 3 test book", self.folder, chapters=[
            Chapter(1, "Chapter 1", "Mira said, “Wait here.” Ren answered, “I will.”")
        ])
        self.project.save()
        self.bridge = _BridgeHarness(self.project)

    def test_case_insensitive_update_preserves_omitted_fields_and_deduplicates_aliases(self):
        save_state(self.folder, {
            "characters": [{
                "name": "Mira", "role": "Lead", "short_description": "Saved description",
                "notes": "Saved notes", "scope": "Series-wide",
                "voice_profile": "Mira Voice", "aliases": ["Captain Mira"],
            }]
        })

        result = PremiumV2Bridge._character_update(self.bridge, {
            "original_name": "mIrA", "name": "Mira",
            "aliases": ["Captain Mira", "Captain Mira", "Mira Vale"],
        })

        saved = load_state(self.folder)["characters"][0]
        self.assertTrue(result["saved"])
        self.assertEqual(saved["role"], "Lead")
        self.assertEqual(saved["short_description"], "Saved description")
        self.assertEqual(saved["notes"], "Saved notes")
        self.assertEqual(saved["scope"], "Series-wide")
        self.assertEqual(saved["voice_profile"], "Mira Voice")
        self.assertEqual(saved["aliases"], ["Captain Mira", "Mira Vale"])

    def test_rename_rejects_case_insensitive_duplicate_without_mutating_state(self):
        original = {
            "characters": [{"name": "Mira", "aliases": []}, {"name": "Ren", "aliases": []}]
        }
        save_state(self.folder, original)

        with self.assertRaisesRegex(ValueError, "already uses that name"):
            PremiumV2Bridge._character_update(self.bridge, {
                "original_name": "Ren", "name": "mIRA"
            })

        self.assertEqual(load_state(self.folder)["characters"], original["characters"])

    def test_delete_removes_stale_references_but_preserves_other_multi_speakers(self):
        text = self.project.chapters[0].text
        first_start = text.index("Wait here.")
        second_start = text.index("I will.")
        self.project.chapters[0].dialogue_assignments = [
            {"start": first_start, "end": first_start + len("Wait here."),
             "text": "Wait here.", "speaker": "Mira", "speakers": ["Mira", "Ren"],
             "multi_speaker_mode": "chorus", "source": "manual"},
            {"start": second_start, "end": second_start + len("I will."),
             "text": "I will.", "speaker": "Mira", "speakers": ["Mira"], "source": "manual"},
        ]
        self.project.save()
        save_state(self.folder, {
            "characters": [
                {"name": "Mira", "aliases": ["Mira Vale"]},
                {"name": "Ren", "aliases": []},
            ],
            "voice_cast": {"Mira": "Mira Voice", "Mira Vale": "Mira Voice", "Ren": "Ren Voice"},
        })

        result = PremiumV2Bridge._character_delete(self.bridge, {"name": "mira"})

        state = load_state(self.folder)
        reloaded = Project.load(self.folder)
        self.assertTrue(result["deleted"])
        self.assertEqual([row["name"] for row in state["characters"]], ["Ren"])
        self.assertEqual(state["voice_cast"], {"Ren": "Ren Voice"})
        assignments = reloaded.chapters[0].dialogue_assignments
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["speakers"], ["Ren"])
        self.assertEqual(assignments[0]["speaker"], "Ren")
        self.assertEqual(assignments[0]["text"], "Wait here.")

    def test_delete_missing_character_fails_without_mutation(self):
        save_state(self.folder, {"characters": [{"name": "Mira"}]})
        before = load_state(self.folder)

        with self.assertRaisesRegex(ValueError, "no longer in the saved cast"):
            PremiumV2Bridge._character_delete(self.bridge, {"name": "Missing"})

        self.assertEqual(load_state(self.folder), before)


class Stage3CharacterAnalysisPersistenceTests(unittest.TestCase):
    def test_analysis_evidence_and_user_metadata_survive_save_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            chapters = [Chapter(
                1, "One",
                '“Are you ready?” Mira asked.\n“Ready,” Ren replied.'
            )]
            project = Project("Analysis persistence", folder, chapters=chapters)
            project.save()
            save_state(folder, {
                "characters": [{
                    "name": "Mira", "aliases": ["Captain Mira"],
                    "voice_profile": "Mira Voice", "short_description": "User description",
                    "notes": "Do not lose this note", "scope": "Series-wide",
                    "chapter_appearances": [1], "dialogue_count": 1,
                    "examples": ["Old example"], "confidence": 0.2,
                }]
            })
            bridge = _BridgeHarness(project)

            PremiumV2Bridge._character_worker(bridge, "analysis-job", project)

            reloaded = load_state(folder)
            by_name = {item["name"].casefold(): item for item in reloaded["characters"]}
            mira = by_name["mira"]
            self.assertEqual(reloaded["character_analysis"]["dialogue_total"], 2)
            self.assertGreaterEqual(mira["dialogue_count"], 1)
            self.assertTrue(mira["examples"])
            self.assertGreaterEqual(mira["confidence"], 0.2)
            self.assertEqual(mira["aliases"], ["Captain Mira"])
            self.assertEqual(mira["voice_profile"], "Mira Voice")
            self.assertEqual(mira["short_description"], "User description")
            self.assertEqual(mira["notes"], "Do not lose this note")
            self.assertEqual(mira["scope"], "Series-wide")
            self.assertEqual(bridge.job_updates[-1][1]["state"], "completed")


    def test_unassigned_dialogue_count_survives_analysis_save_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = Project("Unassigned dialogue", folder, chapters=[
                Chapter(1, "One", "“Nobody answered.”")
            ])
            project.save()
            bridge = _BridgeHarness(project)

            PremiumV2Bridge._character_worker(bridge, "unassigned-job", project)

            saved = load_state(folder)["character_analysis"]
            self.assertEqual(saved["dialogue_total"], 1)
            self.assertEqual(saved["unassigned_dialogue"], 1)
            self.assertEqual(bridge.job_updates[-1][1]["state"], "completed")


class Stage3ChapterAssignmentOffsetTests(unittest.TestCase):
    def _project(self, folder, text, assignments):
        chapter = Chapter(1, "One", text, dialogue_assignments=assignments)
        project = Project("Offset test", Path(folder), chapters=[chapter])
        project.save()
        return project

    def test_split_moves_right_side_offsets_and_invalidates_boundary_spans(self):
        with tempfile.TemporaryDirectory() as temp:
            text = "Opening line.\n\nMira said, “Wait here.”\n\nClosing line."
            split_at = text.index("Mira said")
            quote_start = text.index("Wait here.")
            assignments = [
                {"start": 0, "end": len("Opening line."), "text": "Opening line.", "speaker": "Ren"},
                {"start": quote_start, "end": quote_start + len("Wait here."),
                 "text": "Wait here.", "speaker": "Mira"},
                {"start": split_at - 1, "end": split_at + 3, "text": "boundary", "speaker": "Ghost"},
            ]
            project = self._project(temp, text, assignments)
            bridge = _BridgeHarness(project)

            result = PremiumV2Bridge._chapter_split(bridge, {
                "number": 1, "split_at": split_at, "text": text
            })

            reloaded = Project.load(Path(temp))
            self.assertTrue(result["saved"])
            self.assertEqual(len(reloaded.chapters), 2)
            left, right = reloaded.chapters
            self.assertEqual(len(left.dialogue_assignments), 1)
            self.assertEqual(left.text[left.dialogue_assignments[0]["start"]:left.dialogue_assignments[0]["end"]],
                             left.dialogue_assignments[0]["text"])
            self.assertEqual(len(right.dialogue_assignments), 1)
            moved = right.dialogue_assignments[0]
            self.assertEqual(right.text[moved["start"]:moved["end"]], moved["text"])
            self.assertEqual(moved["text"], "Wait here.")

    def test_reorder_keeps_assignments_attached_to_their_chapter(self):
        with tempfile.TemporaryDirectory() as temp:
            first_text = "Mira says, “Wait here.”"
            second_text = "Ren says, “Come along.”"
            project = Project("Reorder test", Path(temp), chapters=[
                Chapter(1, "First", first_text, dialogue_assignments=[{
                    "start": first_text.index("Wait here."),
                    "end": first_text.index("Wait here.") + len("Wait here."),
                    "text": "Wait here.", "speaker": "Mira",
                }]),
                Chapter(2, "Second", second_text, dialogue_assignments=[{
                    "start": second_text.index("Come along."),
                    "end": second_text.index("Come along.") + len("Come along."),
                    "text": "Come along.", "speaker": "Ren",
                }]),
            ])
            project.save()
            bridge = _BridgeHarness(project)

            PremiumV2Bridge._chapter_reorder(bridge, {"number": 1, "new_number": 2})

            reloaded = Project.load(Path(temp))
            self.assertEqual(reloaded.chapters[0].title, "Second")
            self.assertEqual(reloaded.chapters[1].title, "First")
            for chapter in reloaded.chapters:
                assignment = chapter.dialogue_assignments[0]
                self.assertEqual(
                    chapter.text[assignment["start"]:assignment["end"]],
                    assignment["text"],
                )

    def test_merge_shifts_assignments_into_the_combined_source_text(self):
        with tempfile.TemporaryDirectory() as temp:
            first_text = "Opening line."
            second_text = "Mira said, “Wait here.”"
            start = second_text.index("Wait here.")
            project = Project("Merge test", Path(temp), chapters=[
                Chapter(1, "First", first_text),
                Chapter(2, "Second", second_text, dialogue_assignments=[{
                    "start": start, "end": start + len("Wait here."),
                    "text": "Wait here.", "speaker": "Mira",
                }]),
            ])
            project.save()
            bridge = _BridgeHarness(project)

            PremiumV2Bridge._chapter_merge(bridge, {"number": 2})

            reloaded = Project.load(Path(temp))
            self.assertEqual(len(reloaded.chapters), 1)
            merged = reloaded.chapters[0]
            assignment = merged.dialogue_assignments[0]
            self.assertEqual(
                merged.text[assignment["start"]:assignment["end"]],
                assignment["text"],
            )
            self.assertEqual(assignment["text"], "Wait here.")

    def test_split_invalidates_offsets_when_editor_text_differs_from_saved_source(self):
        with tempfile.TemporaryDirectory() as temp:
            text = "Opening line.\n\nClosing line."
            project = self._project(temp, text, [
                {"start": 0, "end": len("Opening line."), "text": "Opening line.", "speaker": "Mira"}
            ])
            bridge = _BridgeHarness(project)

            changed_text = "Changed opening.\n\nClosing line."
            PremiumV2Bridge._chapter_split(bridge, {
                "number": 1, "split_at": changed_text.index("Closing"),
                "text": changed_text
            })

            reloaded = Project.load(Path(temp))
            self.assertEqual(reloaded.chapters[0].dialogue_assignments, [])
            self.assertEqual(reloaded.chapters[1].dialogue_assignments, [])


class Stage3CharacterDetectionCoverageTests(unittest.TestCase):
    def test_first_person_self_identification_is_saved_as_narrating_character(self):
        from app.chapters.characters import analyze_book

        result = analyze_book([Chapter(1, "One", "My name is Rimuru Tempest. I walked home.")])
        rimuru = next(item for item in result.characters if item.name.casefold() == "rimuru tempest")
        self.assertEqual(rimuru.role, "Narrating Character")

    def test_short_name_alias_routes_to_canonical_character(self):
        from app.chapters.characters import analyze_book

        result = analyze_book([Chapter(
            1, "One",
            'Rimuru Tempest said, “Stay here.” Rimuru replied, “I will.”'
        )])
        rimuru = next(item for item in result.characters if item.name.casefold() == "rimuru tempest")
        self.assertGreaterEqual(rimuru.dialogue_count, 2)

    def test_attributed_dialogue_discovers_each_speaker(self):
        from app.chapters.characters import analyze_book

        result = analyze_book([Chapter(
            1, "One", '“Wait!” Rias shouted.\n“Understood,” Issei replied.'
        )])
        names = {item.name.casefold() for item in result.characters}
        self.assertIn("rias", names)
        self.assertIn("issei", names)
        self.assertEqual(result.dialogue_total, 2)


if __name__ == "__main__":
    unittest.main()
