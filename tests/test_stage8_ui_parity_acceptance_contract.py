from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage8UIPackagedAcceptanceContractTests(unittest.TestCase):
    def test_packaged_acceptance_visits_all_fifteen_sidebar_destinations(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        expected = [
            "dashboard", "library", "import", "chapters", "voices",
            "characters", "pronunciation", "sound", "generate", "player",
            "history", "models", "performance", "settings", "help",
        ]
        start = source.index("const stage8Destinations = [")
        end = source.index("];", start) + 2
        block = source[start:end]
        for destination in expected:
            self.assertIn(f'"{destination}"', block)
            self.assertIn(f'stage829_sidebar_destination_" + destination', source)
        self.assertIn('button.nav-btn[data-page="', source)
        self.assertIn('page.classList.contains("active")', source)
        self.assertIn('page.getClientRects().length > 0', source)


if __name__ == "__main__":
    unittest.main()
