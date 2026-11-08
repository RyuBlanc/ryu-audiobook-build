"""Stage 5.3 restart-recovery and durable job-state regression contracts."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

from app.core.state import load_state, save_state
from app.ui import premium_v2_host as host


class DurableJobRecoveryHarness:
    """Exercise the production durable-job loader without constructing a Qt window."""

    _load_durable_jobs = host.PremiumV2Bridge._load_durable_jobs
    _reconcile_interrupted_generation_project = host.PremiumV2Bridge._reconcile_interrupted_generation_project
    _terminal_job_state = staticmethod(host.PremiumV2Bridge._terminal_job_state)
    _persist_json_rows = host.PremiumV2Bridge._persist_json_rows
    _persist_jobs = host.PremiumV2Bridge._persist_jobs
    _persist_history = host.PremiumV2Bridge._persist_history
    _record_history_job = host.PremiumV2Bridge._record_history_job
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, jobs_path: Path, history_path: Path) -> None:
        self._jobs: dict[str, dict] = {}
        self._history: dict[str, dict] = {}
        self._jobs_lock = threading.RLock()
        self._jobs_path = lambda: jobs_path
        self._history_path = lambda: history_path


class Stage53DurableJobRecoveryTests(unittest.TestCase):
    def test_restart_marks_paused_and_running_generation_jobs_failed_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_path = root / "premium_v2_jobs.json"
            history_path = root / "premium_v2_history.json"
            rows = []
            projects = {}
            expected_identity: dict[str, dict[str, object]] = {}

            for index, prior_status in enumerate(("paused", "running"), start=1):
                job_id = f"generation-job-{index}"
                generation_mode = "narrator_only" if index == 1 else "character_cast"
                narrator_only = generation_mode == "narrator_only"
                character_voice_profile_count = 0 if narrator_only else 3
                expected_identity[job_id] = {
                    "generation_mode": generation_mode,
                    "narrator_only": narrator_only,
                    "character_voice_profile_count": character_voice_profile_count,
                }
                project_folder = root / f"project-{index}"
                project_folder.mkdir()
                save_state(
                    project_folder,
                    {
                        "status": "generating",
                        "generation_job_id": job_id,
                        "output_path": None,
                        "completed_chapters": [1],
                        "generation_mode": generation_mode,
                        "narrator_only_generation": narrator_only,
                        "character_voice_profile_count": character_voice_profile_count,
                    },
                )
                projects[job_id] = project_folder
                rows.append(
                    {
                        "job_id": job_id,
                        "id": job_id,
                        "type": "audiobook-generation",
                        "title": f"Generate Book {index}",
                        "project_title": f"Book {index}",
                        "project_folder": str(project_folder),
                        "state": prior_status,
                        "progress": 40,
                        "stage": "Rendering narration chunks",
                        "message": "Worker was active before restart",
                        "retry_count": 0,
                        "recoverable": False,
                        "result": {
                            "generation_mode": generation_mode,
                            "narrator_only": narrator_only,
                            "character_voice_profile_count": character_voice_profile_count,
                        },
                    }
                )

            jobs_path.write_text(json.dumps(rows), encoding="utf-8")
            bridge = DurableJobRecoveryHarness(jobs_path, history_path)

            bridge._load_durable_jobs()

            persisted_rows = json.loads(jobs_path.read_text(encoding="utf-8"))
            persisted_by_id = {row["job_id"]: row for row in persisted_rows}
            self.assertEqual(set(bridge._jobs), set(projects))
            self.assertEqual(set(bridge._history), set(projects))

            for job_id, project_folder in projects.items():
                with self.subTest(job_id=job_id):
                    expected = expected_identity[job_id]
                    recovered = bridge._jobs[job_id]
                    self.assertEqual(recovered["state"], "failed")
                    self.assertEqual(recovered["stage"], "Interrupted by application restart")
                    self.assertTrue(recovered["recoverable"])
                    self.assertEqual(recovered["error"]["code"], "interrupted")
                    self.assertEqual(persisted_by_id[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["job_id"], job_id)
                    for durable_row in (recovered, persisted_by_id[job_id], bridge._history[job_id]):
                        self.assertEqual(durable_row["result"]["generation_mode"], expected["generation_mode"])
                        self.assertIs(durable_row["result"]["narrator_only"], expected["narrator_only"])
                        self.assertEqual(
                            durable_row["result"]["character_voice_profile_count"],
                            expected["character_voice_profile_count"],
                        )

                    project_state = load_state(project_folder)
                    self.assertEqual(project_state["status"], "failed")
                    self.assertEqual(project_state["generation_job_id"], job_id)
                    self.assertTrue(project_state["generation_recovery_required"])
                    self.assertEqual(project_state["generation_mode"], expected["generation_mode"])
                    self.assertIs(project_state["narrator_only_generation"], expected["narrator_only"])
                    self.assertEqual(
                        project_state["character_voice_profile_count"],
                        expected["character_voice_profile_count"],
                    )

    def test_old_interrupted_job_cannot_overwrite_a_newer_project_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_path = root / "premium_v2_jobs.json"
            history_path = root / "premium_v2_history.json"
            project_folder = root / "project"
            project_folder.mkdir()
            save_state(
                project_folder,
                {
                    "status": "generating",
                    "generation_job_id": "new-generation-job",
                    "generation_started_at": "2026-11-03T12:00:00+00:00",
                },
            )
            jobs_path.write_text(
                json.dumps(
                    [
                        {
                            "job_id": "old-generation-job",
                            "id": "old-generation-job",
                            "type": "audiobook-generation",
                            "project_title": "Book",
                            "project_folder": str(project_folder),
                            "state": "paused",
                            "progress": 25,
                            "recoverable": False,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            bridge = DurableJobRecoveryHarness(jobs_path, history_path)

            bridge._load_durable_jobs()

            self.assertEqual(bridge._jobs["old-generation-job"]["state"], "failed")
            project_state = load_state(project_folder)
            self.assertEqual(project_state["status"], "generating")
            self.assertEqual(project_state["generation_job_id"], "new-generation-job")
            self.assertNotIn("generation_recovery_required", project_state)


if __name__ == "__main__":
    unittest.main()


class GenerationFinishOwnershipHarness:
    """Call the real completion callback without constructing the Qt application."""

    _generation_finished = host.PremiumV2Bridge._generation_finished
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, job_id: str) -> None:
        self._jobs_lock = threading.RLock()
        self._generators = {job_id: object()}
        self._job_update = Mock()


class Stage53StaleGenerationCallbackTests(unittest.TestCase):
    def test_late_success_cannot_overwrite_a_newer_project_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            old_output = root / "older-job.m4b"
            old_output.write_bytes(b"old-job-output" * 100)
            new_output = root / "newer-job.m4b"
            state = {
                "status": "generating",
                "generation_job_id": "newer-generation-job",
                "generation_target_path": str(new_output),
                "output_path": None,
                "completed_chapters": [],
            }
            bridge = GenerationFinishOwnershipHarness("older-generation-job")
            project = SimpleNamespace(folder=project_folder)
            summary = SimpleNamespace(
                output_path=old_output,
                cancelled=False,
                packaging_failed=False,
                chapters_failed=[],
                chapters_completed=1,
                chapters_total=1,
                chapters_completed_numbers=[1],
                failure_details={},
            )

            with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state") as save:
                bridge._generation_finished(
                    "older-generation-job", project, summary, old_output, "Old Narrator"
                )

            self.assertEqual(state["status"], "generating")
            self.assertEqual(state["generation_job_id"], "newer-generation-job")
            self.assertEqual(state["generation_target_path"], str(new_output))
            self.assertIsNone(state["output_path"])
            save.assert_not_called()
            update = bridge._job_update.call_args.kwargs
            self.assertEqual(update["state"], "completed")
            self.assertIsNone(update["output_path"])
            self.assertTrue(update["result"]["superseded"])
            self.assertNotIn("older-generation-job", bridge._generators)

    def test_project_switch_keeps_late_completion_bound_to_original_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_a_folder = root / "project-a"
            project_b_folder = root / "project-b"
            project_a_folder.mkdir()
            project_b_folder.mkdir()
            output_a = root / "book-a.m4b"
            output_a.write_bytes(b"project-a-output" * 100)
            save_state(
                project_a_folder,
                {
                    "status": "generating",
                    "generation_job_id": "project-a-job",
                    "output_path": None,
                },
            )
            save_state(
                project_b_folder,
                {
                    "status": "generating",
                    "generation_job_id": "project-b-job",
                    "output_path": None,
                },
            )

            project_a = SimpleNamespace(folder=project_a_folder)
            project_b = SimpleNamespace(folder=project_b_folder)
            bridge = GenerationFinishOwnershipHarness("project-a-job")
            # The UI has since switched to B; completion retains the captured A
            # project reference and must not consult or overwrite B's current state.
            bridge._active_project = Mock(return_value=project_b)
            summary = SimpleNamespace(
                output_path=output_a,
                cancelled=False,
                packaging_failed=False,
                chapters_failed=[],
                chapters_completed=1,
                chapters_total=1,
                chapters_completed_numbers=[1],
                failure_details={},
            )

            bridge._generation_finished(
                "project-a-job", project_a, summary, output_a, "Project A Narrator"
            )

            project_a_state = load_state(project_a_folder)
            project_b_state = load_state(project_b_folder)
            self.assertEqual(project_a_state["status"], "completed")
            self.assertEqual(project_a_state["generation_job_id"], "project-a-job")
            self.assertEqual(project_a_state["output_path"], str(output_a))
            self.assertEqual(project_b_state["status"], "generating")
            self.assertEqual(project_b_state["generation_job_id"], "project-b-job")
            self.assertIsNone(project_b_state["output_path"])
            update = bridge._job_update.call_args.kwargs
            self.assertEqual(update["state"], "completed")
            self.assertEqual(update["output_path"], str(output_a))
