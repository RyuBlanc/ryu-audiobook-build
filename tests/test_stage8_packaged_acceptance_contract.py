from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage8PackagedAcceptanceContractTests(unittest.TestCase):
    def test_packaged_acceptance_runs_real_narrator_only_full_book_generation(self):
        python_source = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        javascript_source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn("narrator_only_project_folder =", python_source)
        self.assertIn('"narrator_only_generation": False', python_source)
        self.assertIn('"characters": [],', python_source)
        self.assertIn('"narrator_only_project_folder": str(narrator_only_project_folder.resolve())', python_source)
        self.assertIn("document.querySelector(\"#narratorOnlyGeneration\")", javascript_source)
        self.assertIn("active.narrator_only_generation === true", javascript_source)
        self.assertIn('narratorOnlyJob.result?.generation_mode === "narrator_only"', javascript_source)
        self.assertIn('Number(narratorOnlyJob.result?.character_voice_profile_count) === 0', javascript_source)
        self.assertIn('xapp08_packaged_narrator_only_full_book_generation', javascript_source)
        self.assertIn("real narrator-only M4B audio in the Premium V2 Audiobooks player", javascript_source)
        playback_start = javascript_source.index('const narratorOnlyCard = await waitFor(')
        playback_end = javascript_source.index('record("xapp08_packaged_narrator_only_full_book_generation"', playback_start)
        playback_flow = javascript_source[playback_start:playback_end]
        self.assertIn('card.dataset.projectFolder || "") === String(config.narrator_only_project_folder || "")', playback_flow)
        self.assertIn('querySelector("[data-open-project-folder]").click()', playback_flow)
        self.assertIn('readyState >= 1 && audio.paused', playback_flow)
        self.assertIn('audioUsesPath(narratorOnlyLoadedAudio, narratorOnlyPlayer.playback_output_path)', playback_flow)
        self.assertIn('querySelector("[data-play-project-folder]").click()', playback_flow)
        self.assertIn('!narratorOnlyAudio.paused && narratorOnlyAudio.readyState >= 2', playback_flow)

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
