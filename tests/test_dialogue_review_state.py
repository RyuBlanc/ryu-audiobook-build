from __future__ import annotations

from pathlib import Path
import unittest

from app.chapters.dialogue_review import retain_current_dialogue_skips


ROOT = Path(__file__).resolve().parents[1]


class DialogueReviewSkipPersistenceTests(unittest.TestCase):
    def test_reanalysis_preserves_skips_for_unchanged_source_passages(self):
        same = {
            "id": "dialogue-3-40-55",
            "chapter_number": 3,
            "start": 40,
            "end": 55,
            "source_text": "“Run!”",
        }
        changed_same_offsets = {
            "id": "dialogue-3-80-95",
            "chapter_number": 3,
            "start": 80,
            "end": 95,
            "source_text": "“Stay here!”",
        }
        previous = [same, changed_same_offsets, {
            "id": "dialogue-4-5-15",
            "chapter_number": 4,
            "start": 5,
            "end": 15,
            "source_text": "“Go now.”",
        }]
        current = [
            dict(same),
            {**changed_same_offsets, "source_text": "“Wait there!”"},
            {
                "id": "dialogue-3-120-135",
                "chapter_number": 3,
                "start": 120,
                "end": 135,
                "source_text": "“New passage.”",
            },
        ]

        actual = retain_current_dialogue_skips(
            ["dialogue-3-40-55", "dialogue-3-80-95", "dialogue-4-5-15", "dialogue-3-40-55"],
            previous,
            current,
        )

        self.assertEqual(actual, ["dialogue-3-40-55"])

    def test_skip_reconciliation_rejects_missing_malformed_and_ambiguous_records(self):
        duplicate_id = {"id":"dialogue-1-4-10", "chapter_number":1, "start":4, "end":10, "source_text":"“A.”"}
        conflicting_duplicate = {**duplicate_id, "source_text":"“B.”"}
        previous = [
            duplicate_id,
            conflicting_duplicate,
            {"id":"bad-offset", "chapter_number":1, "start":-1, "end":10, "source_text":"bad"},
            {"chapter_number":1, "start":4, "end":10, "source_text":"no id"},
        ]
        current = [duplicate_id, {"id":"dialogue-1-20-27", "chapter_number":1, "start":20, "end":27, "source_text":"“New.”"}]

        self.assertEqual(
            retain_current_dialogue_skips(
                ["dialogue-1-4-10", "bad-offset", "missing-id", "not-in-analysis"],
                previous,
                current,
            ),
            [],
        )

    def test_character_worker_reconciles_skips_instead_of_clearing_them(self):
        source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        worker_start = source.index("    def _character_worker(self, job_id: str, project) -> None:")
        worker_end = source.index("\n    def ", worker_start + 1)
        worker = source[worker_start:worker_end]
        self.assertIn("previous_dialogue_suggestions = state.get(\"character_dialogue_suggestions\") or []", worker)
        self.assertIn("previous_dialogue_skips = state.get(\"character_dialogue_skips\") or []", worker)
        self.assertIn("retain_current_dialogue_skips(", worker)
        self.assertNotIn('state["character_dialogue_skips"] = []', worker)


if __name__ == "__main__":
    unittest.main()
