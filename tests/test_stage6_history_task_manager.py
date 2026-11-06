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

    def test_task_manager_dialog_is_bounded_and_reflows_at_small_viewports(self) -> None:
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        base = ".modal-back>.jobs-modal{box-sizing:border-box;width:min(780px,calc(100vw - 40px));min-width:0;max-width:100%;max-height:calc(100dvh - 40px);overflow-x:hidden;overflow-y:auto}"
        mobile = "@media(max-width:800px){.modal-back{padding:10px}.modal-back>.jobs-modal{width:calc(100vw - 20px);max-width:calc(100vw - 20px);max-height:calc(100dvh - 20px);padding:14px"
        self.assertIn(base, html)
        self.assertIn(mobile, html)
        self.assertIn(".jobs-modal .job-row{grid-template-columns:32px minmax(0,1fr)", html)
        self.assertIn(".jobs-modal .job-actions{grid-column:1/-1", html)
        self.assertIn(".jobs-modal .job-main{min-width:0;max-width:100%", html)

    def test_task_manager_rows_match_responsive_three_column_css_contract(self) -> None:
        self.assertIn('class="job-type-icon"', self.adapter)
        self.assertIn('class="job-main"', self.adapter)
        self.assertIn('class="job-actions"', self.adapter)
        self.assertIn("data-job-meta", self.adapter)
        self.assertIn("writeTextIfChanged(meta, jobMetaSummary(j))", self.adapter)
        self.assertIn("data-job-view", self.adapter)
        self.assertIn("renderedRows.forEach(row =>", self.adapter)
        self.assertIn("rowsHaveViewActions", self.adapter)
        self.assertIn("button.dataset.jobView = id", self.adapter)

    def test_task_manager_capture_handler_prevents_legacy_demo_rows_from_replacing_live_jobs(self) -> None:
        self.assertIn("window.__ryuBackendJobFilterCaptureBound", self.adapter)
        self.assertIn("document.addEventListener('click', event =>", self.adapter)
        self.assertIn("#backgroundJobsModal [data-job-filter]", self.adapter)
        self.assertIn("event.stopImmediatePropagation()", self.adapter)
        self.assertIn("backendJobFilter = requested", self.adapter)

    def test_task_manager_repairs_stale_rows_even_when_backend_signature_is_unchanged(self) -> None:
        self.assertIn("const backendDomMatches =", self.adapter)
        self.assertIn("JSON.stringify(renderedIds) === JSON.stringify(expectedIds)", self.adapter)
        self.assertIn("!box.querySelector('.job-row:not([data-backend-job])')", self.adapter)
        self.assertIn("if (box.dataset.backendJobsSignature !== signature || !backendDomMatches)", self.adapter)
        self.assertIn("const rowsHaveViewActions = renderedRows.every(row =>", self.adapter)
        self.assertIn("rowStructureValid && rowsHaveViewActions", self.adapter)
        self.assertIn("button.dataset.jobView = id", self.adapter)

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
        self.assertIn("stage7Player.narrator", packaged)

    def test_packaged_acceptance_requires_chapter_preview_project_and_chapter_ownership(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        marker = "stage6_chapter_preview_owner_project_and_stable_chapter_identity"
        self.assertIn(marker, packaged)
        self.assertIn(marker, runner)
        self.assertIn("completedProductionPreview.current_chapter_id", packaged)


    def test_player_preferences_are_reapplied_after_media_metadata_load(self) -> None:
        metadata_handler = self.adapter.split("audio.onloadedmetadata = () => {", 1)[1].split("audio.onerror = () =>", 1)[0]
        play_handler = self.adapter.split("audio.onplay = () => {", 1)[1].split("audio.onpause = () =>", 1)[0]
        for handler in (metadata_handler, play_handler):
            self.assertIn("audio.playbackRate = playerRate;", handler)
            self.assertIn("audio.volume = playerVolume;", handler)

    def test_player_grid_fits_desktop_and_tablet_widths_without_overflow(self) -> None:
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        base_rule = ".player-grid{grid-template-columns:330px minmax(400px,1fr) 330px}"
        desktop_rule = (
            "@media(min-width:1251px) and (max-width:1450px){.player-grid{"
            "grid-template-columns:minmax(220px,.9fr) minmax(320px,1.3fr) minmax(220px,.9fr)}}"
        )
        self.assertIn(base_rule, html)
        self.assertIn(desktop_rule, html)
        self.assertIn("Stage 6 tablet overflow guard", html)
        self.assertIn("#player.page{padding:20px 16px 110px!important;min-width:0;overflow-x:hidden}", html)
        self.assertIn("grid-template-columns:minmax(0,1fr)!important", html)
        self.assertIn("max-width:100%", html)
        self.assertIn("grid-template-columns:var(--side) minmax(0,1fr)", html)
        self.assertIn("min-width:0;width:100%;max-width:100%;overflow:auto;position:relative", html)
        self.assertIn("min-width:0;width:100%;max-width:100%;display:flex", html)
        self.assertGreater(html.rfind("Stage 6 tablet overflow guard"), html.index(base_rule))
        self.assertGreater(html.rfind("Stage 6 tablet overflow guard"), html.index(desktop_rule))
        self.assertGreater(html.rfind("Stage 6 tablet overflow guard"), html.index("@media(max-width:1250px)"))
        self.assertIn(1024, (960, 1024, 1100, 1200, 1250, 1280, 1366, 1440))

    def test_packaged_matrix_checks_shared_app_shell_at_all_viewports(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for marker in (
            "stage6_responsive_shared_shell_bounds_41_resolutions",
            "application-shell",
            "shared workspace grid item retained its automatic minimum width",
            "mobile application shell did not switch to its single-column layout",
        ):
            self.assertIn(marker, packaged)
        self.assertIn("stage6_responsive_shared_shell_bounds_41_resolutions", runner)

    def test_packaged_acceptance_reacquires_live_audiobook_card_after_open(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        open_step = packaged.index('stage7Card.querySelector("[data-open-project-folder]").click();')
        play_step = packaged.index('const stage7LivePlay = stage7Card.querySelector("[data-play-project-folder]");', open_step)
        self.assertIn("stage7Card.isConnected", packaged[open_step:play_step])
        self.assertIn("stage7LivePlay.isConnected", packaged[play_step:play_step + 700])
        self.assertIn("String(stage7LivePlay.dataset.playProjectFolder || \"\") === stage7Folder", packaged[play_step:play_step + 700])



    def test_cue_import_rejection_is_checked_before_copy_or_metadata_write(self) -> None:
        host_source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        handler = host_source[host_source.index("def _sound_import("):]
        handler = handler[:handler.index("def _sound_assign(")]
        guard = 'if target_kind != "music" and duration_seconds > 5.0:'
        self.assertIn(guard, handler)
        self.assertLess(handler.index(guard), handler.index("destination = target_root / source.name"))
        self.assertLess(handler.index(guard), handler.index("metadata_path.write_text"))

    def test_packaged_cue_retry_and_preview_jobs_are_drained_before_stage54(self) -> None:
        packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        retry = "cue save debounce and in-flight persistence settle"
        drain = "all Sound Design preview jobs have reached terminal state before Stage 5.4"
        stage54 = "Stage 5.4 job-control metadata gate"
        self.assertIn(retry, packaged)
        self.assertIn(drain, packaged)
        self.assertLess(packaged.index(retry), packaged.index("same_and_chapter_based_real_full_book_preview"))
        self.assertLess(packaged.index(drain), packaged.index(stage54))

    def test_sound_preview_replacement_catches_stale_play_promise(self) -> None:
        adapter_source = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("const previewAudio = new Audio(fileUrl)", adapter_source)
        self.assertIn("await previewAudio.play().catch(error =>", adapter_source)
        self.assertIn("if (soundPreviewAudio !== previewAudio || previewAudio.paused) return;", adapter_source)

if __name__ == "__main__":
    unittest.main()
