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


    def test_every_project_open_route_uses_one_draft_safe_transition(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function openProjectWithPreservedDraft(folder)")
        end = adapter.index("// Dashboard recent cards are re-rendered", start)
        transition = adapter[start:end]
        self.assertLess(
            transition.index("await flushChapterDraftBeforeSwitch()"),
            transition.index("call('project.open', {folder:targetFolder})"),
        )
        for required in (
            "chapterListEpoch++",
            "chapterSelectionEpoch++",
            "characterListEpoch++",
            "characterSuggestionsEpoch++",
            "await refreshCurrentProjectCard()",
            "String(active.folder || '') !== targetFolder",
            "await refreshProjects()",
            "await refreshChapters()",
            "await refreshCharacters()",
        ):
            self.assertIn(required, transition)

        for route in (
            "openProjectWithPreservedDraft(c.source_project_folder)",
            "openProjectWithPreservedDraft(folder)",
            "openProjectWithPreservedDraft(button.dataset.openProject)",
            "openProjectWithPreservedDraft(recentProject.dataset.projectFolder)",
            "openProjectWithPreservedDraft(candidate.folder)",
        ):
            self.assertIn(route, adapter)
        self.assertEqual(adapter.count("call('project.open'"), 1)

    def test_project_open_does_not_start_a_racing_fire_and_forget_active_refresh(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("const call = async (command, payload = {}) =>")
        end = adapter.index("const esc =", start)
        bridge_call = adapter[start:end]
        self.assertNotIn("command === 'project.open'", bridge_call)
        self.assertIn("if (command === 'project.rename')", bridge_call)
        start = adapter.index("async function openProjectWithPreservedDraft(folder)")
        end = adapter.index("// Dashboard recent cards are re-rendered", start)
        self.assertIn("await refreshCurrentProjectCard()", adapter[start:end])

    def test_project_switch_flushes_pending_chapter_edits_before_open(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function openProjectWithPreservedDraft(folder)")
        end = adapter.index("// Dashboard recent cards are re-rendered", start)
        transition = adapter[start:end]
        self.assertLess(
            transition.index("await flushChapterDraftBeforeSwitch()"),
            transition.index("call('project.open', {folder:targetFolder})"),
        )
        self.assertIn("await refreshCurrentProjectCard()", transition)
        self.assertIn("await refreshChapters()", transition)
        self.assertIn("await refreshCharacters()", transition)

    def test_project_switch_waits_for_a_stable_chapter_draft_and_stops_on_churn(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function flushChapterDraftBeforeSwitch()")
        end = adapter.index("function chapterDeleteSelection()", start)
        flush = adapter[start:end]
        self.assertIn("for (let attempt = 0; attempt < 5; attempt++)", flush)
        self.assertIn("let previousSaveFailed = false", flush)
        self.assertIn("const hasUnsavedDraft = text !== savedText || title !== savedTitle", flush)
        self.assertIn("previousSaveFailed || chapterSaveTimer || hasUnsavedDraft || saveStateNeedsRetry", flush)
        self.assertIn("await saveTask", flush)
        self.assertIn("The chapter kept changing while it was being saved.", flush)
        self.assertIn("The project switch was stopped to protect your edits", flush)
        self.assertIn("if (Number(window.ryuPremiumSelectedChapter || 0) !== number) continue;", flush)
        self.assertLess(flush.index("await chapterSavePromise"), flush.index("const text = String(editor.value"))
        self.assertIn("throw error", flush)

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


    def test_saved_theme_effects_and_motion_are_applied_to_the_document_root(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("function applyVisualStabilityPreferences(")
        end = adapter.index("const call =", start)
        prefs = adapter[start:end]
        self.assertIn("settings.theme", prefs)
        self.assertIn("root.dataset.theme !== theme", prefs)
        self.assertIn("root.dataset.theme = theme", prefs)
        self.assertIn("settings.effects", prefs)
        self.assertIn("root.dataset.effects !== effects", prefs)
        self.assertIn("root.dataset.effects = effects", prefs)
        self.assertIn("root.dataset.ryuReduceMotion = reduce ? '1' : '0'", prefs)

    def test_high_effects_remain_enabled_with_bounded_blur_and_safe_toast_layout(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Stage 1 stability: bounded glass effects")
        end = html.index("</style>", start)
        guard = html[start:end]
        self.assertIn("html[data-effects='high'] .production-flow", guard)
        self.assertIn("blur(12px) saturate(125%)", guard)
        self.assertIn("html[data-effects='high'] .card", guard)
        self.assertIn("blur(8px) saturate(115%)", guard)
        self.assertIn("filter: blur(16px)", guard)
        self.assertIn("max-height:min(42vh,320px)", guard)
        self.assertIn("body.ryu-mini-player-visible .toast-wrap { bottom:96px; }", guard)
        self.assertIn("@media(max-width:800px)", guard)
        self.assertIn("body.ryu-mini-player-visible .toast-wrap { bottom:86px; }", guard)


    def test_high_effects_page_transitions_do_not_translate_or_scale_large_containers(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Stage 1 stability: bounded glass effects")
        end = html.index("</style>", start)
        guard = html[start:end]
        rule_start = guard.index("html[data-effects='high'] .page.active")
        rule_end = guard.index("@keyframes stage1HighEffectsReveal", rule_start)
        reveal_rule = guard[rule_start:rule_end]
        self.assertIn("#voices>.content", reveal_rule)
        self.assertIn("#voices .panel.active", reveal_rule)
        self.assertIn("animation: stage1HighEffectsReveal 140ms ease-out both !important", reveal_rule)
        self.assertNotIn("translate", reveal_rule)
        self.assertNotIn("scale(", reveal_rule)
        keyframes = guard[rule_end:]
        self.assertIn("from { opacity: .94; }", keyframes)
        self.assertIn("to { opacity: 1; }", keyframes)

    def test_workflow_strip_and_voice_status_blurs_are_bounded_in_both_effect_modes(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Stage 1 stability: bounded glass effects")
        end = html.index("</style>", start)
        guard = html[start:end]
        self.assertIn("html[data-effects='high'] .workflow-strip", guard)
        self.assertIn("html[data-effects='high'] #voices .status", guard)
        self.assertIn("html[data-effects='normal'] .workflow-strip", guard)
        self.assertIn("html[data-effects='normal'] #voices .status", guard)
        high_workflow = guard[guard.index("html[data-effects='high'] .workflow-strip"):guard.index("html[data-effects='high'] #voices .status")]
        high_voice = guard[guard.index("html[data-effects='high'] #voices .status"):guard.index("html[data-effects='normal'] .workflow-strip")]
        normal = guard[guard.index("html[data-effects='normal'] .workflow-strip"):guard.index(".loader-glass")]
        self.assertIn("blur(12px) saturate(125%) !important", high_workflow)
        self.assertIn("blur(8px) saturate(115%) !important", high_voice)
        self.assertIn("blur(4px) saturate(110%) !important", normal)

    def test_mini_player_visibility_toggles_notification_safe_area(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("function syncMiniPlayer()")
        end = adapter.index("function dashboardPageActive()", start)
        sync = adapter[start:end]
        self.assertIn("const visible = Boolean(playerAudio && playerAudio.src", sync)
        self.assertIn("ryu-mini-player-visible", sync)
        self.assertIn("body.classList.toggle('ryu-mini-player-visible', visible)", sync)

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
