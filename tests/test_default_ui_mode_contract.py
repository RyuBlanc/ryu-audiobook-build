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

    def test_native_qt_shell_remains_available_as_an_explicit_compatibility_mode(self):
        self.assertIn("RYU_UI_MODE=native", self.source)
        self.assertRegex(self.source, r"else:\s*\n\s*window = ProjectWorkflow\(\)")


if __name__ == "__main__":
    unittest.main()
