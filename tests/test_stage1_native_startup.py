"""Stage 1 regression gates for the packaged Premium V2 startup path.

These tests guard the real desktop launch path, not only the HTML source
contracts. In particular, the approved HTML loader must remain visible while
the desktop bridge and required workspace hydration are pending.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class Stage1NativeStartupAcceptanceTests(unittest.TestCase):
    def test_hosted_html_holds_the_approved_html_loader_until_ready(self):
        from app.ui.frontend_assets import prepare_native_host_html

        source = (
            "<html><head><title>Ryu</title></head><body>"
            '<div id="appLoader"></div>'
            "<script>setTimeout(finish,1700);</script>"
            "</body></html>"
        )
        prepared = prepare_native_host_html(
            source,
            base_url="file:///C:/Program%20Files/Ryu/assets/frontend/",
        )

        self.assertIn(
            '<base href="file:///C:/Program%20Files/Ryu/assets/frontend/">',
            prepared,
        )
        self.assertIn("window.__ryuNativeHost = true;", prepared)
        self.assertIn(
            "if (!window.__ryuNativeHost) setTimeout(finish,1700);",
            prepared,
        )
        self.assertIn('<div id="appLoader"></div>', prepared)

    def test_native_host_base_url_is_escaped_and_loader_contract_is_required(self):
        from app.ui.frontend_assets import FrontendAssetError, prepare_native_host_html

        prepared = prepare_native_host_html(
            "<html><head></head><body></body></html>",
            base_url='file:///C:/Ryu & "Assets"/frontend/',
        )
        self.assertIn(
            '<base href="file:///C:/Ryu &amp; &quot;Assets&quot;/frontend/">',
            prepared,
        )
        with self.assertRaises(FrontendAssetError):
            prepare_native_host_html("<html><head></head><body></body></html>")

    def test_adapter_does_not_remove_html_loader_before_required_hydration(self):
        adapter = ADAPTER.read_text(encoding="utf-8")
        wire_start = adapter.index("async function wire()")
        wire_end = adapter.index("const start = () => wire()", wire_start)
        wire = adapter[wire_start:wire_end]
        loader_removal = wire.index("legacyLoader.remove()")
        required_hydration = wire.index(
            "await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters], {required:true})"
        )
        self.assertGreater(
            loader_removal,
            required_hydration,
            "The HTML loader must remain visible until required startup hydration has completed.",
        )
        self.assertGreater(
            loader_removal,
            wire.index("await call('app.get_info')"),
        )

    def test_native_host_shows_webengine_html_loader_during_bridge_setup(self):
        host = HOST.read_text(encoding="utf-8")
        install_start = host.index("def _install_bridge(self, ok: bool)")
        install_end = host.index("def _check_frontend_ready(", install_start)
        install = host[install_start:install_end]
        self.assertIn("self.web if self._uses_html_startup_loader else self._loading_page", install)
        self.assertIn('self._hosted_html_path = settings_root() / "frontend_cache" / path.name', host)
        self.assertIn("self._hosted_html_path.write_text(", host)
        self.assertIn("self._hosted_html_source, encoding=\"utf-8\"", host)
        self.assertIn("self.web.load(QUrl.fromLocalFile(str(self._hosted_html_path.resolve())))", host)
        self.assertIn("prepare_native_host_html(", host)
        self.assertNotIn("self.web.setHtml(", host)

    def test_bridge_iife_uses_the_exported_diagnostic_emitter(self):
        host = HOST.read_text(encoding="utf-8")
        bridge_start = host.index("const bridgeStartedAt = Date.now()")
        bridge_end = host.index("const waitForTransport = () =>", bridge_start)
        bridge = host[bridge_start:bridge_end]
        self.assertIn("const emit = window.__ryuEmitFrontendDiagnostic;", host)
        self.assertIn("emit('startup-progress'", bridge)
        self.assertIn("window.dispatchEvent(new CustomEvent('ryu-backend-ready'))", bridge)
        self.assertLess(
            bridge.index("emit('startup-progress'"),
            bridge.index("window.dispatchEvent(new CustomEvent('ryu-backend-ready'))"),
        )

    def test_webchannel_handshake_retries_and_reports_failure_instead_of_hanging(self):
        host = HOST.read_text(encoding="utf-8")
        self.assertIn("backend-bridge-failed", host)
        self.assertIn("bridgeStartedAt", host)
        self.assertIn("window.setTimeout(waitForTransport, 100)", host)
        self.assertIn("script.onerror", host)
        self.assertIn("window.__ryuBridgeFailureReason = String(", host)
        self.assertIn("def _finish_bridge_connect_timeout(", host)
        self.assertIn("performance.getEntriesByType('resource')", host)
        self.assertIn("Qt WebChannel handshake diagnostics:", host)
        self.assertIn('kind in {"backend-bridge-failed", "adapter-start-failed"}', host)

    def test_startup_smoke_marker_records_real_frontend_ready_or_failure(self):
        host = HOST.read_text(encoding="utf-8")
        self.assertIn("RYU_STARTUP_SMOKE_MARKER", host)
        self.assertIn("def _write_startup_smoke_marker(", host)
        ready_start = host.index("def _on_frontend_ready(")
        ready_end = host.index("def _retry_web_renderer(", ready_start)
        self.assertIn('self._write_startup_smoke_marker("ready")', host[ready_start:ready_end])
        failure_start = host.index("def _show_web_failure(")
        failure_end = host.index("def _set_loading_status(", failure_start)
        self.assertIn('self._write_startup_smoke_marker("failed"', host[failure_start:failure_end])

    def test_windows_smoke_waits_for_frontend_ready_instead_of_only_process_liveness(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("RYU_STARTUP_SMOKE_MARKER", workflow)
        self.assertIn("startup smoke did not reach Premium V2 readiness", workflow)
        self.assertIn("The Premium V2 startup smoke reported failure", workflow)
        self.assertNotIn("Start-Sleep -Seconds 12", workflow)


if __name__ == "__main__":
    unittest.main()
