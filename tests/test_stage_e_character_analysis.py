from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from app.chapters.detector import Chapter
from app.chapters.passage_index import load_or_build_passage_index


ROOT = Path(__file__).resolve().parents[1]


class StageECharacterAnalysisTests(unittest.TestCase):
    def test_passage_index_keeps_more_than_120_dialogue_passages_across_all_chapters(self):
        chapters = []
        for chapter_number in range(1, 4):
            text = "\n\n".join(
                f'“Dialogue passage {chapter_number}-{index:03d} contains complete source evidence.”'
                for index in range(1, 51)
            )
            chapters.append(Chapter(chapter_number, f"Coverage {chapter_number}", text))

        with tempfile.TemporaryDirectory() as temporary:
            index = load_or_build_passage_index(Path(temporary), chapters)

        dialogue_rows = [row for row in index["passages"] if row["dialogue"]]
        self.assertEqual(len(dialogue_rows), 150)
        self.assertEqual(index["counts"]["dialogue_passage_count"], 150)
        self.assertEqual({row["chapter_number"] for row in dialogue_rows}, {1, 2, 3})
        for row in dialogue_rows:
            source = chapters[row["chapter_number"] - 1].text
            self.assertEqual(source[row["start"]:row["end"]], row["text"])

    def test_character_worker_processes_every_dialogue_segment_without_a_fixed_slice(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        end = host.index("\n    def _character_assign(", start)
        worker = host[start:end]

        self.assertIn("segments = dialogue_segments(chapter)", worker)
        self.assertIn("for segment in segments:", worker)
        self.assertIn("suggestions.append({", worker)
        self.assertNotRegex(worker, re.compile(r"(?:segments|suggestions)\s*\[\s*:\s*\d+\s*\]"))

    def test_empty_ai_character_output_does_not_replace_source_grounded_detection(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        end = host.index("\n    def _character_assign(", start)
        worker = host[start:end]

        source_analysis = worker.index("analysis = analyze_book(project.chapters)")
        ai_call = worker.index("ai_report = brain.analyze_book(")
        ai_candidate_merge = worker.index("analysis.characters.append(candidate)")
        final_filter = worker.index("analysis.characters = [candidate for candidate in analysis.characters if credible_candidate(candidate)]")

        self.assertLess(source_analysis, ai_call)
        self.assertGreater(ai_candidate_merge, ai_call)
        self.assertGreater(final_filter, ai_candidate_merge)
        self.assertIn("analysis.characters", worker[ai_call:final_filter])

    def test_cancellation_is_checked_before_atomic_cast_and_dialogue_commit(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        end = host.index("\n    def _character_assign(", start)
        worker = host[start:end]

        lock_start = worker.index("with self._character_review_state_lock:")
        save_index = worker.index("save_state(project.folder, latest_state)", lock_start)
        cancel_index = worker.rfind("check_cancelled()", lock_start, save_index)
        committed_index = worker.index("analysis_committed = True", save_index)

        self.assertGreaterEqual(cancel_index, lock_start)
        self.assertLess(cancel_index, save_index)
        self.assertGreater(committed_index, save_index)
        self.assertIn('"partial_results_committed": False', worker)
        self.assertIn("No partial cast or dialogue index was committed.", worker)


if __name__ == "__main__":
    unittest.main()
