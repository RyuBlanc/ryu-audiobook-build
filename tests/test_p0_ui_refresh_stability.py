"""P0 UI regression checks for flicker-free background job progress updates."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackgroundJobRefreshStabilityTests(unittest.TestCase):

    def test_polling_dom_writes_are_guarded_and_hidden_dashboard_is_not_repainted(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        self.assertIn("if (node.textContent === next) return false;", adapter)
        self.assertIn("if (node.style[property] === next) return false;", adapter)
        start = adapter.index("async function refreshJobsImpl()")
        end = adapter.index("async function monitorJob(", start)
        refresh = adapter[start:end]
        self.assertIn("if (isVisiblePage('dashboard')) refreshDashboardGeneration(allJobs);", refresh)
        self.assertIn("writeTextIfChanged(messageNode, j.message || '')", refresh)
        self.assertIn("writeStyleIfChanged(progress, 'width', pct + '%')", refresh)
        self.assertIn("writeTextIfChanged($('jobsRunningCount'),", refresh)

    def test_job_progress_widgets_are_scoped_to_the_originating_page(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function monitorJob(")
        end = adapter.index("function requestElevenLabsApiKey()", start)
        monitor = adapter[start:end]
        self.assertIn("const originPage = document.querySelector('.page.active')?.id || ''", monitor)
        self.assertIn("const originVisible = isVisiblePage(originPage)", monitor)
        self.assertIn("originVisible && originPage === 'generate'", monitor)
        self.assertIn("originVisible && originPage === 'import' && job.type === 'import'", monitor)
        self.assertIn("originVisible && originPage === 'characters' && job.type === 'character-analysis'", monitor)
        self.assertIn("originVisible && originPage === 'voices' && job.type === 'voice-preview'", monitor)
        self.assertNotIn("if ($('genPercent')) $('genPercent').textContent =", monitor)
        self.assertNotIn("if ($('importBar')) $('importBar').style.width =", monitor)

    def test_generic_notifications_do_not_mutate_other_workflows(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("const message = (text, error = false) =>")
        end = adapter.index("const act =", start)
        helper = adapter[start:end]
        self.assertNotIn("const node = $('importStatus')", helper)
        self.assertNotIn("const validation = $('validation')", helper)
        self.assertIn("document.querySelector('.page.active #validation')", helper)
        self.assertIn("writeTextIfChanged(toasts, text)", helper)

    def test_active_project_refresh_is_ordered_and_clears_stale_identity(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        self.assertIn("let activeProjectCardEpoch = 0", adapter)
        start = adapter.index("async function refreshCurrentProjectCard(")
        end = adapter.index("function installProjectCardStatusObserver()", start)
        refresh = adapter[start:end]
        self.assertIn("const requestToken = ++activeProjectCardEpoch", refresh)
        self.assertIn("if (requestToken !== activeProjectCardEpoch)", refresh)
        self.assertIn("window.ryuPremiumActiveProject = null", refresh)

    def test_project_switch_flushes_pending_chapter_edits_before_open(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        dashboard_start = adapter.index("if ($('dashboard')) $('dashboard').addEventListener('click'")
        library_start = adapter.index("if ($('libraryGrid')) $('libraryGrid').addEventListener('click'", dashboard_start)
        dashboard = adapter[dashboard_start:library_start]
        library_end = adapter.index("if ($('libraryGrid') && !$('libraryGrid').dataset.bulkDeleteBound)", library_start)
        library = adapter[library_start:library_end]
        for block in (dashboard, library):
            self.assertLess(block.index("await flushChapterDraftBeforeSwitch()"), block.index("call('project.open'"))
            self.assertLess(block.index("call('project.open'"), block.index("await refreshCurrentProjectCard()"))
            self.assertIn("await refreshChapters()", block)

    def test_empty_chapter_state_clears_prototype_text_and_disables_editing(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function refreshChapters()")
        end = adapter.index("async function refreshCharacters()", start)
        refresh = adapter[start:end]
        self.assertIn("let noActiveProject = false", refresh)
        self.assertIn("loaded = await call('chapter.list')", refresh)
        self.assertIn("active project is no longer available in the local library", refresh)
        self.assertIn("data-chapter-empty-state", refresh)
        self.assertIn("No project selected. Import a book or open one from Library to begin.", refresh)
        self.assertIn("editor.value = ''", refresh)
        self.assertIn("editor.disabled = true", refresh)
        self.assertIn("writeBooleanIfChanged(button, 'disabled', true)", refresh)
        self.assertIn("if (typeof renderLiveChapterInsights === 'function') renderLiveChapterInsights()", refresh)
        self.assertIn("Draft preserved locally — chapter refresh needs attention", refresh)

    def test_progress_text_is_updated_in_place_not_used_to_rebuild_job_rows(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function refreshJobsImpl()")
        end = adapter.index("async function monitorJob(", start)
        refresh = adapter[start:end]
        signature_start = refresh.index("const signature = jobs.map")
        signature_end = refresh.index("if (box.dataset.backendJobsSignature !== signature)", signature_start)
        signature = refresh[signature_start:signature_end]

        self.assertIn("j.job_id, j.state, j.type, j.title, Boolean(j.recoverable)", signature)
        self.assertNotIn("Boolean(j.message)", signature)
        self.assertNotIn("Boolean(j.error?.message)", signature)
        self.assertIn("if (box && panelVisible)", refresh)
        self.assertIn("writeTextIfChanged(messageNode, j.message || '')", refresh)
        self.assertIn("writeTextIfChanged(errorNode, j.error?.message || '')", refresh)
        self.assertIn("writeStyleIfChanged(progress, 'width', pct + '%')", refresh)


if __name__ == "__main__":
    unittest.main()
