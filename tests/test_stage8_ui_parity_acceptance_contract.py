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
        self.assertIn("const stage8ResponsiveDestinations = [", source)
        self.assertIn('page.scrollWidth <= availablePageWidth + 2', source)
        self.assertIn('destination + " page has horizontal overflow at " + label', source)

    def test_help_guide_badge_does_not_claim_release_version_before_version_bump(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("Stage 8 acceptance candidate", adapter)
        self.assertNotIn("Version 1.2.0 release candidate", adapter)
        self.assertIn("preserves paragraph boundaries when the selected Chapter-Based track uses After first paragraph", adapter)

    def test_packaged_acceptance_exercises_help_guide_search_and_disclosure_controls(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('helpSearch.value = "After first paragraph"', source)
        self.assertIn('helpNoResults.hidden === false', source)
        self.assertIn('helpGuideExpandAll', source)
        self.assertIn('helpGuideCollapseAll', source)
        self.assertIn('stage829_help_guide_search_empty_expand_collapse', source)



if __name__ == "__main__":
    unittest.main()
