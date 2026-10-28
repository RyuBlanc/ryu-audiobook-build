"""Regression tests for the Premium V2 startup asset failure path."""
from pathlib import Path
import tempfile
import unittest

from app.ui.frontend_assets import FrontendAssetError, load_premium_v2_adapter


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
        self.assertIn("QTimer.singleShot(15000", install)

if __name__ == "__main__":
    unittest.main()
