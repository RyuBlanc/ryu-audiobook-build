"""Stage 5.4 explicit retry/recovery and terminal-control race tests."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ui import premium_v2_host as host


class RetryRecoveryBridgeHarness:
    _job_retry = host.PremiumV2Bridge._job_retry
    _job_recover = host.PremiumV2Bridge._job_recover
    _restart_generation_from_job = host.PremiumV2Bridge._restart_generation_from_job
    _job_pause = host.PremiumV2Bridge._job_pause
    _job_resume = host.PremiumV2Bridge._job_resume
    _job_cancel = host.PremiumV2Bridge._job_cancel

    def __init__(self, row: dict) -> None:
        self._jobs_lock = threading.RLock()
        self._jobs = {row["job_id"]: dict(row)}
        self._generators = {}
        self._production_generate_book = self._create_new_job

    def _create_new_job(self, payload):
        self._jobs["new-generation-job"] = {
            "job_id": "new-generation-job",
            "type": "audiobook-generation",
            "state": "running",
            "project_folder": payload["_project_folder"],
            "retry_count": 0,
        }
        return {"job_id": "new-generation-job", "state": "running"}

    def _job_update(self, job_id, **changes):
        self._jobs[job_id].update(changes)
        return dict(self._jobs[job_id])


def _source_row(folder: Path, *, state="failed", code="generation_failed", recoverable=True):
    return {
        "job_id": "previous-generation-job",
        "type": "audiobook-generation",
        "state": state,
        "project_folder": str(folder),
        "project_title": "Saved Book",
        "recoverable": recoverable,
        "retry_count": 1,
        "error": {"code": code, "message": "Previous generation did not complete."},
    }


class FakeThread:
    def __init__(self) -> None:
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive


class TerminalizingManager:
    def __init__(self, bridge: "ControlRaceBridgeHarness") -> None:
        self.bridge = bridge
        self._thread = FakeThread()

    def _finish(self):
        self.bridge._jobs["race-job"]["state"] = "completed"
        self._thread.alive = False

    def pause(self):
        self._finish()

    def resume(self):
        self._finish()

    def cancel(self):
        self._finish()


class ControlRaceBridgeHarness:
    _job_pause = host.PremiumV2Bridge._job_pause
    _job_resume = host.PremiumV2Bridge._job_resume
    _job_cancel = host.PremiumV2Bridge._job_cancel

    def __init__(self, initial_state: str, manager: TerminalizingManager | None) -> None:
        self._jobs_lock = threading.RLock()
        self._jobs = {
            "race-job": {
                "job_id": "race-job",
                "type": "audiobook-generation",
                "state": initial_state,
            }
        }
        self._generators = {"race-job": manager} if manager is not None else {}
        self._preview_cancel_events = {}
        self._import_cancel_events = {}


class Stage54RetryRecoveryTests(unittest.TestCase):
    def _project(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(folder=folder, title="Saved Book", chapters=[])

    def test_retry_restarts_the_original_project_not_the_currently_selected_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = self._project(root / "original")
            current = self._project(root / "currently-selected")
            row = _source_row(original.folder)
            bridge = RetryRecoveryBridgeHarness(row)

            with patch.object(host, "list_projects", return_value=[current, original]), patch.object(
                host, "load_state", return_value={"generation_job_id": row["job_id"]}
            ):
                result = bridge._job_retry({"job_id": row["job_id"]})

            self.assertEqual(result["job_id"], "new-generation-job")
            self.assertEqual(result["retry_of_job_id"], row["job_id"])
            self.assertEqual(bridge._jobs["new-generation-job"]["retry_of_job_id"], row["job_id"])
            self.assertEqual(bridge._jobs["new-generation-job"]["retry_count"], 2)

    def test_recover_is_limited_to_interrupted_jobs_and_reuses_original_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self._project(root / "project")
            row = _source_row(project.folder, code="interrupted", recoverable=True)
            bridge = RetryRecoveryBridgeHarness(row)

            with patch.object(host, "list_projects", return_value=[project]), patch.object(
                host, "load_state",
                return_value={
                    "generation_job_id": row["job_id"],
                    "generation_recovery_required": True,
                },
            ):
                result = bridge._job_recover({"job_id": row["job_id"]})

            self.assertEqual(result["recovery_of_job_id"], row["job_id"])
            self.assertEqual(bridge._jobs["new-generation-job"]["recovery_of_job_id"], row["job_id"])

    def test_recover_rejects_ordinary_failed_jobs(self) -> None:
        row = _source_row(Path("unavailable-project"), code="generation_failed", recoverable=True)
        bridge = RetryRecoveryBridgeHarness(row)
        with self.assertRaisesRegex(ValueError, "not an interrupted"):
            bridge._job_recover({"job_id": row["job_id"]})

    def test_retry_rejects_nonrecoverable_failed_job(self) -> None:
        row = _source_row(Path("unavailable-project"), recoverable=False)
        bridge = RetryRecoveryBridgeHarness(row)
        with self.assertRaisesRegex(ValueError, "not marked recoverable"):
            bridge._job_retry({"job_id": row["job_id"]})

    def test_retry_rejects_a_project_owned_by_a_newer_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self._project(root / "project")
            row = _source_row(project.folder)
            bridge = RetryRecoveryBridgeHarness(row)
            with patch.object(host, "list_projects", return_value=[project]), patch.object(
                host, "load_state", return_value={"generation_job_id": "newer-job"}
            ):
                with self.assertRaisesRegex(ValueError, "newer generation job"):
                    bridge._job_retry({"job_id": row["job_id"]})

    def test_terminal_completion_wins_over_late_pause_resume_and_cancel(self) -> None:
        for action, initial_state in (("pause", "running"), ("resume", "paused"), ("cancel", "running")):
            with self.subTest(action=action):
                bridge = ControlRaceBridgeHarness(initial_state, None)
                manager = TerminalizingManager(bridge)
                bridge._generators["race-job"] = manager
                result = getattr(bridge, f"_job_{action}")({"job_id": "race-job"})
                self.assertEqual(result["state"], "completed")
                self.assertEqual(bridge._jobs["race-job"]["state"], "completed")


class Stage54RetryRecoveryUiContractTests(unittest.TestCase):
    def test_background_jobs_has_real_retry_and_recover_commands(self) -> None:
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        self.assertIn("action(interrupted ? 'recover' : 'retry'", adapter)
        self.assertIn("state === 'cancelled' && isGeneration", adapter)
        self.assertIn("retry:'job.retry', recover:'job.recover'", adapter)


if __name__ == "__main__":
    unittest.main()
