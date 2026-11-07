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
        start = source.index("const stage8ResponsiveDestinations = [")
        end = source.index("];", start) + 2
        block = source[start:end]
        for destination in expected:
            self.assertIn(f'"{destination}"', block)
            self.assertIn(f'stage829_sidebar_destination_" + destination', source)
        self.assertIn('button.nav-btn[data-page="', source)
        self.assertIn('page.classList.contains("active")', source)
        self.assertIn('page.getClientRects().length > 0', source)
        self.assertIn("const stage8ResponsiveDestinations = [", source)
        self.assertEqual(source.count("const stage8ResponsiveDestinations = ["), 1)
        self.assertLess(
            source.index("const stage8ResponsiveDestinations = ["),
            source.index("async function runStage53JobUiAcceptance"),
            "The shared destination list must be declared in the outer acceptance IIFE, not inside the responsive helper.",
        )
        self.assertIn('page.scrollWidth <= availablePageWidth + 2', source)
        self.assertIn('destination + " page has horizontal overflow at " + label', source)
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.assertIn(".generate-layout{grid-template-columns:minmax(0,.95fr) minmax(0,1.3fr) minmax(0,1fr)}", html)
        self.assertIn(".generate-layout>.card{min-width:0}", html)
        self.assertIn('stage8_generate_page_1280x720_no_horizontal_overflow', source)

    def test_sound_import_controls_stack_at_narrow_viewports(self):
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media(max-width:760px){.sound-master")
        mobile_end = html.index("/* PRONUNCIATION, MODELS & SETTINGS CONNECTED FLOW */", mobile_start)
        mobile = html[mobile_start:mobile_end]
        self.assertIn(".sound-import-box{display:grid;grid-template-columns:minmax(0,1fr)", mobile)
        self.assertIn(".sound-import-box>*{min-width:0;max-width:100%}", mobile)
        self.assertIn(".sound-import-box select,.sound-import-box .btn{width:100%;max-width:100%}", mobile)
        self.assertIn(".sound-track-grid{grid-template-columns:minmax(0,1fr);min-width:0}", mobile)
        self.assertIn(".sound-track,.sound-track-info{min-width:0;max-width:100%;overflow-wrap:anywhere}", mobile)
        self.assertIn(".sound-track-info>*{min-width:0;max-width:100%}", mobile)

    def test_responsive_fixture_uses_one_complete_sound_page_and_reports_overflowing_elements(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('stage6ResponsiveApp.includes(\'id="soundTrackGrid"\')', source)
        self.assertIn("stage6ResponsiveSoundCount === 1", source)
        self.assertNotIn("stage6ResponsiveApp.replace(", source)
        self.assertIn("stage6ResponsiveApp + stage6ResponsiveJobs + stage6ResponsiveDetails", source)
        self.assertIn("const overflowElements = pageOverflow ?", source)
        self.assertIn("rightOverflow", source)
        self.assertIn("internalOverflow", source)

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
