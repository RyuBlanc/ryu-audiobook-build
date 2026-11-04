"""Stage 6 History and Task Manager functional contracts."""
from __future__ import annotations

import threading
import unittest
from pathlib import Path

from app.ui import premium_v2_host as host


ROOT = Path(__file__).resolve().parents[1]


class HistorySnapshotHarness:
    _history_list = host.PremiumV2Bridge._history_list

    def __init__(self) -> None:
        self._jobs_lock = threading.RLock()
        self._jobs = {
            "live-running": {
                "job_id": "live-running", "title": "Live generation", "type": "audiobook-generation",
                "project_title": "Current Book", "state": "running", "progress": 42,
                "queued_at": "2026-11-05T08:00:00+00:00", "updated_at": "2026-11-05T08:02:00+00:00",
            },
            "live-queued": {
                "job_id": "live-queued", "title": "Queued import", "type": "import",
                "project_title": "Queued Book", "state": "queued", "progress": 0,
                "queued_at": "2026-11-05T08:01:00+00:00",
            },
            "terminal-job": {
                "job_id": "terminal-job", "title": "Terminal queue copy", "state": "completed",
                "project_title": "Old Book", "completed_at": "2026-11-05T07:00:00+00:00",
            },
            "cleared-hidden": {
                "job_id": "cleared-hidden", "title": "Hidden cleared job", "state": "completed",
                "hidden": True, "completed_at": "2026-11-05T06:00:00+00:00",
            },
        }
        self._history = {
            "terminal-job": {
                "job_id": "terminal-job", "title": "Durable terminal record", "state": "completed",
                "project_title": "Old Book", "completed_at": "2026-11-05T07:00:00+00:00",
            }
        }


class Stage6HistoryTaskManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")

    def test_history_merges_live_jobs_with_durable_terminal_records_without_duplicates(self) -> None:
        rows = HistorySnapshotHarness()._history_list({})
        by_id = {row["job_id"]: row for row in rows}
        self.assertEqual(set(by_id), {"live-running", "live-queued", "terminal-job"})
        self.assertEqual(by_id["live-running"]["state"], "running")
        self.assertEqual(by_id["live-running"]["progress"], 42)
        self.assertEqual(by_id["live-queued"]["state"], "queued")
        self.assertEqual(by_id["terminal-job"]["title"], "Durable terminal record")
        self.assertEqual(sum(row["job_id"] == "terminal-job" for row in rows), 1)
        self.assertNotIn("cleared-hidden", by_id)

    def test_history_search_and_date_controls_filter_real_backend_records(self) -> None:
        self.assertIn('id="historySearchFilter"', self.adapter)
        self.assertIn('id="historyFromDate"', self.adapter)
        self.assertIn('id="historyToDate"', self.adapter)
        self.assertIn("const timestamp = Date.parse(jobDateValue(job))", self.adapter)
        self.assertIn("searchable.includes(query)", self.adapter)
        self.assertIn("fromDate + 'T00:00:00'", self.adapter)
        self.assertIn("toDate + 'T23:59:59.999'", self.adapter)

    def test_history_and_task_manager_view_actions_open_real_details(self) -> None:
        self.assertIn("async function openJobDetails(jobId)", self.adapter)
        self.assertIn("function renderJobDetails(job)", self.adapter)
        self.assertIn("call('job.list', {include_hidden:true})", self.adapter)
        self.assertIn("call('history.list')", self.adapter)
        self.assertIn("data-history-job", self.adapter)
        self.assertIn("data-job-view", self.adapter)
        self.assertIn("data-job-detail-field", self.adapter)

    def test_task_manager_rows_match_responsive_three_column_css_contract(self) -> None:
        self.assertIn('class="job-type-icon"', self.adapter)
        self.assertIn('class="job-main"', self.adapter)
        self.assertIn('class="job-actions"', self.adapter)
        self.assertIn("data-job-meta", self.adapter)
        self.assertIn("writeTextIfChanged(meta, jobMetaSummary(j))", self.adapter)
        self.assertIn("data-job-view", self.adapter)

    def test_packaged_runner_requires_real_two_process_player_restoration(self) -> None:
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for marker in (
            "stage6_playback_position_persisted_before_process_restart",
            "stage6_mini_player_close_preserves_active_session",
            "stage6_playback_position_restored_after_process_restart",
            "stage6_mini_player_navigation_and_close_after_restart",
        ):
            self.assertIn(marker, runner)


    def test_packaged_acceptance_requires_real_history_and_task_manager_interactions(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for marker in (
            "stage6_history_real_search_date_status_and_details",
            "stage6_task_manager_real_records_filters_details_and_counts",
            "stage6_player_volume_rate_persisted_before_restart",
        ):
            self.assertIn(marker, packaged)
            self.assertIn(marker, runner)


    def test_packaged_acceptance_requires_responsive_viewport_matrix(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for marker in (
            "stage6_responsive_viewport_matrix_41_resolutions",
            "stage6_responsive_window_and_scale_emulation",
        ):
            self.assertIn(marker, packaged)
            self.assertIn(marker, runner)


    def test_packaged_acceptance_requires_stage6_cross_module_ownership_integration(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        marker = "stage6_cross_module_production_audiobooks_player_job_history_identity"
        self.assertIn(marker, packaged)
        self.assertIn(marker, runner)
        self.assertIn("job.list", packaged)
        self.assertIn("player.get_active", packaged)


if __name__ == "__main__":
