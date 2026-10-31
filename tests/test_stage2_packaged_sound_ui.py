"""Regression contracts for packaged Stage 2 Sound Design acceptance."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Stage2PackagedSoundUiAcceptanceTests(unittest.TestCase):
    def test_acceptance_hook_is_opt_in_and_attached_to_real_frontend_readiness(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("self._start_sound_ui_acceptance()", host)
        self.assertIn("RYU_SOUND_UI_ACCEPTANCE_SCRIPT", host)
        self.assertIn("RYU_SOUND_UI_ACCEPTANCE_CONFIG", host)
        self.assertIn("RYU_SOUND_UI_ACCEPTANCE_MARKER", host)
        self.assertIn("window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__", host)
        self.assertIn("QTimer(self)", host)
        # No acceptance variables are set in normal launches. The hook must return
        # before changing any UI, backend state, or event loop behavior.
        start = host.index("def _start_sound_ui_acceptance")
        finish = host.index("def _poll_sound_ui_acceptance", start)
        hook = host[start:finish]
        self.assertLess(hook.index("if not any((script_value, config_value, marker_value))"), hook.index("try:"))
        self.assertIn("return", hook[hook.index("if not any((script_value, config_value, marker_value))"):])

    def test_browser_driver_uses_real_music_library_controls_and_bridge(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        for required in (
            "window.go('sound')",
            "[data-sound-tab=\"' + view + '\"]",
            "#musicImportCategory",
            "#importMusicTracks",
            "sound.import",
            "sound.catalog",
            "#soundTrackSearch",
            "data-music-category",
            "data-source",
            "data-select-sound",
            "#previewSelectedTrack",
            "#setBookDefaultTrack",
            "sound.chapter_bgm.get",
            "Pause selected track",
            "candidate_selection_does_not_overwrite_default",
        ):
            self.assertIn(required, script)

    def test_packaged_runner_creates_isolated_project_and_audio_fixtures(self):
        helper = (ROOT / "tests/packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for required in (
            "import winreg",
            "def get_active_project_setting",
            "def set_active_project_setting",
            "winreg.OpenKey",
            "winreg.CreateKeyEx",
            "winreg.QueryValueEx",
            "winreg.SetValueEx",
            "winreg.DeleteValue",
            "project.json",
            "chapters.json",
            "dialogue_assignments",
            "review_status",
            "skip_for_generation",
            "Path.home() / \"Ryu's Audiobook\"",
            "write_tone_fixture",
            "RYU_SOUND_UI_ACCEPTANCE_SCRIPT",
            "RYU_SOUND_UI_ACCEPTANCE_CONFIG",
            "RYU_SOUND_UI_ACCEPTANCE_MARKER",
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "validate_saved_music_state",
            "previous_active = get_active_project_setting()",
            "set_active_project_setting(str(project_folder.resolve()))",
            "set_active_project_setting(previous_active)",
        ):
            self.assertIn(required, helper)
        self.assertNotIn("from PySide6.QtCore import QSettings", helper)
        self.assertNotIn("from app.chapters.detector import Chapter", helper)
        self.assertNotIn("from app.core.project import Project", helper)
        self.assertNotIn("from app.core.state import save_state", helper)

    def test_packaged_driver_proves_real_music_and_cue_playback_and_cue_card_readability(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        for required in (
            "window.Audio = function (src)",
            "window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__",
            "audio.readyState >= 2",
            "audio.currentTime",
            "music_audio_preview_play_pause_resume",
            "music_preview_track_switch",
            "#importCueClips",
            'command === "sound.import" && request.target_kind === "cue"',
            "config.cue_paths",
            "#cueGrid [data-cue-path]",
            "#selectedCueTitle",
            "#selectedCueMeta",
            "#playSelectedCue",
            "#pauseSelectedCue",
            "#replaySelectedCue",
            "titleRect.bottom <= metadataRect.top",
            "cue_audio_preview_play_pause_replay",
            "cue_preview_track_switch",
            "cue_card_readability_and_selected_track_details",
        ):
            self.assertIn(required, script)

    def test_packaged_driver_waits_for_imported_cue_cards_and_reports_render_diagnostics(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('await waitFor("two imported cue cards to render"', script)
        self.assertIn("Imported cue cards did not render after native catalogue import.", script)
        self.assertIn("renderedCuePaths", script)
        self.assertIn("gridSignature", script)
        self.assertIn("cueRoleCounts", script)

    def test_category_fixture_import_uses_source_path_and_checks_library_destination(self):
        runner = (ROOT / "tests/packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('"source_path": str(item["source"].resolve())', runner)
        self.assertIn('"path": str((audio_root / item["source"].name).resolve())', runner)
        self.assertIn("request.paths = fixture && fixture.source_path ? [fixture.source_path] : [];", script)
        self.assertIn('String(track.path || "") === String(fixture.path)', script)
        self.assertIn('String(track.category || "").toLowerCase() === fixture.category', script)

    def test_packaged_runner_provisions_and_validates_separate_cue_fixtures(self):
        helper = (ROOT / "tests/packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for required in (
            "cue_alpha_source",
            "cue_beta_source",
            "cue_paths",
            "cue_track_titles",
            "validate_imported_audio_metadata",
            '"role": "cue"',
            '"category": "universal"',
        ):
            self.assertIn(required, helper)

    def test_music_grid_repairs_stale_dom_even_when_catalogue_signature_is_unchanged(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("async function refreshSounds()")
        end = adapter.index("async function refreshSoundCues()", start)
        refresh = adapter[start:end]
        self.assertIn("const expectedTrackCount = visible.length;", refresh)
        self.assertIn("const renderedTrackCount = grid ? grid.querySelectorAll('[data-select-sound]').length : 0;", refresh)
        self.assertIn("renderedSignature !== signature", refresh)
        self.assertIn("renderedTrackCount !== expectedTrackCount", refresh)
        self.assertIn("(expectedTrackCount > 0 && renderedTrackCount === 0)", refresh)
        self.assertIn("if (gridNeedsRepair)", refresh)
        self.assertLess(refresh.index("gridNeedsRepair"), refresh.index("grid.innerHTML = visible.map"))
        self.assertIn("grid.dataset.soundListSignature = signature;", refresh)

    def test_cue_library_refresh_loads_fresh_catalogue_without_invalidating_music_grid(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        music_start = adapter.index("async function refreshSounds()")
        cue_start = adapter.index("async function refreshSoundCues()", music_start)
        cue_end = adapter.index("function chapterMusicCategoryGroup", cue_start)
        music_refresh = adapter[music_start:cue_start]
        cue_refresh = adapter[cue_start:cue_end]
        self.assertIn("const requestToken = ++soundListEpoch;", music_refresh)
        self.assertIn("if (requestToken !== soundListEpoch) return sounds;", music_refresh)
        self.assertIn("const requestToken = ++cueListEpoch;", cue_refresh)
        self.assertNotIn("++soundListEpoch", cue_refresh)
        self.assertNotIn("catalogRequestToken", cue_refresh)
        self.assertNotIn("requestToken !== soundListEpoch", cue_refresh)
        self.assertIn("const [loadedCatalog, loadedAssignments] = await Promise.all([", cue_refresh)
        self.assertIn("call('sound.catalog')", cue_refresh)
        self.assertIn("call('sound.cues.get')", cue_refresh)
        self.assertIn("if (requestToken !== cueListEpoch) return cueAssignments;", cue_refresh)
        self.assertIn("sounds = Array.isArray(loadedCatalog) ? loadedCatalog : [];", cue_refresh)
        self.assertLess(cue_refresh.index("call('sound.catalog')"), cue_refresh.index("const visible = sounds.filter"))
        self.assertIn("isCueSoundAsset(t)", cue_refresh)

    def test_packaged_volume_interaction_focuses_the_real_slider_before_editing(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        start = script.index('const volume = document.querySelector("#advancedMusicVolume");')
        end = script.index('record("music_volume_control"', start)
        interaction = script[start:end]
        self.assertIn("volume.focus();", interaction)
        self.assertIn("document.activeElement === volume", interaction)
        focus_at = interaction.index("volume.focus();")
        edit_at = interaction.index("volume.value = String(config.expected_volume * 100);")
        self.assertLess(focus_at, edit_at)
        self.assertLess(interaction.index("volume.value ="), interaction.index('new Event("input"'))
        self.assertIn('new Event("change"', interaction)
        self.assertIn("saved.default_volume", interaction)
        self.assertIn('textContent.trim() === "42%"', interaction)
        self.assertIn('volume.value === "42"', interaction)
    def test_built_in_filter_failure_captures_native_catalogue_source_diagnostics(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        for required in (
            'const diagnosticCatalog = await invoke("sound.catalog", {});',
            "sourceCounts",
            "categoryCounts",
            "roleCounts",
            "catalogCount:",
            "activeCategory",
            "activeSource",
            "renderedRows",
            "Built-in filter did not settle on bundled music rows.",
        ):
            self.assertIn(required, script)
        self.assertIn(
            'const builtInSource = document.querySelector(\'#soundSourceFilter [data-source="built-in"]\');',
            script,
        )
        self.assertIn("catch (filterError)", script)

    def test_packaged_driver_waits_for_rendered_source_filter_results_not_only_button_state(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('rows.every(button => rowText(button).includes("Bundled with application"))', script)
        self.assertIn('rows.every(button => rowText(button).includes("Imported locally"))', script)
        self.assertIn("const texts = rows.map(rowText);", script)
        self.assertIn('texts.some(text => text.includes("Bundled with application"))', script)
        self.assertIn('texts.some(text => text.includes("Imported locally"))', script)
        self.assertIn('rows.every(button => rowText(button).includes("Fantasy adventure"))', script)
        self.assertIn('music_builtin_source_filter', script)
        self.assertIn('music_imported_source_filter', script)
        self.assertIn('music_all_source_filter', script)

    def test_windows_package_job_runs_the_real_frozen_executable_acceptance(self):
        workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("Run packaged Sound Design Music Library acceptance", workflow)
        self.assertIn("tests\\packaged_sound_ui_acceptance.py", workflow)
        self.assertIn("dist\\Ryu's Audiobook\\Ryu's Audiobook.exe", workflow)

    def test_packaged_acceptance_uses_durable_python_created_by_the_build_job(self):
        workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        acceptance_start = workflow.index("Run packaged Sound Design Music Library acceptance")
        acceptance_end = workflow.index("- name: Install Inno Setup", acceptance_start)
        acceptance_step = workflow[acceptance_start:acceptance_end]
        self.assertIn("ryu-qwen-python-bootstrap", acceptance_step)
        self.assertIn("python312", acceptance_step)
        self.assertIn("durable acceptance Python", acceptance_step)

    def test_cue_save_failure_state_survives_catalogue_refresh_and_retry(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        refresh_start = adapter.index("async function refreshSoundCues()")
        refresh_end = adapter.index("function chapterMusicCategoryGroup", refresh_start)
        refresh = adapter[refresh_start:refresh_end]
        schedule_start = adapter.index("function scheduleCueAutoSave()")
        schedule_end = adapter.index("async function savePendingCueChanges()", schedule_start)
        schedule = adapter[schedule_start:schedule_end]
        save_start = adapter.index("async function savePendingCueChanges()")
        save_end = adapter.index("function currentSoundManifestPayload", save_start)
        save = adapter[save_start:save_end]
        self.assertIn("cueSaveError = '';", adapter)
        self.assertIn("if (cueSaveError)", refresh)
        self.assertIn("cueSaveState.textContent = cueSaveError;", refresh)
        self.assertIn("if (cueSaveError)", schedule)
        self.assertIn("if (status) status.textContent = cueSaveError;", schedule)
        self.assertLess(schedule.index("if (cueSaveError)"), schedule.index("cueAutoSaveTimer = setTimeout"))
        self.assertIn("cueSaveError = 'Save failed. Unsaved cue changes have been retained.';", schedule)
        self.assertIn("failureStatus.textContent = cueSaveError;", schedule)
        self.assertIn("retryButton.disabled = !cueChangesDirty;", schedule)
        self.assertIn("cueSaveError = 'Save failed. Unsaved cue changes have been retained.';", save)
        self.assertIn("cueSaveError = '';", save)
        failure_start = script.index("config.reject_next_cue_save = true;")
        failure_end = script.index('record("cue_save_failure_retains_retryable_changes"', failure_start)
        failure_flow = script[failure_start:failure_end]
        self.assertIn("cueAllSource.click();", failure_flow)
        self.assertIn('textContent.includes("Save failed")', failure_flow)
        self.assertIn('textContent.includes("Unsaved")', failure_flow)
        self.assertIn('textContent.includes("All cue changes saved")', failure_flow)

    def test_chapter_selection_wait_requeries_row_after_real_renderer_rebuild(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = script.index("async function selectChapter(number)")
        end = script.index("async function chooseChapterCandidate", start)
        selection = script[start:end]
        wait_start = selection.index('await waitFor("Chapter " + number + " selection"')
        wait = selection[wait_start:]
        self.assertIn('const chapterRowSelector = \'#chapterBgmList [data-chapter-bgm="\' + number + \'"]\';', selection)
        self.assertIn("const rowToSelect = document.querySelector(chapterRowSelector);", selection)
        self.assertIn("rowToSelect.click();", selection)
        self.assertIn("const selectedRow = document.querySelector(chapterRowSelector);", wait)
        self.assertIn('selectedRow?.classList.contains("active") === true', wait)
        self.assertNotIn('rowToSelect.classList.contains("active")', wait)
        render_start = adapter.index("function renderChapterBgm()")
        render_end = adapter.index("async function refreshChapterBgm()", render_start)
        render = adapter[render_start:render_end]
        self.assertIn("list.innerHTML = rows.map", render)

    def test_chapter_acceptance_waits_for_completed_save_and_reenabled_editor(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        helper_start = script.index("async function waitForChapterSaveComplete")
        helper_end = script.index("await selectChapter(1);", helper_start)
        helper = script[helper_start:helper_end]
        self.assertIn('status === "Chapter assignment saved."', helper)
        self.assertIn("controls.every(control => control && !control.disabled)", helper)
        self.assertIn("row.start_offset === expectedValues.start_offset", helper)
        self.assertIn("row.end_behavior === expectedValues.end_behavior", helper)
        self.assertIn("Math.abs(Number(row.volume) - expectedValues.volume) < 0.005", helper)
        self.assertIn("await waitForChapterSaveComplete(1, \"custom\", alpha.path);", script)
        self.assertIn("await waitForChapterSaveComplete(2, \"custom\", beta.path);", script)
        self.assertIn('volume:0.37, start_offset:"after_first_paragraph", end_behavior:"continue_to_transition"', script)
        self.assertIn('volume:0.29, start_offset:"after_10_seconds", end_behavior:"stop_immediately"', script)
        save_start = adapter.index("async function saveCurrentChapterBgmDraft")
        save_end = adapter.index("function scheduleCueAutoSave", save_start)
        save = adapter[save_start:save_end]
        self.assertIn("controls.forEach(control => { control.disabled = true; });", save)
        self.assertIn("setChapterBgmSaveStatus('Chapter assignment saved.');", save)
        self.assertIn("controls.forEach((control, index) => { control.disabled = priorDisabled[index]; });", save)


    def test_mix_summary_preserves_all_pending_slider_drafts(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        summary_start = adapter.index("function renderSoundMixSummary()")
        summary_end = adapter.index("function renderChapterBgm()", summary_start)
        summary = adapter[summary_start:summary_end]

        # Editing one level can trigger a render while the next level is being
        # edited. The saved backend values must not overwrite any pending draft.
        for control in ("bgmLevelInput", "narrationInput", "cueLevelInput"):
            self.assertIn(
                f"if (!mixLevelsDirty && {control} && document.activeElement !== {control}",
                summary,
            )

        save_start = adapter.index("async function saveSoundMixLevels(force = false)")
        save_end = adapter.index("async function flushSoundDesignState", save_start)
        save = adapter[save_start:save_end]
        self.assertIn("if (revision === mixLevelsRevision)", save)
        self.assertIn("mixLevelsDirty = false;", save)
        self.assertIn("renderSoundMixSummary();", save)


    def test_mix_level_manifest_saves_do_not_rewrite_global_bgm_toggle(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        payload_start = adapter.index("function currentSoundManifestPayload()")
        payload_end = adapter.index("async function saveSoundManifest", payload_start)
        payload = adapter[payload_start:payload_end]
        self.assertNotIn("enabled:", payload)
        self.assertIn("saveSoundManifest({path, enabled})", adapter)

        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        save_start = host.index("def _sound_save_manifest(")
        save_end = host.index("def _sound_chapter_bgm_get(", save_start)
        save = host[save_start:save_end]
        self.assertIn('explicit_enabled = "enabled" in payload', save)
        self.assertIn("current_mode = effective_background_audio_mode(state)", save)
        self.assertIn('else current_mode != "off"', save)
        self.assertIn('else current_mode,', save)
