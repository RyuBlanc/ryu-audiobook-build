"""Stage 5.3 PROD-14 terminal project/job/history consistency matrix."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.state import load_state, save_state
from app.ui import premium_v2_host as host


class DurableGenerationCompletionHarness:
    """Exercise actual generation completion, queue and History persistence methods."""

    _generation_finished = host.PremiumV2Bridge._generation_finished
    _job_update = host.PremiumV2Bridge._job_update
    _job_list = host.PremiumV2Bridge._job_list
    _history_list = host.PremiumV2Bridge._history_list
    _persist_json_rows = host.PremiumV2Bridge._persist_json_rows
    _persist_jobs = host.PremiumV2Bridge._persist_jobs
    _persist_history = host.PremiumV2Bridge._persist_history
    _record_history_job = host.PremiumV2Bridge._record_history_job
    _terminal_job_state = staticmethod(host.PremiumV2Bridge._terminal_job_state)
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, root: Path, job_id: str, result: dict | None = None) -> None:
        self._jobs_lock = threading.RLock()
        self._jobs = {
            job_id: {
                "job_id": job_id,
                "id": job_id,
                "type": "audiobook-generation",
                "project_title": "Terminal State Book",
                "project_folder": str(root / "project"),
                "state": "running",
                "progress": 64,
                "output_path": None,
                "result": dict(result or {}),
            }
        }
        self._history: dict[str, dict] = {}
        self._generators = {job_id: object()}
        self._generation_progress_timing = {}
        self._jobs_path = lambda: root / "premium_v2_jobs.json"
        self._history_path = lambda: root / "premium_v2_history.json"


class Stage53TerminalJobConsistencyTests(unittest.TestCase):
    def _summary(self, *, cancelled=False, failed=False, output=None):
        return SimpleNamespace(
            output_path=output,
            cancelled=cancelled,
            packaging_failed=False,
            chapters_failed=[1] if failed else [],
            chapters_completed=0 if failed or cancelled else 1,
            chapters_total=1,
            chapters_completed_numbers=[] if failed or cancelled else [1],
            failure_details={1: "Deterministic TTS failure"} if failed else {},
            packaging_error=None,
        )

    def test_completed_failed_and_cancelled_results_share_one_terminal_job_identity(self) -> None:
        scenarios = (
            ("completed", False, False, True, "Saved Narrator", True, "narrator_only", True, 1),
            ("failed", False, True, True, "Saved Narrator", False, "character_cast", False, 3),
            ("cancelled", True, False, True, "Saved Narrator", False, "narrator_only", True, 1),
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for (expected_status, cancelled, failed, old_output_exists, narrator, attach_output,
                 generation_mode, narrator_only, character_profile_count) in scenarios:
                with self.subTest(status=expected_status):
                    case_root = root / expected_status
                    case_root.mkdir()
                    project_folder = case_root / "project"
                    project_folder.mkdir()
                    job_id = f"terminal-{expected_status}-job"
                    output = case_root / "Terminal State Book.m4b"
                    if old_output_exists:
                        output.write_bytes(b"prior-or-current-output" * 128)

                    save_state(
                        project_folder,
                        {
                            "status": "generating",
                            "generation_job_id": job_id,
                            "generation_target_path": str(output),
                            "output_path": None,
                            "completed_chapters": [],
                            "generation_mode": generation_mode,
                            "narrator_only_generation": narrator_only,
                            "character_voice_profile_count": character_profile_count,
                        },
                    )
                    project = SimpleNamespace(folder=project_folder)
                    bridge = DurableGenerationCompletionHarness(
                        case_root, job_id,
                        result={
                            "generation_mode": generation_mode,
                            "narrator_only": narrator_only,
                            "character_voice_profile_count": character_profile_count,
                        },
                    )
                    summary = self._summary(
                        cancelled=cancelled,
                        failed=failed,
                        output=output,
                    )

                    bridge._generation_finished(job_id, project, summary, output, narrator)

                    project_state = load_state(project_folder)
                    queue_row = next(
                        row for row in bridge._job_list({"include_hidden": False})
                        if row["job_id"] == job_id
                    )
                    history_row = next(
                        row for row in bridge._history_list({})
                        if row["job_id"] == job_id
                    )
                    expected_output = str(output) if attach_output else None

                    self.assertEqual(project_state["status"], expected_status)
                    self.assertEqual(project_state["generation_job_id"], job_id)
                    self.assertEqual(queue_row["state"], expected_status)
                    self.assertEqual(history_row["state"], expected_status)
                    self.assertEqual(queue_row["job_id"], history_row["job_id"])
                    self.assertEqual(queue_row["output_path"], expected_output)
                    self.assertEqual(history_row["output_path"], expected_output)
                    for terminal_row in (queue_row, history_row):
                        self.assertEqual(terminal_row["result"]["generation_mode"], generation_mode)
                        self.assertIs(terminal_row["result"]["narrator_only"], narrator_only)
                        self.assertEqual(
                            terminal_row["result"]["character_voice_profile_count"],
                            character_profile_count,
                        )
                    self.assertEqual(queue_row["output_path"], expected_output)
                    self.assertNotIn(job_id, bridge._generators)

                    saved_jobs = json.loads(
                        (case_root / "premium_v2_jobs.json").read_text(encoding="utf-8")
                    )
                    saved_history = json.loads(
                        (case_root / "premium_v2_history.json").read_text(encoding="utf-8")
                    )
                    saved_job = next(row for row in saved_jobs if row["job_id"] == job_id)
                    saved_record = next(row for row in saved_history if row["job_id"] == job_id)
                    self.assertEqual(saved_job["state"], expected_status)
                    self.assertEqual(saved_record["state"], expected_status)
                    self.assertEqual(saved_job["job_id"], saved_record["job_id"])
                    self.assertEqual(saved_job["output_path"], expected_output)
                    self.assertEqual(saved_record["output_path"], expected_output)
                    self.assertEqual(saved_job["result"]["generation_mode"], generation_mode)
                    self.assertEqual(saved_record["result"]["generation_mode"], generation_mode)
                    self.assertIs(saved_record["result"]["narrator_only"], narrator_only)
                    self.assertEqual(
                        saved_record["result"]["character_voice_profile_count"],
                        character_profile_count,
                    )


    def test_complete_chapter_count_without_worker_output_does_not_publish_stale_m4b(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            job_id = "missing-output-generation-job"
            output = root / "previously-finished-book.m4b"
            output.write_bytes(b"previously completed audiobook" * 128)
            save_state(
                project_folder,
                {
                    "status": "generating",
                    "generation_job_id": job_id,
                    "generation_target_path": str(output),
                    "output_path": None,
                    "completed_chapters": [],
                    "generation_mode": "narrator_only",
                    "narrator_only_generation": True,
                    "character_voice_profile_count": 0,
                },
            )
            bridge = DurableGenerationCompletionHarness(
                root, job_id,
                result={
                    "generation_mode": "narrator_only",
                    "narrator_only": True,
                    "character_voice_profile_count": 0,
                },
            )
            # This worker reports every chapter complete, but returns no output.
            # An older, non-empty M4B at the target path must not satisfy this job.
            summary = self._summary(output=None)
            bridge._generation_finished(
                job_id, SimpleNamespace(folder=project_folder), summary, output, "Saved Narrator",
            )

            queue_row = bridge._job_list({"include_hidden": False})[0]
            history_row = bridge._history_list({})[0]
            project_state = load_state(project_folder)
            self.assertEqual(queue_row["state"], "failed")
            self.assertIsNone(queue_row["output_path"])
            self.assertIsNone(queue_row["result"]["output_path"])
            self.assertEqual(queue_row["result"]["generation_mode"], "narrator_only")
            self.assertTrue(queue_row["result"]["narrator_only"])
            self.assertEqual(history_row["state"], "failed")
            self.assertIsNone(history_row["output_path"])
            self.assertIsNone(history_row["result"]["output_path"])
            self.assertEqual(project_state["status"], "failed")
            self.assertIsNone(project_state.get("output_path"))
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

    def test_reported_output_must_match_the_requested_generation_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            job_id = "mismatched-output-generation-job"
            expected_output = root / "new-book.m4b"
            prior_output = root / "different-existing-book.m4b"
            prior_output.write_bytes(b"another book's old output" * 128)
            unexpected_output = root / "unexpected-worker-output.m4b"
            unexpected_output.write_bytes(b"unrelated worker output" * 128)
            save_state(
                project_folder,
                {
                    "status": "generating",
                    "generation_job_id": job_id,
                    "generation_target_path": str(expected_output),
                    "output_path": None,
                    "completed_chapters": [],
                    "generation_mode": "character_cast",
                    "narrator_only_generation": False,
                    "character_voice_profile_count": 2,
                },
            )
            bridge = DurableGenerationCompletionHarness(
                root, job_id,
                result={
                    "generation_mode": "character_cast",
                    "narrator_only": False,
                    "character_voice_profile_count": 2,
                },
            )
            summary = self._summary(output=unexpected_output)
            bridge._generation_finished(
                job_id, SimpleNamespace(folder=project_folder), summary, expected_output, "Saved Narrator",
            )

            queue_row = bridge._job_list({"include_hidden": False})[0]
            self.assertEqual(queue_row["state"], "failed")
            self.assertIsNone(queue_row["output_path"])
            self.assertIsNone(queue_row["result"]["output_path"])
            self.assertEqual(queue_row["result"]["generation_mode"], "character_cast")
            self.assertIsNone(load_state(project_folder).get("output_path"))
            self.assertTrue(unexpected_output.is_file())

    def test_incomplete_attempt_does_not_attach_preexisting_m4b_to_failed_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            job_id = "incomplete-generation-job"
            output = root / "previously-finished-book.m4b"
            output.write_bytes(b"existing complete audiobook" * 128)
            save_state(
                project_folder,
                {
                    "status": "generating",
                    "generation_job_id": job_id,
                    "generation_target_path": str(output),
                    "output_path": None,
                    "completed_chapters": [],
                    "generation_mode": "character_cast",
                    "narrator_only_generation": False,
                    "character_voice_profile_count": 2,
                },
            )
            bridge = DurableGenerationCompletionHarness(
                root, job_id,
                result={
                    "generation_mode": "character_cast",
                    "narrator_only": False,
                    "character_voice_profile_count": 2,
                },
            )
            summary = self._summary(output=output)
            # The old file exists and is non-empty, but this attempt completed
            # fewer chapters than the book requires. It must not be published
            # as the failed attempt's output in Queue or durable History.
            summary.chapters_completed = 0
            summary.chapters_completed_numbers = []
            summary.chapters_failed = []

            bridge._generation_finished(
                job_id, SimpleNamespace(folder=project_folder), summary, output, "Saved Narrator",
            )

            queue_row = bridge._job_list({"include_hidden": False})[0]
            history_row = bridge._history_list({})[0]
            project_state = load_state(project_folder)
            self.assertEqual(queue_row["state"], "failed")
            self.assertIsNone(queue_row["output_path"])
            self.assertIsNone(queue_row["result"]["output_path"])
            self.assertEqual(history_row["state"], "failed")
            self.assertIsNone(history_row["output_path"])
            self.assertIsNone(history_row["result"]["output_path"])
            self.assertIsNone(project_state.get("output_path"))
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
