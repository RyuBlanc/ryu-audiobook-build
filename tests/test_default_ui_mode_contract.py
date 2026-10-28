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
        self.assertIn("window = create_main_window(ui_mode)", self.source)
        self.assertIn('if mode not in {"premium-v2", "html", "web"}:', self.source)
        self.assertIn("return PremiumV2Window()", self.source)
        self.assertIn("Required Premium V2 Dragon Studio frontend is missing", self.source)

    def test_native_qt_shell_is_only_an_explicit_compatibility_mode(self):
        self.assertIn("RYU_UI_MODE=native", self.source)
        self.assertIn('if mode == "native":', self.source)
        self.assertIn("window = ProjectWorkflow()", self.source)
        self.assertIn("The application will not fall back to the older native interface.", self.source)
        self.assertNotRegex(self.source, r"if frontend_path\(\)\.is_file\(\):\s*\n\s*window = PremiumV2Window\(\)\s*\n\s*else:\s*\n\s*window = ProjectWorkflow\(\)")


if __name__ == "__main__":
    unittest.main()
