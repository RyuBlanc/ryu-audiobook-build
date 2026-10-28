"""Behavioral Stage 3 regressions for saved cast lifecycle and analysis persistence."""
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.characters import Character, CharacterAnalysis
from app.chapters.detector import Chapter
from app.core.state import load_state, save_state
from app.ui.premium_v2_host import PremiumV2Bridge


class Stage3CharacterLifecycleBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project_root = Path(self.temp_dir.name) / "project"
        self.project = SimpleNamespace(folder=self.project_root, title="Test Book", chapters=[])

        roots_patch = patch("app.ui.premium_v2_host.ensure_roots")
        durable_patch = patch.object(PremiumV2Bridge, "_load_durable_jobs")
        roots_patch.start()
        durable_patch.start()
        self.addCleanup(roots_patch.stop)
        self.addCleanup(durable_patch.stop)

        self.bridge = PremiumV2Bridge()
        self.bridge._active_project = Mock(return_value=self.project)
        self.bridge._find_profile = Mock(return_value=None)
        self.bridge._character_review_state_lock = threading.RLock()

    def save_project_state(self, state):
        save_state(self.project_root, state)
        return load_state(self.project_root)

    def test_case_insensitive_rename_keeps_saved_canonical_name_and_normalizes_aliases(self):
        self.save_project_state({
            "characters": [{
                "name": "Mira",
                "aliases": ["Captain Mira"],
                "role": "Lead",
                "short_description": "Saved description",
                "notes": "Saved note",
                "scope": "Current book only",
                "voice_profile": None,
            }]
        })

        result = self.bridge._character_update({
            "original_name": "mIRA",
            "name": "Mira Vale",
            "aliases": "Captain Mira, captain mira, MIRA VALE, Another",
        })

        saved = load_state(self.project_root)["characters"][0]
        self.assertTrue(result["saved"])
        self.assertEqual(saved["name"], "Mira Vale")
        self.assertEqual(saved["aliases"], ["Mira", "Captain Mira", "Another"])
        self.assertEqual(saved["role"], "Lead")
        self.assertEqual(saved["short_description"], "Saved description")
        self.assertEqual(saved["notes"], "Saved note")
        self.assertEqual(saved["voice_profile"], None)

    def test_case_insensitive_duplicate_name_is_rejected_without_persisting(self):
        before = self.save_project_state({
            "characters": [
                {"name": "Mira", "aliases": []},
                {"name": "Ren", "aliases": []},
            ]
        })
        before_bytes = (self.project_root / "state.json").read_bytes()

        with self.assertRaisesRegex(ValueError, "already uses that name"):
            self.bridge._character_update({
                "original_name": "mira",
                "name": "REN",
            })

        self.assertEqual(load_state(self.project_root), before)
        self.assertEqual((self.project_root / "state.json").read_bytes(), before_bytes)

    def test_delete_is_blocked_when_legacy_dialogue_assignment_uses_a_character_alias(self):
        state = {
            "characters": [{
                "name": "Mira Vale",
                "aliases": ["Mira"],
                "voice_profile": "Mira Voice",
            }, {"name": "Ren", "aliases": []}]
        }
        self.save_project_state(state)
        chapter = Chapter(
            1, "Chapter One", "Mira said, “Wait here.”",
            dialogue_assignments=[{
                "start": 11, "end": 23, "text": "“Wait here.”", "speaker": "Mira"
            }],
        )
        self.project.chapters = [chapter]

        with self.assertRaisesRegex(ValueError, "dialogue assignments still reference"):
            self.bridge._character_delete({"name": "Mira Vale"})

        self.assertEqual(load_state(self.project_root)["characters"], state["characters"])

    def test_delete_is_blocked_when_multi_speaker_assignment_references_character(self):
        state = {"characters": [{"name": "Mira", "aliases": []}, {"name": "Ren", "aliases": []}]}
        self.save_project_state(state)
        chapter = Chapter(
            1, "Chapter One", "“We should leave.”",
            dialogue_assignments=[{
                "start": 0, "end": 20, "text": "“We should leave.”",
                "speaker": "Ren", "speakers": ["Ren", "Mira"], "multi_speaker_mode": "chorus",
            }],
        )
        self.project.chapters = [chapter]

        with self.assertRaisesRegex(ValueError, "dialogue assignments still reference"):
            self.bridge._character_delete({"name": "Mira"})

        self.assertEqual(load_state(self.project_root)["characters"], state["characters"])

    def test_delete_unreferenced_character_removes_only_the_selected_cast_record(self):
        self.save_project_state({
            "characters": [{"name": "Mira", "aliases": []}, {"name": "Ren", "aliases": []}]
        })

        result = self.bridge._character_delete({"name": "mIrA"})

        self.assertTrue(result["deleted"])
        self.assertEqual(result["remaining"], 1)
        self.assertEqual([row["name"] for row in load_state(self.project_root)["characters"]], ["Ren"])

    def test_character_analysis_outputs_survive_state_reload(self):
        candidate = Character(
            name="Mira", role="Supporting Character", dialogue_count=3,
            examples=["Updated example one", "Updated example two"],
            confidence=0.91, aliases=["Mira Vale"],
        )
        analysis = CharacterAnalysis(
            narrator=Character("Narrator", "Audiobook Narrator"),
            characters=[candidate], dialogue_total=5, unassigned_dialogue=2,
        )
        self.save_project_state({
            "characters": [{
                "name": "Mira", "role": "Lead", "aliases": ["Captain Mira"],
                "voice_profile": "Mira Voice", "notes": "Keep this user note.",
                "dialogue_count": 1, "examples": ["Old example"], "confidence": 0.2,
            }]
        })
        self.project.chapters = [Chapter(1, "Chapter One", 'Mira said, “Hello there.”')]

        with (
            patch("app.ui.premium_v2_host.analyze_book", return_value=analysis),
            patch("app.ui.premium_v2_host.list_reusable_characters", return_value=[]),
            patch("app.chapters.characters._discover_explicit_speakers", return_value={"Mira"}),
            patch("app.chapters.character_learning.load_learning_examples", return_value=[]),
            patch("app.chapters.character_learning.prepare_learning_index", return_value=[]),
            patch("app.chapters.character_learning.rank_speaker_suggestions", return_value=[]),
            patch("app.chapters.dialogue.dialogue_segments", return_value=[]),
            patch.object(self.bridge, "_sync_saved_cast"),
            patch.object(self.bridge, "_job_update"),
            patch.object(self.bridge, "_now", return_value="2026-10-28T00:00:00Z"),
        ):
            self.bridge._character_worker("analysis-job", self.project)

        reloaded = load_state(self.project_root)
        saved_mira = next(row for row in reloaded["characters"] if row["name"] == "Mira")
        status = self.bridge._character_analysis_status({})

        self.assertEqual(saved_mira["dialogue_count"], 3)
        self.assertEqual(saved_mira["examples"], ["Updated example one", "Updated example two"])
        self.assertEqual(saved_mira["confidence"], 0.91)
        self.assertEqual(saved_mira["voice_profile"], "Mira Voice")
        self.assertEqual(saved_mira["notes"], "Keep this user note.")
        self.assertIn("Mira Vale", saved_mira["aliases"])
        self.assertTrue(status["analyzed"])
        self.assertEqual(status["dialogue_total"], 5)
        self.assertEqual(status["unassigned_dialogue"], 2)
        self.assertEqual(status["suggestion_count"], 0)


    def test_bridge_split_moves_dialogue_assignments_with_their_exact_text(self):
        text = 'Mira said, “Hello.”\n\nRen replied, “Goodbye.”'
        mira_text = '“Hello.”'
        ren_text = '“Goodbye.”'
        chapter = Chapter(1, "Combined", text, dialogue_assignments=[
            {"start": text.index(mira_text), "end": text.index(mira_text) + len(mira_text),
             "text": mira_text, "speaker": "Mira", "source": "manual"},
            {"start": text.index(ren_text), "end": text.index(ren_text) + len(ren_text),
             "text": ren_text, "speaker": "Ren", "source": "manual"},
        ])
        self.project.chapters = [chapter]
        self.project.save = Mock()
        self.bridge._mark_project_edited = Mock()

        self.bridge._chapter_split({
            "number": 1, "split_at": text.index("Ren replied"),
            "text": text, "title": "First", "new_title": "Second",
        })

        self.assertEqual(len(self.project.chapters), 2)
        first, second = self.project.chapters
        self.assertEqual([item["speaker"] for item in first.dialogue_assignments], ["Mira"])
        self.assertEqual([item["speaker"] for item in second.dialogue_assignments], ["Ren"])
        for result_chapter in self.project.chapters:
            for item in result_chapter.dialogue_assignments:
                self.assertEqual(
                    result_chapter.text[item["start"]:item["end"]],
                    item["text"],
                )
        self.project.save.assert_called_once()

    def test_bridge_merge_remaps_dialogue_assignments_after_whitespace_trim(self):
        left_text = '  Mira said, “Hello.”'
        right_text = '  Ren replied, “Goodbye.”'
        mira_text = '“Hello.”'
        ren_text = '“Goodbye.”'
        first = Chapter(1, "First", left_text, dialogue_assignments=[{
            "start": left_text.index(mira_text), "end": left_text.index(mira_text) + len(mira_text),
            "text": mira_text, "speaker": "Mira", "source": "manual",
        }])
        second = Chapter(2, "Second", right_text, dialogue_assignments=[{
            "start": right_text.index(ren_text), "end": right_text.index(ren_text) + len(ren_text),
            "text": ren_text, "speaker": "Ren", "source": "manual",
        }])
        self.project.chapters = [first, second]
        self.project.save = Mock()
        self.bridge._mark_project_edited = Mock()

        self.bridge._chapter_merge({"number": 2})

        self.assertEqual(len(self.project.chapters), 1)
        merged = self.project.chapters[0]
        self.assertEqual([item["speaker"] for item in merged.dialogue_assignments], ["Mira", "Ren"])
        for item in merged.dialogue_assignments:
            self.assertEqual(merged.text[item["start"]:item["end"]], item["text"])
        self.project.save.assert_called_once()



if __name__ == "__main__":
    unittest.main()
