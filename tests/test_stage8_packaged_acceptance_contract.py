from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage8PackagedAcceptanceContractTests(unittest.TestCase):
    def test_production_preview_selector_resolves_live_option_during_polling(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        start = source.index("async function selectProductionPreviewChapter")
        end = source.index("await selectProductionPreviewChapter(2", start)
        helper = source[start:end]
        wait_start = helper.index('await waitFor("Production-owned Chapter "')
        predicate = helper.index("function () {", wait_start)
        predicate_end = helper.index("}, 10000);", predicate)
        predicate_source = helper[predicate:predicate_end]
        setup_source = helper[:predicate]
        self.assertIn("const expectedOption = optionFor(chapterNumber);", predicate_source)
        self.assertNotIn("const expectedOption = optionFor(chapterNumber);", setup_source)
        self.assertIn("Production chapter selector diagnostic=", helper)
        self.assertIn("productionChapterPicker.selectedOptions?.[0]?.textContent", predicate_source)


if __name__ == "__main__":
    unittest.main()
