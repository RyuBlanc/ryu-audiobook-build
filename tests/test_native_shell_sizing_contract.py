"""Desktop shell and user-controlled text/window sizing contracts."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NativeShellSizingContracts(unittest.TestCase):
    def test_embedded_window_blocks_chromium_zoom_and_uses_native_geometry(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("class StableQWebEngineView(QWebEngineView)", host)
        self.assertIn("def keyPressEvent(self, event)", host)
        self.assertIn("def wheelEvent(self, event)", host)
        self.assertIn("event.modifiers() & Qt.KeyboardModifier.ControlModifier", host)
        self.assertIn("self.web.setZoomFactor(1.0)", host)
        self.assertIn("def apply_window_size(self, choice: str)", host)
        self.assertIn("self.resize(max(640, width), max(480, height))", host)
        self.assertIn('"window_size": self.settings.value("ui/window_size", "auto")', host)
        self.assertIn('"text_scale": self.settings.value("ui/text_scale", 100)', host)

    def test_settings_exposes_persisted_text_scale_and_window_size_not_browser_zoom(self):
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        for token in ('id="uiTextScale"', 'id="uiWindowSize"', "UI text size", "Window size"):
            self.assertIn(token, html)
        self.assertIn("function applyUiTextScale(value)", adapter)
        self.assertIn("function installUiTextScaleRuntime()", adapter)
        self.assertIn("event.ctrlKey", adapter)
        self.assertIn("text_scale:Number($('uiTextScale')?.value||100)", adapter)
        self.assertIn("window_size:$('uiWindowSize')?.value||'auto'", adapter)
        self.assertIn('"text_scale": "ui/text_scale"', host)
        self.assertIn('"window_size": "ui/window_size"', host)

    def test_reduced_motion_is_a_saved_preference_and_disables_heavy_visual_effects(self):
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('id="reduceMotionAdvanced"', html)
        self.assertIn("reduce_motion:Boolean($('reduceMotionAdvanced')?.checked)", adapter)
        self.assertIn("function applyVisualStabilityPreferences(settings = {})", adapter)
        self.assertIn("backdrop-filter:none!important;", adapter)
        self.assertIn("transition-duration:0.01ms!important;", adapter)
        self.assertIn('"reduce_motion": self.settings.value("ui/reduce_motion", False, type=bool)', host)
        self.assertIn('if key == "reduce_motion" and not isinstance(value, bool):', host)

    def test_blank_interface_diagnostics_and_recovery_watchdog_are_wired(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "class DiagnosticQWebEnginePage(QWebEnginePage)",
            "def javaScriptConsoleMessage(",
            "def report_frontend_diagnostic(",
            "window.addEventListener('error'",
            "window.addEventListener('unhandledrejection'",
            "def _check_frontend_ready(",
            "def _finish_frontend_health_check(",
            "did not finish initializing",
        ):
            self.assertIn(token, host)
        self.assertIn("window.__ryuPremiumAdapterReady = true", adapter)
        self.assertIn("adapter-start-failed", adapter)

    def test_text_scaling_uses_one_css_scale_variable_and_skips_default_size_work(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function captureUiFontBaselines(root)", adapter)
        self.assertIn("function queueUiTextScaleBaselineCapture(node)", adapter)
        self.assertIn("const ryuUiScalePendingRoots = new Set()", adapter)
        self.assertIn("existing.contains(node)", adapter)
        self.assertIn("ryuUiScalePendingRoots.clear()", adapter)
        self.assertIn("if (ryuUiTextScale === 100 && !ryuUiTextBaselinesReady) return;", adapter)
        self.assertIn("root.style.setProperty('--ryu-ui-text-scale', String(ryuUiTextScale / 100))", adapter)
        self.assertIn("const scaleFactor = ryuUiTextScale !== 100", adapter)
        self.assertIn("const current = computed / scaleFactor;", adapter)
        self.assertIn("const skipTags = new Set(['SCRIPT','STYLE','LINK','META','NOSCRIPT','TEMPLATE','SVG','CANVAS','VIDEO','AUDIO'])", adapter)
        self.assertIn("font-size: calc(var(--ryu-base-font-px, 14px) * var(--ryu-ui-text-scale, 1)) !important;", adapter)
        self.assertIn("not hundreds of inline font mutations", adapter)
        self.assertNotIn("root.style.setProperty('font-size', (base * scale / 100)", adapter)
        self.assertIn("browser zoom shortcuts and Ctrl+mousewheel", adapter)

    def test_native_settings_controls_text_size_and_window_resolution(self):
        settings = (ROOT / "app/ui/settings_page.py").read_text(encoding="utf-8")
        workflow = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('self.text_scale = QComboBox()', settings)
        self.assertIn('self.settings.setValue("ui/text_scale"', settings)
        self.assertIn('self.settings.setValue("ui/window_size"', settings)
        self.assertIn('text_scale=text_scale', settings)
        self.assertIn('def apply_window_size(self, choice: str)', workflow)
        self.assertIn('ui/window_size', workflow)
        self.assertIn('saved_window_size', main)

    def test_native_voice_design_preview_does_not_initialize_long_form_anchor_bank(self):
        voice = (ROOT / "app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn('qwen_mode="design-preview"', voice)
        self.assertIn('one-pass preview', voice)
        self.assertNotIn('VoiceDesign preview and audiobook require the local Qwen Base model', voice)

    def test_character_studio_static_samples_are_removed_and_empty_states_are_real(self):
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for sample in ("Rimuru Tempest", "18 of 23 reviewed", "The eastern route is clear…", "324</b>"):
            self.assertNotIn(sample, html)
        self.assertIn("No Characters Found", html)
        self.assertIn("Loading the selected project", html)
        self.assertIn("function renderCharacterStudioLive()", adapter)
        self.assertIn("function renderDialogueReview()", adapter)
        self.assertIn("call('character.list')", adapter)
        self.assertIn("call('chapter.list')", adapter)
        self.assertIn("call('character.dialogue.suggestions.list')", adapter)


if __name__ == "__main__":
    unittest.main()
