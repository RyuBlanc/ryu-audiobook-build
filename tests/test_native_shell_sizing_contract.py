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
        self.assertIn("self.resize(max(min_width, width), max(min_height, height))", host)
        self.assertIn('"window_size": self.settings.value("ui/window_size", "auto")', host)
        self.assertIn('"text_scale": self.settings.value("ui/text_scale", 100)', host)


    def test_premium_v2_is_default_and_native_shell_is_explicit_compatibility_mode(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        before_main = main[:main.index("def main()")]
        self.assertNotIn("from app.ui.premium_v2_host import", before_main)
        self.assertIn('os.environ.get("RYU_UI_MODE", "premium-v2")', main)
        self.assertIn('if ui_mode in {"premium-v2", "html", "web"}:', main)
        self.assertIn("window = PremiumV2Window()", main)
        self.assertIn("window = ProjectWorkflow()", main)

    def test_native_window_applies_saved_size_before_first_display(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        main_body = main[main.index("def main()"):]
        first_display = main_body.index("window.show()")
        self.assertLess(main_body.index("saved_window_size ="), first_display)
        self.assertLess(main_body.rindex("apply_size(saved_window_size)"), first_display)
        self.assertNotIn("window.show()\n    saved_window_size =", main_body)

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



    def test_native_host_rejects_missing_or_empty_adapter_before_injection(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        helper = (ROOT / "app/ui/frontend_assets.py").read_text(encoding="utf-8")
        start = host.index("    def _install_bridge(self, ok: bool)")
        end = host.index("    def _check_frontend_ready(", start)
        install = host[start:end]
        self.assertIn("load_premium_v2_adapter(adapter_path)", install)
        self.assertIn("except FrontendAssetError as exc:", install)
        self.assertIn("self._show_web_failure(message)", install)
        self.assertIn("script += \"\\n\" + adapter_source", install)
        self.assertLess(install.index("return", install.index("except FrontendAssetError")), install.index("self.web.page().runJavaScript(script)"))
        self.assertIn("if not target.is_file():", helper)
        self.assertIn("if not source.strip():", helper)
        self.assertIn("except (OSError, UnicodeError) as exc:", helper)


    def test_frontend_watchdog_reads_adapter_failure_details(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        check_start = host.index("def _check_frontend_ready(")
        check_end = host.index("def _finish_frontend_health_check(", check_start)
        check = host[check_start:check_end]
        self.assertIn("error:String(window.__ryuPremiumAdapterFailure || '').slice(0,1000)", check)
        finish = host[check_end:]
        self.assertIn("startup_error = (", finish)
        self.assertIn("if startup_error:", finish)
        self.assertIn("Your local project files have not been deleted. Details: ", finish)

    def test_native_loading_surface_stays_visible_until_backend_frontend_ready(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('self._web_stack.setCurrentWidget(self._loading_page)', host)
        self.assertIn('def _on_frontend_ready(self)', host)
        self.assertIn('reveal = getattr(window, "_on_frontend_ready", None)', host)
        self.assertIn('def _set_loading_status(self, message: str)', host)
        self.assertIn('Retrying the interface and reconnecting local services', host)
        self.assertIn('await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters]);', adapter)
        self.assertNotIn('self._web_stack.setCurrentWidget(self.web)\n        self.web.reload()', host)

    def test_window_minimum_size_is_bounded_by_the_available_screen(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        native = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        for source in (host, native):
            self.assertIn('min_width = max(1, min(960, int(available.width())))', source)
            self.assertIn('min_height = max(1, min(620, int(available.height())))', source)
            self.assertIn('self.setMinimumSize(min_width, min_height)', source)

    def test_catalog_backed_pages_defer_disk_scans_until_navigation(self):
        page_specs = (
            ("app/ui/dashboard_page.py", "DashboardPage", "self.refresh()"),
            ("app/ui/library.py", "LibraryPage", "self.refresh()"),
            ("app/ui/history_page.py", "HistoryPage", "self.refresh()"),
            ("app/ui/models_page.py", "ModelsPage", "self.refresh()"),
            ("app/ui/hardware_page.py", "HardwarePage", "self.refresh()"),
            ("app/ui/character_library.py", "CharacterLibraryPage", "self.refresh()"),
            ("app/ui/audiobooks_page.py", "AudiobooksPage", "self.refresh()"),
            ("app/ui/voice_cast_page.py", "VoiceCastPage", "self.load_current_project()"),
        )
        for relative_path, class_name, forbidden in page_specs:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            class_start = source.index(f"class {class_name}")
            class_end = source.find("\nclass ", class_start + 1)
            if class_end < 0:
                class_end = len(source)
            class_source = source[class_start:class_end]
            init_start = class_source.index("    def __init__(")
            init_end = class_source.find("\n    def ", init_start + 1)
            constructor = class_source[init_start:init_end if init_end >= 0 else None]
            self.assertNotIn(forbidden, constructor, f"{relative_path} still scans during construction")
            if class_name == "VoiceCastPage":
                self.assertNotIn("self.refresh_profiles()", constructor)

        hardware_source = (ROOT / "app/ui/hardware_page.py").read_text(encoding="utf-8")
        hardware_start = hardware_source.index("class HardwarePage")
        hardware_end = hardware_source.find("\nclass ", hardware_start + 1)
        hardware_class = hardware_source[hardware_start:hardware_end if hardware_end >= 0 else None]
        hardware_init_start = hardware_class.index("    def __init__(")
        hardware_init_end = hardware_class.index("\n    def refresh(", hardware_init_start)
        hardware_init = hardware_class[hardware_init_start:hardware_init_end]
        self.assertNotIn("detect_hardware()", hardware_init)

        workflow = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("def _schedule_visible_refresh(self, widget: QWidget, refresh, context: str)", workflow)
        self.assertIn("QTimer.singleShot(75, run_refresh)", workflow)
        self.assertIn("if self.stack.currentWidget() is not widget:", workflow)
        for token in (
            "self.dashboard, self.dashboard.refresh",
            "self.library, self.library.refresh",
            "self.character_library_page,",
            "self.audiobooks_page, self.audiobooks_page.refresh",
            "self.history_page, self.history_page.refresh",
            "self.models_page, self.models_page.refresh",
            "self.hardware_page, self.hardware_page.refresh",
        ):
            self.assertIn(token, workflow)

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
        self.assertIn('text_scale=int(self.text_scale.currentData() or 100)', settings)
        self.assertIn('scale=int(self.interface_scale.currentData() or 100)', settings)
        self.assertIn('def apply_window_size(self, choice: str)', workflow)
        # Geometry persistence is owned by SettingsPage; the shell exposes
        # the handler that applies the already-saved value.
        self.assertIn('def apply_window_size(self, choice: str)', workflow)
        self.assertIn('saved_window_size', main)
        settings_saved_start = workflow.index("    def _settings_saved(")
        settings_saved_end = workflow.index("    def resizeEvent(", settings_saved_start)
        settings_saved = workflow[settings_saved_start:settings_saved_end]
        # Window geometry is applied once by SettingsPage after saving. Reapplying
        # it inside the reduced-motion callback caused duplicate resize events.
        self.assertNotIn("self.apply_window_size(", settings_saved)
        self.assertIn("apply_size(window_size)", settings)

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
