"""Stage 3 Step 2: saved assignment origin and character-delete integrity."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.chapters.assignment_utils import assign_dialogue_to_chapters
from app.chapters.detector import Chapter
from app.ui import premium_v2_host as host


class AssignmentProvenanceUtilityTests(unittest.TestCase):
    def test_manual_assignment_remains_the_default_source(self):
        text = '“We should leave now.”'
        chapter = Chapter(1, "Arrival", text)
        result = assign_dialogue_to_chapters([chapter], text, ["Mira"], chapter_number=1)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(chapter.dialogue_assignments[0]["source"], "manual")
        self.assertEqual(chapter.dialogue_assignments[0]["confidence"], 1.0)

    def test_ai_assignment_source_and_confidence_survive_utility_persistence(self):
        text = '“The gate is closing.”'
        chapter = Chapter(1, "Gate", text)
        result = assign_dialogue_to_chapters([chapter], text, ["Mira"], chapter_number=1, source="ai", confidence=0.93)
        self.assertEqual(result["source"], "ai")
        self.assertEqual(chapter.dialogue_assignments[0]["source"], "ai")
        self.assertAlmostEqual(chapter.dialogue_assignments[0]["confidence"], 0.93)

    def test_unknown_assignment_source_is_rejected_without_mutation(self):
        text = '“Wait for me.”'
        chapter = Chapter(1, "Wait", text)
        with self.assertRaisesRegex(ValueError, "source must be manual or ai"):
            assign_dialogue_to_chapters([chapter], text, ["Mira"], chapter_number=1, source="guessed")
        self.assertEqual(chapter.dialogue_assignments, [])

    def test_ai_confidence_must_be_finite_and_between_zero_and_one(self):
        text = '“Wait for me.”'
        for confidence in (-0.1, 1.1, float("nan"), float("inf")):
            chapter = Chapter(1, "Wait", text)
            with self.subTest(confidence=confidence):
                with self.assertRaisesRegex(ValueError, "AI confidence"):
                    assign_dialogue_to_chapters([chapter], text, ["Mira"], chapter_number=1, source="ai", confidence=confidence)
            self.assertEqual(chapter.dialogue_assignments, [])


class _BridgeHarness:
    _chapter_dialogue_assign = host.PremiumV2Bridge._chapter_dialogue_assign
    _character_delete = host.PremiumV2Bridge._character_delete
    _project_series_name = host.PremiumV2Bridge._project_series_name

    def __init__(self, project):
        self.project = project

    def _active_project(self):
        return self.project

    def _now(self):
        return "2026-10-31T00:00:00+00:00"


class AssignmentProvenanceBridgeTests(unittest.TestCase):
    def _project(self, chapter):
        return SimpleNamespace(folder=Path("unused-stage3-step2-project"), title="Test Series", chapters=[chapter], save=Mock())

    def test_bridge_persists_ai_origin_for_exact_selected_source_span(self):
        text = 'Narration. “The gate is closing.”'
        chapter = Chapter(1, "Gate", text)
        start, end = text.index("“"), text.index("”") + 1
        state = {"series_name": "Test Series", "characters": [{"name": "Mira", "aliases": ["Mi"], "series": "Test Series"}]}
        project = self._project(chapter)
        bridge = _BridgeHarness(project)
        with patch.object(host, "load_state", side_effect=lambda _folder: state), patch.object(host, "save_state") as save_state, patch("app.chapters.character_learning.record_assignment_feedback"):
            result = bridge._chapter_dialogue_assign({
                "dialogue_text": text[start:end], "speakers": ["Mira"], "chapter_number": 1, "start": start, "end": end,
                "series": "Test Series", "mode": "single", "source": "ai", "confidence": 0.94,
            })
        self.assertTrue(result["saved"])
        self.assertEqual(result["source"], "ai")
        self.assertEqual(chapter.dialogue_assignments[0]["source"], "ai")
        self.assertAlmostEqual(chapter.dialogue_assignments[0]["confidence"], 0.94)
        project.save.assert_called_once()
        save_state.assert_called_once()

    def test_bridge_rejects_unknown_source_before_saving(self):
        text = '“The gate is closing.”'
        chapter = Chapter(1, "Gate", text)
        state = {"series_name": "Test Series", "characters": [{"name": "Mira", "series": "Test Series"}]}
        project = self._project(chapter)
        bridge = _BridgeHarness(project)
        with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state") as save_state:
            with self.assertRaisesRegex(ValueError, "source must be manual or ai"):
                bridge._chapter_dialogue_assign({
                    "dialogue_text": text, "speakers": ["Mira"], "chapter_number": 1, "start": 0, "end": len(text),
                    "series": "Test Series", "source": "guess",
                })
        self.assertEqual(chapter.dialogue_assignments, [])
        project.save.assert_not_called()
        save_state.assert_not_called()


class CharacterDeleteIntegrityTests(unittest.TestCase):
    def _bridge(self, chapter):
        project = SimpleNamespace(folder=Path("unused-stage3-step2-project"), chapters=[chapter])
        return _BridgeHarness(project)

    def test_character_with_saved_alias_assignment_cannot_be_deleted(self):
        chapter = Chapter(1, "Arrival", '“Hello.”')
        chapter.dialogue_assignments = [{
            "start": 0, "end": len(chapter.text), "text": chapter.text, "speakers": ["Mi"],
            "speaker": "Mi", "series": "Test Series", "source": "manual",
        }]
        state = {"series_name": "Test Series", "characters": [{"name": "Mira", "aliases": ["Mi"], "series": "Test Series"}]}
        bridge = self._bridge(chapter)
        with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state") as save_state:
            with self.assertRaisesRegex(ValueError, "saved dialogue assignments"):
                bridge._character_delete({"name": "Mira", "series": "Test Series"})
        self.assertEqual(len(state["characters"]), 1)
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        save_state.assert_not_called()

    def test_deleting_unassigned_character_in_one_series_keeps_other_series_identity(self):
        chapter = Chapter(1, "Arrival", '“Hello.”')
        chapter.dialogue_assignments = [{
            "start": 0, "end": len(chapter.text), "text": chapter.text, "speakers": ["Mira"],
            "speaker": "Mira", "series": "Other Series", "source": "manual",
        }]
        state = {"series_name": "Test Series", "characters": [
            {"name": "Mira", "aliases": [], "series": "Test Series"},
            {"name": "Mira", "aliases": [], "series": "Other Series"},
        ]}
        bridge = self._bridge(chapter)
        with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state"):
            result = bridge._character_delete({"name": "Mira", "series": "Test Series"})
        self.assertTrue(result["deleted"])
        self.assertEqual([row["series"] for row in state["characters"]], ["Other Series"])
        self.assertEqual(chapter.dialogue_assignments[0]["series"], "Other Series")

    def test_ambiguous_character_delete_requires_series(self):
        chapter = Chapter(1, "Arrival", "Narration.")
        state = {"series_name": "Test Series", "characters": [
            {"name": "Mira", "series": "Test Series"}, {"name": "Mira", "series": "Other Series"},
        ]}
        bridge = self._bridge(chapter)
        with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state") as save_state:
            with self.assertRaisesRegex(ValueError, "more than one series"):
                bridge._character_delete({"name": "Mira"})
        self.assertEqual(len(state["characters"]), 2)
        save_state.assert_not_called()


class FrontendAssignmentSourceContractTests(unittest.TestCase):
    def test_ai_and_manual_paths_send_distinct_saved_assignment_sources(self):
        source = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("source:assignmentSource", source)
        self.assertIn("selected.dataset.source === 'ai' ? 'ai' : 'manual'", source)
        self.assertIn("source:'ai', confidence:topConfidence", source)
        self.assertIn("data-confidence=", source)

    def test_project_character_delete_includes_series_identity(self):
        source = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("call('character.delete', {name, series:characterSeries(current)})", source)
