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
        self.assertIn('if ui_mode in {"premium-v2", "html", "web"}:', self.source)
        self.assertIn("window = PremiumV2Window()", self.source)


    def test_missing_premium_v2_asset_never_silently_launches_legacy_shell(self):
        mode_start = self.source.index(
            'if ui_mode in {"premium-v2", "html", "web"}:'
        )
        mode_end = self.source.index("window.setWindowIcon(app_icon)", mode_start)
        mode_block = self.source[mode_start:mode_end]
        missing_start = mode_block.index("if not premium_frontend.is_file():")
        premium_create = mode_block.index("window = PremiumV2Window()", missing_start)
        missing_asset_path = mode_block[missing_start:premium_create]
        self.assertIn("QMessageBox.critical(", missing_asset_path)
        self.assertIn("The older interface will not be loaded as a fallback.", missing_asset_path)
        self.assertIn("return 2", missing_asset_path)
        self.assertNotIn("ProjectWorkflow()", missing_asset_path)

    def test_native_qt_shell_remains_available_as_an_explicit_compatibility_mode(self):
        self.assertIn("RYU_UI_MODE=native", self.source)
        self.assertRegex(self.source, r"else:\s*\n\s*window = ProjectWorkflow\(\)")


if __name__ == "__main__":
    unittest.main()
