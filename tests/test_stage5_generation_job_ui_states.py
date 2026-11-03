"""Stage 5.3 UI-state contracts for generation controls in Background Jobs and Dashboard."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Stage53GenerationJobUiStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        cls.packaged = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")

    def test_background_jobs_generation_actions_are_exclusive_by_state(self):
        start = self.adapter.index("function backgroundGenerationJobActions(")
        end = self.adapter.index("let backendJobFilter", start)
        renderer = self.adapter[start:end]
        self.assertIn("state === 'running'", renderer)
        self.assertIn("state === 'pause_requested'", renderer)
        self.assertIn("state === 'paused'", renderer)
        self.assertIn("Pausing at the next chapter boundary", renderer)
        self.assertIn("Cancelling…", renderer)
        self.assertNotIn("['running','pause_requested'].includes(state) ? action('pause'", renderer)
        self.assertIn("backgroundGenerationJobActions(j, id, action, canControlGeneration, canCancelImport, canCancelPreview)", self.adapter)
        for command in ("pause:'job.pause'", "resume:'job.resume'", "cancel:'job.cancel'"):
            self.assertIn(command, self.adapter)

    def test_dashboard_control_keeps_stable_identity_and_pending_labels(self):
        start = self.adapter.index("function refreshDashboardGeneration(")
        end = self.adapter.index("function audiobookPageActive()", start)
        renderer = self.adapter[start:end]
        self.assertIn("dashboardGenerationControl", self.adapter)
        self.assertIn("controlState === 'pause_requested' ? 'Pausing…'", renderer)
        self.assertIn("controlState === 'cancel_requested' ? 'Cancelling…'", renderer)
        self.assertIn("delete control.dataset.dashboardGenerationAction", renderer)
        self.assertIn("button.dataset.dashboardGenerationControl === '1'", self.adapter)

    def test_frozen_app_acceptance_exercises_real_job_ui_and_bridge_dispatch(self):
        self.assertIn("runStage53JobUiAcceptance()", self.packaged)
        self.assertIn("stage53_background_job_state_controls", self.packaged)
        self.assertIn("stage53_dashboard_job_state_controls", self.packaged)
        self.assertIn('command === "job.list"', self.packaged)
        self.assertIn('["job.pause","job.resume","job.cancel"]', self.packaged)

    def test_production_preview_monitor_acceptance_reopens_page_before_render_assertion(self):
        preview_start = self.packaged.index("real Production Preview job start")
        reopen = self.packaged.index('window.go("generate")', preview_start)
        visible = self.packaged.index("Production Preview monitor page is visible", preview_start)
        monitor_wait = self.packaged.index("Production Preview monitor selected chapter identity", preview_start)
        audio_completion = self.packaged.index("real Production Preview audio completion", preview_start)
        self.assertLess(preview_start, reopen)
        self.assertLess(reopen, visible)
        self.assertLess(visible, monitor_wait)
        self.assertLess(monitor_wait, audio_completion)
        self.assertIn("Production preview monitor diagnostic", self.packaged)
        self.assertIn("latestPreviewJob?.current_chapter_id", self.packaged)
    def test_frozen_app_acceptance_runs_real_saved_profile_full_generation(self):
        packaged_runner = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        self.assertIn("full_generation_project_folder", packaged_runner)
        self.assertIn("full_generation_output_path", packaged_runner)
        self.assertIn("stage53_packaged_real_full_generation", self.packaged)
        self.assertIn('document.querySelector("#startGenerate").click()', self.packaged)
        self.assertIn('invoke("history.list", {})', self.packaged)
        self.assertIn('historyGenerationJob.project_folder', self.packaged)
        self.assertIn('completedGenerationProject.completed === true', self.packaged)
        self.assertNotIn('completedGenerationProject.generation_job_id', self.packaged)


if __name__ == "__main__":
    unittest.main()
