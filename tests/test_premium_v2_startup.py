"""Startup guard for the approved Premium V2 Dragon Studio interface."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, sentinel

import app.main as application


ROOT = Path(__file__).resolve().parents[1]


class PremiumV2StartupTests(unittest.TestCase):
    def test_default_launch_uses_premium_v2_when_frontend_is_present(self):
        with TemporaryDirectory() as temporary:
            frontend = Path(temporary) / "ryu_audiobook_premium_v2.html"
            frontend.write_text("<!doctype html><title>Premium V2</title>", encoding="utf-8")
            with patch.dict(os.environ):
                os.environ.pop("RYU_UI_MODE", None)
                with (
                    patch("app.ui.premium_v2_host.frontend_path", return_value=frontend),
                    patch("app.ui.premium_v2_host.PremiumV2Window", return_value=sentinel.premium_window) as premium_window,
                    patch("app.main.ProjectWorkflow") as native_window,
                ):
                    selected = application.create_main_window()
            self.assertIs(selected, sentinel.premium_window)
            premium_window.assert_called_once_with()
            native_window.assert_not_called()

    def test_missing_premium_v2_frontend_fails_closed_instead_of_opening_old_ui(self):
        with TemporaryDirectory() as temporary:
            missing_frontend = Path(temporary) / "missing" / "ryu_audiobook_premium_v2.html"
            with (
                patch("app.ui.premium_v2_host.frontend_path", return_value=missing_frontend),
                patch("app.ui.premium_v2_host.PremiumV2Window") as premium_window,
                patch("app.main.ProjectWorkflow") as native_window,
            ):
                with self.assertRaisesRegex(FileNotFoundError, "will not fall back to the older native interface"):
                    application.create_main_window("premium-v2")
            premium_window.assert_not_called()
            native_window.assert_not_called()

    def test_native_compatibility_shell_requires_explicit_mode(self):
        with patch("app.main.ProjectWorkflow", return_value=sentinel.native_window) as native_window:
            selected = application.create_main_window("native")
        self.assertIs(selected, sentinel.native_window)
        native_window.assert_called_once_with()

    def test_unknown_mode_is_rejected_instead_of_defaulting_to_native_ui(self):
        with patch("app.main.ProjectWorkflow") as native_window:
            with self.assertRaisesRegex(ValueError, "Unsupported RYU_UI_MODE"):
                application.create_main_window("premium-v2-old")
        native_window.assert_not_called()

    def test_build_explicitly_packages_the_premium_v2_html_and_backend_adapter(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("ryu_audiobook_premium_v2.html", build_script)
        self.assertIn("premium_v2_backend_adapter.js", build_script)
        self.assertIn("Frozen package is missing the Premium V2 Dragon Studio HTML frontend", workflow)
        self.assertIn("Packaged Premium V2 asset differs from source", workflow)


if __name__ == "__main__":
    unittest.main()
