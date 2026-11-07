from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage8WindowsInstallerContractTests(unittest.TestCase):
    def test_html_installer_reports_native_bridge_startup_for_packaged_acceptance(self):
        source = (ROOT / "installer" / "html_installer.py").read_text(encoding="utf-8")
        script = (ROOT / "installer" / "ryu_installer.js").read_text(encoding="utf-8")
        self.assertIn("RYU_INSTALLER_STARTUP_SMOKE_MARKER", source)
        self.assertIn("QTimer.singleShot(100, self._probe_startup_smoke_bridge)", source)
        self.assertIn("window.__ryuInstallerBridgeReady = false", script)
        self.assertIn("window.__ryuInstallerBridgeReady=true", script)

    def test_windows_release_workflow_installs_upgrades_launches_and_uninstalls_core_installer(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("Verify functional HTML installer UI startup", workflow)
        self.assertIn("Install, launch, upgrade and uninstall Windows installer", workflow)
        for required in (
            "RYU_INSTALLER_STARTUP_SMOKE_MARKER",
            "RYU_FROZEN_SELF_TEST_MARKER",
            "RYU_STARTUP_SMOKE_MARKER",
            "unins000.exe",
            "preserve-on-uninstall.txt",
            "Build\\s+",
            "/VERYSILENT",
        ):
            self.assertIn(required, workflow)


if __name__ == "__main__":
    unittest.main()
