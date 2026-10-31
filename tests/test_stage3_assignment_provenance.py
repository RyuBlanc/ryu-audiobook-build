"""Stage 3 Step 2: saved assignment origin and character-delete integrity."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory

from app.core.project import Project
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

    def test_ai_assignment_source_and_confidence_survive_project_save_and_reopen(self):
        with TemporaryDirectory() as folder:
            text = '“The gate is closing.”'
            chapter = Chapter(1, "Gate", text, [{
                "start": 0, "end": len(text), "text": text,
                "speaker": "Mira", "speakers": ["Mira"], "series": "Test Series",
                "source": "ai", "confidence": 0.93,
            }])
            project = Project("Test Series", Path(folder), chapters=[chapter])
            project.save()
            reopened = Project.load(Path(folder))
            saved = reopened.chapters[0].dialogue_assignments[0]
            self.assertEqual(saved["source"], "ai")
            self.assertAlmostEqual(saved["confidence"], 0.93)
            self.assertEqual(saved["series"], "Test Series")

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
    _character_update = host.PremiumV2Bridge._character_update
    _character_create = host.PremiumV2Bridge._character_create
    _project_series_name = host.PremiumV2Bridge._project_series_name

    def __init__(self, project):
        self.project = project
        self.saved_library_rows = []

    def _active_project(self):
        return self.project

    def _now(self):
        return "2026-10-31T00:00:00+00:00"

    def _find_profile(self, _name):
        return None

    def _character_library_save(self, payload):
        self.saved_library_rows.append(dict(payload))
        return {"saved": True}


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

    def test_bridge_ai_source_is_preserved_when_offsets_are_resolved_by_backend(self):
        text = 'Narration. “The gate is closing.”'
        chapter = Chapter(1, "Gate", text)
        state = {"series_name": "Test Series", "characters": [{"name": "Mira", "series": "Test Series"}]}
        project = self._project(chapter)
        bridge = _BridgeHarness(project)
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch("app.chapters.character_learning.record_assignment_feedback"):
            result = bridge._chapter_dialogue_assign({
                "dialogue_text": "“The gate is closing.”", "speakers": ["Mira"],
                "chapter_number": 1, "series": "Test Series", "source": "ai", "confidence": 0.91,
            })
        self.assertTrue(result["saved"])
        self.assertEqual(result["source"], "ai")
        self.assertAlmostEqual(chapter.dialogue_assignments[0]["confidence"], 0.91)

    def test_assignment_writes_only_to_the_selected_active_project(self):
        text_a = '“Only Project A.”'
        text_b = '“Only Project B.”'
        chapter_a = Chapter(1, "A", text_a)
        chapter_b = Chapter(1, "B", text_b)
        project_a = self._project(chapter_a)
        project_b = self._project(chapter_b)
        project_a.folder = Path("project-a")
        project_b.folder = Path("project-b")
        state_by_folder = {
            "project-a": {"series_name": "Series A", "characters": [{"name": "Mira", "series": "Series A"}]},
            "project-b": {"series_name": "Series B", "characters": [{"name": "Mira", "series": "Series B"}]},
        }
        bridge_a, bridge_b = _BridgeHarness(project_a), _BridgeHarness(project_b)
        with patch.object(host, "load_state", side_effect=lambda folder: state_by_folder[str(folder)]), \
             patch.object(host, "save_state"), \
             patch("app.chapters.character_learning.record_assignment_feedback"):
            result_a = bridge_a._chapter_dialogue_assign({
                "dialogue_text": text_a, "speakers": ["Mira"], "chapter_number": 1,
                "series": "Series A", "source": "manual",
            })
            self.assertTrue(result_a["saved"])
            self.assertEqual(len(chapter_a.dialogue_assignments), 1)
            self.assertEqual(chapter_b.dialogue_assignments, [])
            result_b = bridge_b._chapter_dialogue_assign({
                "dialogue_text": text_b, "speakers": ["Mira"], "chapter_number": 1,
                "series": "Series B", "source": "manual",
            })
        self.assertTrue(result_b["saved"])
        self.assertEqual(chapter_a.dialogue_assignments[0]["text"], text_a)
        self.assertEqual(chapter_b.dialogue_assignments[0]["text"], text_b)
        self.assertEqual(chapter_a.dialogue_assignments[0]["series"], "Series A")
        self.assertEqual(chapter_b.dialogue_assignments[0]["series"], "Series B")
        self.assertEqual(chapter_a.dialogue_assignments[0]["source"], "manual")
        self.assertEqual(chapter_b.dialogue_assignments[0]["source"], "manual")

    def test_bridge_assignment_provenance_and_series_survive_project_reopen(self):
        with TemporaryDirectory() as root:
            project_a_folder = Path(root) / "project-a"
            project_b_folder = Path(root) / "project-b"
            project_a_folder.mkdir()
            project_b_folder.mkdir()
            manual_text = '“Only Project A manual.”'
            ai_text = '“Only Project A AI.”'
            other_text = '“Only Project B.”'
            project_a = Project(
                "Series A",
                project_a_folder,
                chapters=[Chapter(1, "A", manual_text + "\\n" + ai_text)],
            )
            project_b = Project(
                "Series B",
                project_b_folder,
                chapters=[Chapter(1, "B", other_text)],
            )
            project_a.save()
            project_b.save()
            states = {
                str(project_a_folder): {
                    "series_name": "Series A",
                    "characters": [{"name": "Mira", "series": "Series A"}],
                },
                str(project_b_folder): {
                    "series_name": "Series B",
                    "characters": [{"name": "Mira", "series": "Series B"}],
                },
            }
            bridge_a, bridge_b = _BridgeHarness(project_a), _BridgeHarness(project_b)
            with (
                patch.object(host, "load_state", side_effect=lambda folder: states[str(folder)]),
                patch.object(host, "save_state"),
                patch("app.chapters.character_learning.record_assignment_feedback"),
            ):
                manual_result = bridge_a._chapter_dialogue_assign({
                    "dialogue_text": manual_text, "speakers": ["Mira"],
                    "chapter_number": 1, "series": "Series A", "source": "manual",
                })
                ai_result = bridge_a._chapter_dialogue_assign({
                    "dialogue_text": ai_text, "speakers": ["Mira"],
                    "chapter_number": 1, "series": "Series A", "source": "ai", "confidence": 0.87,
                })
                other_result = bridge_b._chapter_dialogue_assign({
                    "dialogue_text": other_text, "speakers": ["Mira"],
                    "chapter_number": 1, "series": "Series B", "source": "manual",
                })
            self.assertTrue(manual_result["saved"])
            self.assertTrue(ai_result["saved"])
            self.assertTrue(other_result["saved"])
            reopened_a = Project.load(project_a_folder)
            reopened_b = Project.load(project_b_folder)
            assignments_a = reopened_a.chapters[0].dialogue_assignments
            assignments_b = reopened_b.chapters[0].dialogue_assignments
            self.assertEqual(len(assignments_a), 2)
            self.assertEqual(len(assignments_b), 1)
            by_text_a = {row["text"]: row for row in assignments_a}
            by_text_b = {row["text"]: row for row in assignments_b}
            self.assertEqual(by_text_a[manual_text]["series"], "Series A")
            self.assertEqual(by_text_a[manual_text]["source"], "manual")
            self.assertEqual(by_text_a[ai_text]["series"], "Series A")
            self.assertEqual(by_text_a[ai_text]["source"], "ai")
            self.assertAlmostEqual(by_text_a[ai_text]["confidence"], 0.87)
            self.assertEqual(by_text_b[other_text]["series"], "Series B")
            self.assertEqual(by_text_b[other_text]["source"], "manual")
            self.assertNotIn(other_text, by_text_a)
            self.assertNotIn(manual_text, by_text_b)

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


class CharacterUpdateSeriesIntegrityTests(unittest.TestCase):
    def _bridge(self):
        project = SimpleNamespace(folder=Path("unused-stage3-character-update-project"), chapters=[])
        return _BridgeHarness(project)

    def test_character_create_allows_same_canonical_name_in_a_different_series(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A", "aliases": ["A-Mira"]},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch.object(host, "list_reusable_characters", return_value=[]):
            result = bridge._character_create({
                "name": "Mira",
                "series": "Series B",
                "aliases": ["B-Mira"],
                "short": "Mira",
            })
        self.assertTrue(result["saved"])
        self.assertEqual([(row["name"], row["series"]) for row in state["characters"]], [
            ("Mira", "Series A"), ("Mira", "Series B")
        ])
        self.assertEqual(bridge.saved_library_rows[-1]["series"], "Series B")

    def test_character_create_updates_existing_character_only_within_same_series(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A", "aliases": ["A-Mira"], "role": "Lead"},
                {"name": "Mira", "series": "Series B", "aliases": ["B-Mira"], "role": "Rival"},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch.object(host, "list_reusable_characters", return_value=[]):
            result = bridge._character_create({
                "name": "Mira",
                "series": "Series B",
                "aliases": ["Night Runner"],
                "short": "Mira",
            })
        self.assertTrue(result["saved"])
        self.assertEqual(len(state["characters"]), 2)
        self.assertEqual(state["characters"][0]["aliases"], ["A-Mira"])
        self.assertEqual(state["characters"][1]["aliases"], ["Night Runner"])
        self.assertEqual(state["characters"][1]["role"], "Rival")

    def test_character_update_targets_the_selected_series_when_names_are_duplicated(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A", "role": "Lead", "aliases": ["A-Mira"]},
                {"name": "Mira", "series": "Series B", "role": "Rival", "aliases": ["B-Mira"]},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch.object(host, "list_reusable_characters", return_value=[]):
            result = bridge._character_update({
                "original_name": "Mira",
                "original_series": "Series B",
                "name": "Mira Vale",
                "series": "Series B",
                "aliases": "B-Mira, Night Runner",
                "role": "Rival",
            })
        self.assertTrue(result["saved"])
        self.assertEqual(state["characters"][0]["name"], "Mira")
        self.assertEqual(state["characters"][0]["series"], "Series A")
        self.assertEqual(state["characters"][1]["name"], "Mira Vale")
        self.assertEqual(state["characters"][1]["series"], "Series B")
        self.assertIn("Mira", state["characters"][1]["aliases"])
        self.assertEqual(bridge.saved_library_rows[0]["series"], "Series B")

    def test_character_update_without_series_rejects_ambiguous_duplicate_name(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A"},
                {"name": "Mira", "series": "Series B"},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state") as save_state:
            with self.assertRaisesRegex(ValueError, "more than one series"):
                bridge._character_update({
                    "original_name": "Mira",
                    "name": "Mira Vale",
                    "series": "Series A",
                })
        self.assertEqual([row["name"] for row in state["characters"]], ["Mira", "Mira"])
        save_state.assert_not_called()

    def test_same_character_name_is_allowed_in_a_different_target_series(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A"},
                {"name": "Mira", "series": "Series B"},
                {"name": "Ren", "series": "Series A"},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch.object(host, "list_reusable_characters", return_value=[]):
            result = bridge._character_update({
                "original_name": "Ren",
                "original_series": "Series A",
                "name": "Mira",
                "series": "Series C",
            })
        self.assertTrue(result["saved"])
        self.assertEqual([row["name"] for row in state["characters"]], ["Mira", "Mira", "Mira"])
        self.assertEqual([row["series"] for row in state["characters"]], ["Series A", "Series B", "Series C"])


    def test_character_update_rejects_name_collision_within_target_series(self):
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A"},
                {"name": "Ren", "series": "Series A"},
                {"name": "Mira", "series": "Series B"},
            ],
        }
        bridge = self._bridge()
        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state") as save_state:
            with self.assertRaisesRegex(ValueError, "already uses that name in the selected series"):
                bridge._character_update({
                    "original_name": "Ren",
                    "original_series": "Series A",
                    "name": "Mira",
                    "series": "Series A",
                })
        self.assertEqual([row["name"] for row in state["characters"]], ["Mira", "Ren", "Mira"])
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
