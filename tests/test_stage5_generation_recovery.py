"""Stage 5.3 restart-recovery and durable job-state regression contracts."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
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

            for index, prior_status in enumerate(("paused", "running"), start=1):
                job_id = f"generation-job-{index}"
                project_folder = root / f"project-{index}"
                project_folder.mkdir()
                save_state(
                    project_folder,
                    {
                        "status": "generating",
                        "generation_job_id": job_id,
                        "output_path": None,
                        "completed_chapters": [1],
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
                    recovered = bridge._jobs[job_id]
                    self.assertEqual(recovered["state"], "failed")
                    self.assertEqual(recovered["stage"], "Interrupted by application restart")
                    self.assertTrue(recovered["recoverable"])
                    self.assertEqual(recovered["error"]["code"], "interrupted")
                    self.assertEqual(persisted_by_id[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["job_id"], job_id)

                    project_state = load_state(project_folder)
                    self.assertEqual(project_state["status"], "failed")
                    self.assertEqual(project_state["generation_job_id"], job_id)
                    self.assertTrue(project_state["generation_recovery_required"])

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
