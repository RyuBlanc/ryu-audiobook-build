"""Keep the installed app on the verified native workflow until Premium V2 parity is accepted."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"


class DefaultUiModeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_native_qt_workflow_is_the_default_installed_interface(self):
        self.assertIn(
            'ui_mode = os.environ.get("RYU_UI_MODE", "native").strip().casefold()',
            self.source,
        )
        self.assertRegex(self.source, r"else:\s*\n\s*window = ProjectWorkflow\(\)")

    def test_premium_v2_remains_available_for_explicit_parity_testing(self):
        self.assertIn('if ui_mode in {"premium-v2", "html", "web"}:', self.source)
        self.assertIn("window = PremiumV2Window()", self.source)


if __name__ == "__main__":
    unittest.main()
