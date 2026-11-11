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
        self.assertIn('narratorOnlyInitialProject.narrator_only_generation === true', javascript_source)
        self.assertIn('narratorOnlyControl.checked === true', javascript_source)
        self.assertIn('Automatically enabled because this book has no configured character voice profiles', javascript_source)
        playback_start = javascript_source.index('let narratorOnlyCard = null;')
        playback_end = javascript_source.index('record("xapp08_packaged_narrator_only_full_book_generation"', playback_start)
        playback_flow = javascript_source[playback_start:playback_end]
        self.assertIn('String(card.dataset.projectFolder || "") ===', playback_flow)
        self.assertIn('String(config.narrator_only_project_folder || "")', playback_flow)
        self.assertIn('querySelector("[data-open-project-folder]").click()', playback_flow)
        self.assertIn('readyState >= 1 && audio.paused', playback_flow)
        self.assertIn('audioUsesPath(narratorOnlyLoadedAudio, narratorOnlyPlayer.playback_output_path)', playback_flow)
        self.assertIn('querySelector("[data-play-project-folder]").click()', playback_flow)
        self.assertIn('const narratorOnlyAudio = await waitForRealPlayback(', playback_flow)
        self.assertIn('must(narratorOnlyAudio === narratorOnlyLoadedAudio', playback_flow)

    def test_production_preview_selector_reacquires_live_selector_and_option_during_polling(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        start = source.index("async function selectProductionPreviewChapter")
        end = source.index("await selectProductionPreviewChapter(2", start)
        helper = source[start:end]
        wait_start = helper.index('await waitFor("Production-owned Chapter "')
        predicate = helper.index("function () {", wait_start)
        predicate_end = helper.index("}, 10000);", predicate)
        predicate_source = helper[predicate:predicate_end]
        setup_source = helper[:predicate]
        self.assertIn('const pickerFor = () => document.querySelector("#productionPreviewChapterSelect");', helper)
        self.assertIn("const picker = pickerFor();", predicate_source)
        self.assertIn("const expectedOption = optionFor(chapterNumber);", predicate_source)
        self.assertNotIn("const expectedOption = optionFor(chapterNumber);", setup_source)
        self.assertIn("Production chapter selector diagnostic=", helper)
        self.assertIn("picker.selectedOptions?.[0]?.textContent", predicate_source)

    def test_packaged_acceptance_rejects_overlapping_independent_controls_on_all_pages(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn("const visibleControls = Array.from(page.querySelectorAll(", source)
        self.assertIn("const overlappingControls = [];", source)
        self.assertIn('overlapWidth > 3 && overlapHeight > 3', source)
        self.assertIn('page has overlapping independent controls at ', source)
        self.assertIn('record("stage8_no_overlapping_controls_" + destination', source)

    def test_models_center_action_buttons_wrap_without_overlapping_neighbor_controls(self):
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn(".model-actions{display:flex;flex-wrap:wrap;gap:6px;min-width:0}", html)
        self.assertIn(".model-actions .btn{min-width:0;max-width:100%;white-space:normal;overflow-wrap:anywhere}", html)
        self.assertIn("#models .model-grid{margin-bottom:40px}#models .install-queue{margin-top:0}", html)
        self.assertIn("grid.style.paddingBottom = '48px';", adapter)
        self.assertIn('.model-install-details[open]>.model-install-content{display:grid;gap:10px;padding-top:10px}', adapter)
        self.assertIn('#backgroundJobsModal .jobs-modal,.modal-back .jobs-modal{box-sizing:border-box;width:min(780px,calc(100vw - 40px));min-width:0;max-width:calc(100vw - 40px)}', adapter)
        self.assertIn('<div class="model-install-content">', adapter)
        self.assertNotIn('<div style="display:grid;gap:10px;padding-top:10px">', adapter)

    def test_production_chapter_refresh_preserves_explicit_selection(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function syncProductionPreviewChapterSelector()")
        end = adapter.index("function ensureProductionPreviewMonitorUi()", start)
        selector = adapter[start:end]
        stale_data_branch = selector[selector.index("} else if (currentRow && ("):selector.index("if (!rows.length)")]
        self.assertIn("invalidateVoicePreview();", stale_data_branch)
        self.assertIn("productionPreviewSelectedChapterId = currentId;", stale_data_branch)
        self.assertIn("productionPreviewSelectedChapterSignature = currentSignature;", stale_data_branch)
        self.assertNotIn("productionPreviewSelectedChapter = null;", stale_data_branch)

    def test_overlap_failure_reports_exact_controls_and_model_card(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('leftRect:{left:Math.round(left.rect.left)', source)
        self.assertIn('leftModelCard:left.element.closest(".model-card")', source)
        self.assertIn('leftCardRect:(() => {const r=left.element.closest(".model-card")', source)
        self.assertIn('modelGridRect:(() => {const r=d.querySelector("#modelGrid")', source)

    def test_windows_package_runs_real_multichapter_m4b_acceptance_without_changing_bundle(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        smoke = (ROOT / "tests" / "smoke_stage3_real_multichapter.py").read_text(encoding="utf-8")

        run_start = workflow.index("      - name: Run real bundled-Piper multi-chapter M4B acceptance")
        upload_start = workflow.index("      - name: Upload real multi-chapter M4B acceptance evidence", run_start)
        run_step = workflow[run_start:upload_start]
        upload_end = workflow.index("\n      - name: ", upload_start + 1)
        upload_step = workflow[upload_start:upload_end]

        self.assertIn("RYU_PIPER_MODEL_ROOT", run_step)
        self.assertIn("RYU_STAGE3_ACCEPTANCE_OUTPUT", run_step)
        self.assertIn("en_US-ryan-high", run_step)
        self.assertIn("pip install --disable-pip-version-check --no-input -r requirements.txt", run_step)
        self.assertIn("import piper, piper.download_voices, pyttsx3, imageio_ffmpeg, soundfile", run_step)
        self.assertIn("Installing declared application dependencies for real M4B acceptance", run_step)
        self.assertIn("tests\\smoke_stage3_real_multichapter.py", run_step)
        self.assertIn("MODEL_ROOT = Path(os.environ.get(\"RYU_PIPER_MODEL_ROOT\"", smoke)
        self.assertIn("REAL_MULTICHAPTER_M4B=PASS", smoke)
        self.assertIn("REAL_M4B_FFMPEG_DECODE=PASS", smoke)
        self.assertIn("chapters_total != 2", smoke)
        self.assertIn('if: always()', upload_step)
        self.assertIn("Ryu-Stage3-Real-Multichapter-M4B-", upload_step)
        self.assertIn("if-no-files-found: warn", upload_step)

    def test_live_qwen_smoke_download_has_official_fallback_and_pinned_digest(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("$llamaZipExpectedSha256 = '1110e183589e0e2ac5b365fb5c3c4a7e149e0760c1989cac18ee426b08e5813a'", workflow)
        self.assertIn("https://api.github.com/repos/ggml-org/llama.cpp/releases/assets/589841111", workflow)
        self.assertIn("Accept: application/octet-stream", workflow)
        self.assertIn("$actualLlamaZipSha256 -eq $llamaZipExpectedSha256", workflow)
        self.assertIn("Could not obtain the pinned llama.cpp CPU runtime through either official GitHub release route.", workflow)


if __name__ == "__main__":
    unittest.main()
