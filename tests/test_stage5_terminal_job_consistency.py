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


if __name__ == "__main__":
    unittest.main()
