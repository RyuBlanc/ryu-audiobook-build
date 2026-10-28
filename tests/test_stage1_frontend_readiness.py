"""Regression tests for the Premium V2 startup asset failure path."""
from pathlib import Path
import tempfile
import unittest

from app.ui.frontend_assets import (
    FrontendAssetError,
    load_premium_v2_adapter,
    premium_v2_logo_candidates,
)


ROOT = Path(__file__).resolve().parents[1]


class PremiumV2FrontendAssetTests(unittest.TestCase):
    def test_missing_adapter_fails_closed_with_exact_missing_path(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "premium_v2_backend_adapter.js"
            with self.assertRaisesRegex(FrontendAssetError, "adapter is missing") as raised:
                load_premium_v2_adapter(missing)
            self.assertIn(str(missing), str(raised.exception))

    def test_empty_adapter_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "premium_v2_backend_adapter.js"
            empty.write_text("  \n\t", encoding="utf-8")
            with self.assertRaisesRegex(FrontendAssetError, "adapter is empty"):
                load_premium_v2_adapter(empty)

    def test_non_utf8_adapter_fails_closed_with_read_error(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "premium_v2_backend_adapter.js"
            invalid.write_bytes(b"\xff\xfe\xfa")
            with self.assertRaisesRegex(FrontendAssetError, "could not be read"):
                load_premium_v2_adapter(invalid)

    def test_valid_adapter_is_returned_without_rewriting_content(self):
        expected = "window.__ryuPremiumAdapterReady = false;\n// verified test adapter\n"
        with tempfile.TemporaryDirectory() as temp:
            valid = Path(temp) / "premium_v2_backend_adapter.js"
            valid.write_text(expected, encoding="utf-8")
            self.assertEqual(load_premium_v2_adapter(valid), expected)


    def test_required_startup_hydration_fails_closed_without_blocking_optional_panels(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        helper_start = adapter.index("const hydratePhase = async (phase, options = {})")
        helper_end = adapter.index("await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters]", helper_start)
        helper = adapter[helper_start:helper_end]
        self.assertIn("const required = options.required === true", helper)
        self.assertIn("if (required)", helper)
        self.assertIn("Required Premium V2 startup hydration failed in", helper)
        self.assertIn("await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters], {required:true})", adapter)
        self.assertIn("await hydratePhase([refreshCharacters, refreshCharacterLibrary, refreshTerms])", adapter)
        self.assertIn("await hydratePhase([refreshSounds, refreshSoundCues, refreshChapterBgm])", adapter)
        self.assertIn("await hydratePhase([refreshJobs, refreshHistory, refreshModels])", adapter)
        self.assertIn("window.__ryuPremiumAdapterFailure = String(", adapter)
        self.assertLess(
            adapter.index("await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters], {required:true})"),
            adapter.index("window.__ryuPremiumAdapterReady = true;"),
        )

    def test_startup_watchdog_shows_the_required_hydration_failure_detail(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        check_start = host.index("def _check_frontend_ready(")
        check_end = host.index("def _finish_frontend_health_check(", check_start)
        check = host[check_start:check_end]
        self.assertIn("error:String(window.__ryuPremiumAdapterFailure || '').slice(0,1000)", check)
        finish_start = host.index("def _finish_frontend_health_check(")
        finish = host[finish_start:]
        self.assertIn('startup_error = (', finish)
        self.assertIn('if startup_error:', finish)
        self.assertIn("Your local project files have not been deleted. Details: ", finish)
        self.assertIn("self._show_web_failure(", finish)


    def test_adapter_start_failure_shows_native_recovery_surface_immediately(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("def report_frontend_diagnostic(")
        end = host.index("def _settings_get(", start)
        diagnostic = host[start:end]
        self.assertIn('if kind == "adapter-start-failed":', diagnostic)
        self.assertIn('show_failure = getattr(window, "_show_web_failure", None)', diagnostic)
        self.assertIn("show_failure(", diagnostic)
        self.assertIn('if callable(show_failure) and not getattr(window, "_frontend_ready", False):', diagnostic)
        self.assertIn("The Premium V2 interface could not complete startup.", diagnostic)

        show_start = host.index("def _show_web_failure(self, message: str)")
        show_end = host.index("def _set_loading_status(", show_start)
        self.assertIn("self._frontend_failure_shown = True", host[show_start:show_end])
        self.assertIn("or self._frontend_failure_shown", host[host.index("def _check_frontend_ready("):host.index("def _finish_frontend_health_check(")])
        self.assertIn("self._frontend_failure_shown = False", host[host.index("def _retry_web_renderer("):host.index("def _handle_renderer_terminated(")])


    def test_native_loading_screen_uses_the_real_bundled_logo_and_progress_bar(self):
        frontend_html = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        candidates = premium_v2_logo_candidates(frontend_html)
        self.assertEqual(candidates[0].name, "ryu_audiobook_logo.png")
        self.assertEqual(candidates[1].name, "ryu_audiobook_logo.svg")
        self.assertEqual(candidates[-1].name, "ryu_audiobook_logo_master.png")
        self.assertTrue(
            any(path.is_file() and path.stat().st_size > 0 for path in candidates),
            f"No real application logo asset found in: {candidates}",
        )

        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        window_start = host.index("class PremiumV2Window(")
        window_end = host.index("    def apply_window_size(", window_start)
        window = host[window_start:window_end]
        self.assertIn('self._loading_page.setObjectName("startupLoadingPage")', window)
        self.assertIn('self._loading_logo.setObjectName("startupLogo")', window)
        self.assertIn("premium_v2_logo_candidates(path)", window)
        self.assertIn("QPixmap(str(logo_path))", window)
        self.assertIn("self._loading_logo.setPixmap(", window)
        self.assertIn('self._loading_progress = QProgressBar(self._loading_page)', window)
        self.assertIn('self._loading_progress.setObjectName("startupProgress")', window)
        self.assertIn('self._loading_progress.setFormat("%p%")', window)
        self.assertIn("self._update_startup_progress", window)


    def test_startup_percentage_order_matches_real_bridge_milestones(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        install_start = host.index("    def _install_bridge(self, ok: bool)")
        install_end = host.index("    def _check_frontend_ready(", install_start)
        install = host[install_start:install_end]
        # The 26% notification is inside injected JavaScript and only runs after
        # runJavaScript executes; compare host call order separately from JS callback order.
        self.assertLess(
            install.index('self._update_startup_progress("Preparing the local backend bridge…", 22)'),
            install.index("self.web.page().runJavaScript(script)"),
        )
        self.assertLess(
            install.index("self.web.page().runJavaScript(script)"),
            install.index("self._frontend_watchdog.start(120000)"),
        )
        self.assertLess(
            install.index("progress:26"),
            install.index("window.dispatchEvent(new CustomEvent('ryu-backend-ready'))"),
        )
        self.assertIn("self._update_startup_progress(\"Premium V2 interface loaded. Connecting to local services…\", 18)", install)

    def test_startup_progress_diagnostics_update_native_status_monotonically(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        diagnostic_start = host.index("def report_frontend_diagnostic(")
        diagnostic_end = host.index("def _settings_get(", diagnostic_start)
        diagnostic = host[diagnostic_start:diagnostic_end]
        self.assertIn('if kind == "startup-progress":', diagnostic)
        self.assertIn('update = getattr(window, "_update_startup_progress", None)', diagnostic)

        updater_start = host.index("def _update_startup_progress(")
        updater_end = host.index("def _on_frontend_ready(", updater_start)
        updater = host[updater_start:updater_end]
        self.assertIn("self._set_loading_status(message)", updater)
        self.assertIn("self._startup_progress_value = max(self._startup_progress_value, value)", updater)
        self.assertIn("self._loading_progress.setValue(self._startup_progress_value)", updater)
        self.assertIn("self._loading_progress.setRange(0, 0)", updater)
        self.assertIn("self._loading_progress.setRange(0, 100)", updater)
        self.assertIn("self._frontend_watchdog.start(120000)", updater)



    def test_native_live_splash_removes_duplicate_timer_driven_html_loader_before_backend_calls(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="appLoader"', html)
        self.assertIn("setTimeout(finish,1700)", html)

        wire_start = adapter.index("async function wire()")
        first_backend_call = adapter.index("await call('app.get_info')", wire_start)
        startup = adapter[wire_start:first_backend_call]
        self.assertIn("const legacyLoader = $('appLoader')", startup)
        self.assertIn("if (legacyLoader) legacyLoader.remove()", startup)
        self.assertLess(
            startup.index("legacyLoader.remove()"),
            startup.index("window.__ryuEmitFrontendDiagnostic?.('startup-progress'"),
        )
        self.assertLess(
            startup.index("legacyLoader.remove()"),
            adapter.index("await call('app.get_info')", wire_start),
        )

    def test_loading_stays_live_during_early_adapter_wiring(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function wire()")
        controls = adapter.index("installUiTextScaleRuntime()", start)
        first_backend_call = adapter.index("await call('app.get_info')", start)
        early_setup = adapter[start:first_backend_call]
        self.assertIn("window.__ryuEmitFrontendDiagnostic?.('startup-progress'", early_setup)
        self.assertIn("message:'Preparing studio controls and local services…'", early_setup)
        self.assertIn("progress:null", early_setup)
        self.assertLess(early_setup.index("progress:null"), early_setup.index("installUiTextScaleRuntime()"))
        self.assertLess(controls, first_backend_call)

    def test_startup_progress_reports_real_required_hydration_milestones(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        milestones_start = adapter.index("const startupMilestones = {")
        milestones_end = adapter.index("const reportStartupProgress =", milestones_start)
        milestones = adapter[milestones_start:milestones_end]
        for label in (
            "Loading saved settings",
            "Loading your local project library",
            "Loading saved voice profiles",
            "Restoring the chapter workspace",
        ):
            self.assertIn(label, milestones)
        phase_start = adapter.index("const hydratePhase = async (phase, options = {})")
        phase_end = adapter.index("await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters], {required:true})", phase_start)
        phase = adapter[phase_start:phase_end]
        self.assertIn("if (milestone) reportStartupProgress(milestone.loading, null)", phase)
        self.assertIn("await refresh()", phase)
        self.assertIn("if (milestone) reportStartupProgress(milestone.loaded, milestone.complete)", phase)
        self.assertIn("reportStartupProgress('Essential workspace loaded. Finishing the studio…', 94)", adapter)
        self.assertIn("window.__ryuEmitFrontendDiagnostic?.('startup-progress'", adapter)

    def test_native_bridge_diagnostic_carries_bounded_progress(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("const emit = (kind, details = {}) =>")
        end = host.index("window.__ryuEmitFrontendDiagnostic = emit;", start)
        bridge = host[start:end]
        self.assertIn("details.progress === undefined || details.progress === null", bridge)
        self.assertIn("Math.max(0, Math.min(100, Math.round(Number(details.progress))))", bridge)
        self.assertIn("emit('startup-progress'", host)
        self.assertIn("progress:26", host)


    def test_startup_watchdog_is_inactivity_based_and_stops_on_ready_or_failure(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        init_start = host.index("class PremiumV2Window(")
        init_end = host.index("    def apply_window_size(", init_start)
        constructor = host[init_start:init_end]
        self.assertIn("self._frontend_watchdog = QTimer(self)", constructor)
        self.assertIn("self._frontend_watchdog.setSingleShot(True)", constructor)
        self.assertIn("lambda: self._check_frontend_ready(self._frontend_generation)", constructor)

        updater_start = host.index("def _update_startup_progress(")
        updater_end = host.index("def _on_frontend_ready(", updater_start)
        updater = host[updater_start:updater_end]
        self.assertIn("self._frontend_watchdog.start(120000)", updater)
        self.assertIn("if self._frontend_generation > 0", updater)
        ready_start = host.index("def _on_frontend_ready(")
        ready_end = host.index("def _retry_web_renderer(", ready_start)
        self.assertIn("self._frontend_watchdog.stop()", host[ready_start:ready_end])
        failure_start = host.index("def _show_web_failure(")
        failure_end = host.index("def _set_loading_status(", failure_start)
        self.assertIn("self._frontend_watchdog.stop()", host[failure_start:failure_end])
        self.assertNotIn("QTimer.singleShot(15000", host)

    def test_native_host_fails_before_javascript_injection_when_adapter_cannot_load(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _install_bridge(self, ok: bool)")
        end = host.index("    def _check_frontend_ready(", start)
        install = host[start:end]
        self.assertIn("load_premium_v2_adapter(adapter_path)", install)
        self.assertIn("except FrontendAssetError as exc:", install)
        self.assertIn("self._show_web_failure(message)", install)
        self.assertLess(
            install.index("self._show_web_failure(message)"),
            install.index("self.web.page().runJavaScript(script)"),
        )
        self.assertIn('"could not be read. The application will not continue in a "', install)
        self.assertIn('"partially connected state. Repair or reinstall the application.', install)
        self.assertIn("self._frontend_watchdog.start(120000)", install)

if __name__ == "__main__":
    unittest.main()
