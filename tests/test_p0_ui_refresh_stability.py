"""P0 UI regression checks for flicker-free background job progress updates."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackgroundJobRefreshStabilityTests(unittest.TestCase):
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
        self.assertIn("setTextIfChanged(messageNode, j.message || '')", refresh)
        self.assertIn("setTextIfChanged(errorNode, j.error?.message || '')", refresh)
        self.assertIn("setStyleIfChanged(progress, 'width', pct + '%')", refresh)
        self.assertIn("setTextIfChanged(messageNode, j.message || '')", refresh)
        self.assertIn("setHiddenIfChanged(errorNode, !j.error?.message)", refresh)



    def test_repeated_dashboard_poll_skips_unchanged_text_and_progress_writes(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        helper_start = adapter.index("function setTextIfChanged(node, value)")
        helper_end = adapter.index("function setStyleIfChanged(node, property, value)", helper_start)
        text_helper = adapter[helper_start:helper_end]
        self.assertIn("if (node.textContent === next) return false;", text_helper)

        dashboard_start = adapter.index("function refreshDashboardGeneration(")
        dashboard_end = adapter.index("function audiobookPageActive()", dashboard_start)
        dashboard = adapter[dashboard_start:dashboard_end]
        self.assertIn("setTextIfChanged(percentLabel, percent + '% complete')", dashboard)
        self.assertIn("setStyleIfChanged(fill, 'width', percent + '%')", dashboard)
        self.assertNotIn("percentLabel.textContent =", dashboard)
        self.assertNotIn("fill.style.width =", dashboard)

        jobs_start = adapter.index("async function refreshJobsImpl()")
        jobs_end = adapter.index("async function monitorJob(", jobs_start)
        jobs = adapter[jobs_start:jobs_end]
        self.assertIn("setTextIfChanged(stage, j.stage || j.message || j.state || 'unknown')", jobs)
        self.assertIn("setStyleIfChanged(progress, 'width', pct + '%')", jobs)
        self.assertNotIn("if (stage) stage.textContent =", jobs)
        self.assertNotIn("if (progress) progress.style.width =", jobs)



    def test_repeated_job_monitor_tick_skips_unchanged_progress_writes(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        monitor_start = adapter.index("async function monitorJob(")
        monitor_end = adapter.index("function requestElevenLabsApiKey()", monitor_start)
        monitor = adapter[monitor_start:monitor_end]
        self.assertIn("const originPage = document.querySelector('.page.active')?.id || ''", monitor)
        self.assertIn("const originPageVisible = Boolean(originPage && $(originPage)?.classList.contains('active'))", monitor)
        self.assertIn("setTextIfChanged($('genPercent'), Math.round(pct) + '%')", monitor)
        self.assertIn("setCssPropertyIfChanged($('genRing'), '--progress', pct + '%')", monitor)
        self.assertIn("setStyleIfChanged($('importBar'), 'width', pct + '%')", monitor)
        self.assertIn("setTextIfChanged($('aiProgressText'), job.stage || job.message || job.state)", monitor)
        self.assertIn("setStyleIfChanged($('aiProgressBar'), 'width', pct + '%')", monitor)
        self.assertIn("setStyleIfChanged($('previewProgress'), 'width', pct + '%')", monitor)
        self.assertIn("setTextIfChanged($('previewState'),", monitor)
        self.assertIn("setTextIfChanged($('validation'),", monitor)
        self.assertNotIn("if ($('genPercent')) $('genPercent').textContent =", monitor)
        self.assertNotIn("if ($('genRing')) $('genRing').style.setProperty('--progress'", monitor)
        self.assertNotIn("if ($('importBar')) $('importBar').style.width =", monitor)
        self.assertNotIn("if ($('previewProgress')) $('previewProgress').style.width =", monitor)



    def test_import_start_failure_and_terminal_states_keep_truthful_import_status(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function startImportPayload(")
        end = adapter.index("async function importBook(", start)
        import_flow = adapter[start:end]
        self.assertIn("Import could not start:", import_flow)
        self.assertIn("setStyleIfChanged($('importBar'), 'width', '0%')", import_flow)
        self.assertIn("catch (error)", import_flow)
        self.assertIn("const statusText = job.state === 'completed'", import_flow)
        self.assertIn("job.state === 'cancelled'", import_flow)
        self.assertIn("job.state === 'failed'", import_flow)
        self.assertIn("setTextIfChanged($('importStatus'), statusText)", import_flow)
        self.assertIn("setStyleIfChanged($('importBar'), 'width', '100%')", import_flow)

    def test_global_notifications_do_not_overwrite_import_or_hidden_voice_status(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("const message = (text, error = false) =>")
        end = adapter.index("const act =", start)
        helper = adapter[start:end]
        self.assertNotIn("const node = $('importStatus')", helper)
        self.assertNotIn("const validation = $('validation')", helper)
        self.assertIn("document.querySelector('.page.active #validation')", helper)
        self.assertIn("setTextIfChanged(activeValidation, text)", helper)
        self.assertIn("setTextIfChanged(toasts, text)", helper)
        # Import and preview workflows own their detailed status elements.
        self.assertIn("setTextIfChanged($('importStatus'), job.message || job.stage || job.state)", adapter)
        self.assertIn("setTextIfChanged($('validation'), 'Synthesizing preview", adapter)


    def test_chapter_refresh_treats_explicit_no_active_project_as_empty_state(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function refreshChapters()")
        end = adapter.index("async function refreshCharacters()", start)
        refresh = adapter[start:end]
        self.assertIn("let loaded;", refresh)
        self.assertIn("loaded = await call('chapter.list')", refresh)
        self.assertIn(
            "/open a local project from the Library first|active project is no longer available in the local library/i.test(detail)",
            refresh,
        )
        self.assertIn("loaded = [];", refresh)
        self.assertIn("data-chapter-empty-state", refresh)
        self.assertIn("No project selected. Import a book or open one from Library to begin.", refresh)
        self.assertIn("bridge/storage errors remain errors", refresh)

    def test_responsive_workflow_and_notifications_have_bounded_layout_guards(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Keep status notifications clear of the persistent mini-player")
        end = html.index("</style>", start)
        guard = html[start:end]
        self.assertIn("#toasts.toast-wrap", guard)
        self.assertIn("bottom:92px", guard)
        self.assertIn("max-height:min(42vh,320px)", guard)
        self.assertIn("@media(max-width:800px)", guard)
        self.assertIn("bottom:86px", guard)
        self.assertIn("@media(min-width:1181px) and (max-width:1366px)", guard)
        self.assertIn(".flow-track{", guard)
        self.assertIn("overflow-x:auto!important", guard)
        self.assertIn(".flow-stage{flex:0 0 132px!important}", guard)
        self.assertIn(".flow-summary{display:none!important}", guard)

    def test_premium_effects_bound_blur_and_disable_whole_view_entry_animations(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Release stability: reduce repeated whole-view paints")
        end = html.index("</style>", start)
        head_end = html.lower().index("</head>")
        guard = html[start:end]
        self.assertLess(start, head_end)
        self.assertGreaterEqual(start, html.rfind("<style>", 0, head_end))
        self.assertIn(".page.active", guard)
        self.assertIn("#voices>.content", guard)
        self.assertIn("#voices .panel.active", guard)
        self.assertIn(".char-view.active", guard)
        self.assertIn(".sound-view.active", guard)
        self.assertIn("animation:none!important", guard)
        self.assertIn("transform:none!important", guard)
        self.assertIn("backdrop-filter:blur(10px) saturate(125%)!important", guard)
        self.assertIn("backdrop-filter:blur(6px) saturate(115%)!important", guard)
        self.assertIn("backdrop-filter:blur(12px) saturate(125%)!important", guard)
        # High-effects mode also caps the unbounded workflow/loader blur layers;
        # users must not need to enable the Reduce Motion accessibility option.
        self.assertIn("html[data-effects='high'] .workflow,", guard)
        self.assertIn("html[data-effects='high'] .loader-glass", guard)
        self.assertIn("backdrop-filter:blur(8px) saturate(120%)!important", guard)
        self.assertIn("html[data-effects='normal'] .workflow", guard)
        self.assertIn("backdrop-filter:blur(5px) saturate(110%)!important", guard)
        self.assertIn("html[data-effects='normal'] .loader-glass", guard)
        self.assertIn("backdrop-filter:blur(4px) saturate(110%)!important", guard)
        self.assertIn("animation:none!important", guard)
        self.assertIn("transform:none!important", guard)
        self.assertIn(".production-flow{", guard)
        self.assertIn("backdrop-filter:none!important", guard)
        self.assertIn("@media(min-width:1181px) and (max-width:1366px)", guard)
        self.assertIn(".flow-track{", guard)
        self.assertIn("overflow-x:auto!important", guard)
        self.assertIn(".flow-stage{flex:0 0 132px!important}", guard)


    def test_notifications_are_bounded_and_do_not_overlap_the_mini_player(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Keep status notifications clear of the persistent mini-player")
        end = html.index("</style>", start)
        rules = html[start:end]
        for required in (
            "#toasts.toast-wrap",
            "bottom:92px",
            "bottom:86px",
            "max-height:min(42vh,320px)",
            "max-height:min(38vh,280px)",
            "overflow-wrap:anywhere",
            "pointer-events:none",
            "pointer-events:auto",
            "width:calc(100vw - 24px)",
        ):
            self.assertIn(required, rules)




if __name__ == "__main__":
    unittest.main()
