"""Ensure installed launches use the approved Premium V2 Dragon Studio UI."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"


class DefaultUiModeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_premium_v2_is_the_default_installed_interface(self):
        self.assertIn(
            'ui_mode = os.environ.get("RYU_UI_MODE", "premium-v2").strip().casefold()',
            self.source,
        )
        self.assertIn('if ui_mode == "native":', self.source)
        self.assertIn("from app.ui.premium_v2_host import PremiumV2Window, frontend_path", self.source)
        self.assertIn("window = PremiumV2Window()", self.source)


    def test_missing_premium_v2_asset_never_silently_launches_legacy_shell(self):
        mode_start = self.source.find('if ui_mode == "native":')
        self.assertGreaterEqual(mode_start, 0, "Native UI must require an explicit native mode.")
        mode_end = self.source.index("window.setWindowIcon(app_icon)", mode_start)
        mode_block = self.source[mode_start:mode_end]
        premium_start = mode_block.index(
            "from app.ui.premium_v2_host import PremiumV2Window, frontend_path"
        )
        premium_mode = mode_block[premium_start:]
        missing_start = premium_mode.index("if not premium_frontend.is_file():")
        premium_create = premium_mode.index("window = PremiumV2Window()", missing_start)
        missing_asset_path = premium_mode[missing_start:premium_create]
        self.assertIn("QMessageBox.critical(", missing_asset_path)
        self.assertIn("The older interface will not be loaded as a fallback.", missing_asset_path)
        self.assertIn("return 2", missing_asset_path)
        self.assertNotIn("ProjectWorkflow()", premium_mode)

    def test_native_qt_shell_remains_available_as_an_explicit_compatibility_mode(self):
        self.assertIn("RYU_UI_MODE=native", self.source)
        self.assertRegex(
            self.source,
            r'if ui_mode == "native":\s*\n\s*window = ProjectWorkflow\(\)',
        )
        self.assertNotRegex(self.source, r"else:\s*\n\s*window = ProjectWorkflow\(\)")

    def test_unrecognized_ui_mode_does_not_select_legacy_shell(self):
        mode_start = self.source.find('if ui_mode == "native":')
        self.assertGreaterEqual(mode_start, 0, "Only an explicit native mode may select the legacy shell.")
        mode_end = self.source.index("window.setWindowIcon(app_icon)", mode_start)
        mode_block = self.source[mode_start:mode_end]
        native_branch = mode_block.index('if ui_mode == "native":')
        premium_branch = mode_block.index(
            "from app.ui.premium_v2_host import PremiumV2Window, frontend_path"
        )
        self.assertGreater(premium_branch, native_branch)
        self.assertIn("window = PremiumV2Window()", mode_block[premium_branch:])
        self.assertNotIn("ProjectWorkflow()", mode_block[premium_branch:])


if __name__ == "__main__":
    unittest.main()
