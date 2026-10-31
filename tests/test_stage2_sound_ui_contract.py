"""Stage 2 regression contracts for the approved Sound Design UI."""

from pathlib import Path
import re
import unittest


class Stage2SoundDesignUiContractTests(unittest.TestCase):
    @staticmethod
    def _extract_js_braced_block(source: str, opening_brace: int) -> str:
        """Extract a JavaScript block without counting braces in strings/comments."""
        if opening_brace < 0 or opening_brace >= len(source) or source[opening_brace] != "{":
            raise AssertionError("JavaScript block opening brace was not found.")

        depth = 0
        quote = None
        escaped = False
        line_comment = False
        block_comment = False
        index = opening_brace

        while index < len(source):
            char = source[index]
            next_char = source[index + 1] if index + 1 < len(source) else ""

            if line_comment:
                if ord(char) == 10:
                    line_comment = False
            elif block_comment:
                if char == "*" and next_char == "/":
                    block_comment = False
                    index += 1
            elif quote:
                if escaped:
                    escaped = False
                elif ord(char) == 92:
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in ("'", chr(34), chr(96)):
                quote = char
            elif char == "/" and next_char == "/":
                line_comment = True
                index += 1
            elif char == "/" and next_char == "*":
                block_comment = True
                index += 1
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[opening_brace:index + 1]

            index += 1

        raise AssertionError("JavaScript block is not closed.")

    @classmethod
    def _extract_js_function(cls, source: str, declaration: str) -> str:
        """Extract one complete JavaScript function without next-declaration slicing."""
        start = source.find(declaration)
        if start < 0:
            raise AssertionError(f"JavaScript function was not found: {declaration}")
        body_marker = source.find(") {", start)
        if body_marker < 0:
            raise AssertionError(f"JavaScript function body was not found: {declaration}")
        return cls._extract_js_braced_block(source, body_marker + 2)

    @classmethod
    def _extract_js_branch(cls, source: str, declaration: str, condition: str) -> str:
        """Extract a click-handler branch even when sibling branches are reordered."""
        start = source.find(declaration)
        if start < 0:
            raise AssertionError(f"JavaScript handler declaration was not found: {declaration}")
        condition_start = source.find(condition, start)
        if condition_start < 0:
            raise AssertionError(f"JavaScript handler condition was not found: {condition}")
        opening_brace = source.find("{", condition_start + len(condition))
        if opening_brace < 0:
            raise AssertionError(f"JavaScript handler body was not found: {condition}")
        return cls._extract_js_braced_block(source, opening_brace)

    def setUp(self):
        self.html = Path("assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.adapter = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.host = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        self.manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        self.preview = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        start = self.html.index('<section class="page" id="sound">')
        end = self.html.index('<section class="page" id="generate">', start)
        self.sound_markup = self.html[start:end]
        self.sound_header = self.sound_markup[:self.sound_markup.index('<div class="sound-master card">')]

    def test_removed_top_right_preview_and_sync_actions_are_not_rendered(self):
        self.assertNotRegex(self.sound_header, r'<button\b[^>]*\bid="soundPreviewBook"')
        self.assertNotRegex(self.sound_header, r'<button\b[^>]*\bid="saveSoundPresetAdvanced"')

    def test_removed_controls_and_scene_slot_are_not_dereferenced_by_prototype_scripts(self):
        self.assertNotIn("document.getElementById('soundPreviewBook').addEventListener", self.html)
        self.assertNotIn("document.getElementById('saveSoundPresetAdvanced').addEventListener", self.html)
        self.assertNotIn("document.getElementById('mixSceneCue').textContent", self.html)
        self.assertNotIn("['opening','chapter','scene','closing']", self.html)
        self.assertNotIn("['opening','chapter','scene','closing']", self.adapter)



    def test_sound_design_has_no_demo_seed_script_or_fake_summary_values(self):
        self.assertNotIn("const state={bgm:true,defaultTrack:'Fantasy Kingdom'", self.html)
        self.assertNotIn("renderTracks();renderChapters();renderChapterPicker();renderCues();updateSummary();", self.html)
        for sample in ("Fantasy Kingdom", "Dragon Gate Intro", "Crystal Page Turn",
                       "Tempest Closing Theme", "Narration + Fantasy Kingdom + 4 cues"):
            self.assertNotIn(sample, self.sound_markup)
        self.assertNotRegex(self.sound_markup, re.compile(r"scene.?transition", re.IGNORECASE))
        self.assertIn('id="soundTrackGrid"><p class="muted">Loading local music library…</p>', self.sound_markup)
        self.assertIn('id="cueGrid"><p class="muted">Loading local effects library…</p>', self.sound_markup)
        self.assertIn("await hydratePhase([refreshSounds, refreshSoundCues, refreshChapterBgm]);", self.adapter)

    def test_mix_and_production_readiness_report_overall_save_state_truthfully(self):
        self.assertIn('id="mixOverallSaveState"', self.sound_markup)
        for status in (
            "Saving sound configuration…",
            "Unsaved sound changes — save before opening Production Studio.",
            "Saved configuration has ",
            "All sound settings saved.",
            "Sound configuration has not been saved yet.",
        ):
            self.assertIn(status, self.adapter)
        self.assertIn("const soundSaveInFlight = Boolean(", self.adapter)
        self.assertIn("chapterBgmSavePromise || cueSavePromise || mixLevelsSavePromise ||", self.adapter)
        self.assertIn("soundManifestSavePromise || chapterStrategySavePromise", self.adapter)
        self.assertIn("productionSoundReady.textContent = 'Saving sound settings…';", self.adapter)
        self.assertIn("const hasUnsavedSoundChanges =", self.adapter)
        self.assertIn("Object.keys(soundManifestPendingOverrides).length > 0", self.adapter)

    def test_global_bgm_toggle_flushes_drafts_before_persisting_mode(self):
        start = self.adapter.index("const bgmMasterToggle = e.target.closest('#sound [data-bgm-enabled], #generate [data-bgm-enabled]');")
        end = self.adapter.index("const chapterBgmItem = e.target.closest('#chapterBgmList [data-chapter-bgm]');", start)
        handler = self.adapter[start:end]
        self.assertIn("await flushSoundDesignState();", handler)
        self.assertIn("await saveSoundManifest({path, enabled});", handler)
        self.assertLess(handler.index("await flushSoundDesignState();"), handler.index("await saveSoundManifest({path, enabled});"))
        self.assertIn("let chapterStrategySavePromise = null;", self.adapter)
        self.assertIn("chapterStrategySavePromise = runSave;", self.adapter)

    def test_shared_sound_flush_saves_and_verifies_all_drafts(self):
        start = self.adapter.index("async function flushSoundDesignState(")
        end = self.adapter.index("function scheduleLibrarySearchRefresh()", start)
        helper = self.adapter[start:end]
        ordered = (
            "if (chapterStrategySavePromise) await chapterStrategySavePromise;",
            "await saveCurrentChapterBgmDraft();",
            "await savePendingCueChanges();",
            "await saveSoundMixLevels(true);",
            "await refreshChapterBgm();",
            "await refreshSoundCues();",
            "if (unresolved)",
        )
        positions = [helper.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Object.keys(soundManifestPendingOverrides).length > 0", helper)
        self.assertIn("Sound Design changes are still saving or unsaved", helper)

    def test_production_handoff_and_final_generation_flush_sound_design(self):
        handoff_start = self.adapter.index("soundButton.id === 'applySoundToProduction'")
        handoff_end = self.adapter.index("soundButton.id === 'saveChapterBgm'", handoff_start)
        handoff = self.adapter[handoff_start:handoff_end]
        self.assertIn("await flushSoundDesignState();", handoff)
        preview_start = self.adapter.index("soundButton.id === 'soundPreviewBook'")
        preview_end = self.adapter.index("if (!finished) throw new Error('Sound Design preview timed out.", preview_start)
        preview = self.adapter[preview_start:preview_end]
        self.assertIn("await flushSoundDesignState({requireExplicitCueClear:true});", preview)
        generation_start = self.adapter.index("if ($('startGenerate'))")
        generation_end = self.adapter.index("if ($('pauseGenerate'))", generation_start)
        generation = self.adapter[generation_start:generation_end]
        self.assertIn("await flushSoundDesignState();", generation)
        self.assertLess(generation.index("await flushSoundDesignState();"), generation.index("call('production.generate_book'"))

    def test_production_studio_generation_toggle_shares_saved_sound_design_state(self):
        start = self.html.index('<section class="page" id="generate">')
        status = self.html.index('id="productionSoundReady"', start)
        production_markup = self.html[start:status + 120]
        self.assertIn('data-bgm-enabled="true"', production_markup)
        self.assertIn('data-bgm-enabled="false"', production_markup)
        self.assertIn('aria-label="Generation audio mode"', production_markup)
        self.assertNotIn('>✓ Synced</b>', production_markup)
        self.assertIn("document.querySelectorAll('#sound [data-bgm-enabled], #generate [data-bgm-enabled]')", self.adapter)
        self.assertIn("e.target.closest('#sound [data-bgm-enabled], #generate [data-bgm-enabled]')", self.adapter)
        self.assertIn("await saveSoundManifest({path, enabled});", self.adapter)
        self.assertIn("const productionSoundReady = $('productionSoundReady');", self.adapter)
        self.assertIn("Unsaved sound changes", self.adapter)
        self.assertIn("missing audio asset", self.adapter)
        self.assertIn("Voice Only synced", self.adapter)

    def test_voice_only_copy_and_master_toggle_match_saved_generation_contract(self):
        self.assertIn("Narration only; BGM and all story cues are disabled", self.sound_markup)
        self.assertNotIn("Keep narration and story cues only", self.sound_markup)
        self.assertIn("const bgmMasterToggle = e.target.closest('#sound [data-bgm-enabled], #generate [data-bgm-enabled]');", self.adapter)
        self.assertIn("call('sound.save_manifest'", self.adapter)
        self.assertIn("Voice Only saved. Background music and all story cues are disabled", self.adapter)

    def test_mix_summary_values_are_loaded_from_backend_not_demo_defaults(self):
        self.assertIn("function renderSoundMixSummary()", self.adapter)
        for field in ("mixBgmStatus", "mixStrategy", "mixOverrides", "mixEffectiveTracks",
                      "mixBgmVolumeValue", "mixOpening", "mixChapterCue", "mixClosing", "soundPreviewPath",
                      "soundFinalRenderPath", "soundMissingFiles", "soundLastSaved"):
            self.assertIn("setText('" + field + "'", self.adapter)
        self.assertIn('id="soundMissingFiles"', self.sound_markup)
        self.assertIn('id="mixCueSignal"', self.sound_markup)
        self.assertNotIn('id="mixBgmStatus">Enabled</b>', self.sound_markup)
        self.assertNotIn('id="mixDefaultTrack">Fantasy Kingdom</b>', self.sound_markup)
        self.assertNotIn('<div><span>Missing imported files</span>', self.sound_markup)

    def test_music_library_categories_are_real_filter_controls(self):
        required = (
            "all", "fantasy-adventure", "battle-warfare", "mystery",
            "horror", "romance", "sci-fi", "calm-narration", "others",
        )
        for category in required:
            self.assertIn(f'data-music-category="{category}"', self.sound_markup)
        self.assertIn("selectedMusicCategory", self.adapter)
        self.assertIn("matchesCategory", self.adapter)
        self.assertIn("metadata.category", self.adapter)

    def test_music_import_uses_selected_category(self):
        self.assertIn('id="musicImportCategory"', self.sound_markup)
        self.assertIn("category: soundButton.id === 'importMusicTracks' ? ($('musicImportCategory')?.value || 'universal') : 'universal'", self.adapter)

    def test_fixed_cue_markup_has_only_supported_opening_next_and_closing_slots(self):
        self.assertNotIn('data-assign-cue="scene"', self.sound_markup)
        self.assertNotIn('id="sceneCueName"', self.sound_markup)
        self.assertNotIn('id="mixSceneCue"', self.sound_markup)
        self.assertIn('data-assign-cue="opening"', self.sound_markup)
        self.assertIn('data-assign-cue="chapter"', self.sound_markup)
        self.assertIn('data-assign-cue="closing"', self.sound_markup)

    def test_all_sound_design_views_have_working_tab_navigation(self):
        for view in ("music", "chapters", "cues", "mix"):
            self.assertIn(f'data-sound-tab="{view}"', self.sound_markup)
            self.assertIn(f'data-sound-view="{view}"', self.sound_markup)
        self.assertIn("const soundTab = e.target?.closest?.('#sound .sound-tabs [data-sound-tab]');", self.adapter)
        self.assertIn("document.querySelectorAll('#sound .sound-view[data-sound-view]')", self.adapter)
        self.assertIn("if (nextView === 'music') await refreshSounds();", self.adapter)
        self.assertIn("else if (nextView === 'chapters') await refreshChapterBgm();", self.adapter)
        self.assertIn("else if (nextView === 'cues') await refreshSoundCues();", self.adapter)
        self.assertIn("else if (nextView === 'mix')", self.adapter)


    def test_screen_by_screen_sound_design_controls_are_connected(self):
        views = ("music", "chapters", "cues", "mix")
        panes = {}
        for index, view in enumerate(views):
            marker = f'data-sound-view="{view}"'
            position = self.sound_markup.index(marker)
            pane_start = self.sound_markup.rfind('<div class="sound-view', 0, position)
            if index + 1 < len(views):
                next_marker = f'data-sound-view="{views[index + 1]}"'
                next_position = self.sound_markup.index(next_marker)
                pane_end = self.sound_markup.rfind('<div class="sound-view', 0, next_position)
            else:
                pane_end = len(self.sound_markup)
            panes[view] = self.sound_markup[pane_start:pane_end]

        for control in ("soundTrackGrid", "soundTrackSearch", "soundSourceFilter",
                        "musicImportCategory", "previewSelectedTrack", "advancedMusicVolume",
                        "setBookDefaultTrack"):
            self.assertIn('id="' + control + '"', panes["music"])
        for control in ("chapterBgmList", "chapterBgmTitle", "chapterTrackPicker",
                        "chapterVolume", "chapterStartOffset", "chapterEndBehavior",
                        "saveChapterBgm"):
            self.assertIn('id="' + control + '"', panes["chapters"])
        for control in ("cueGrid", "openingCueName", "chapterCueName", "closingCueName",
                        "selectedCueTitle", "playSelectedCue", "pauseSelectedCue",
                        "replaySelectedCue", "saveCueChanges", "clearAllCues"):
            self.assertIn('id="' + control + '"', panes["cues"])
        for control in ("narrationVolume", "cueVolume", "mixBgmStatus", "mixStrategy",
                        "mixOverrides", "mixOpening", "mixChapterCue", "mixClosing"):
            self.assertIn('id="' + control + '"', panes["mix"])

        self.assertIn("e.target.closest('#soundSourceFilter [data-source]')", self.adapter)
        self.assertIn("e.target.closest('#sound .sound-categories-list [data-music-category]')", self.adapter)
        self.assertIn("e.target.closest('#chapterBgmSourceFilter [data-chapter-source]')", self.adapter)
        self.assertIn("e.target.closest('#chapterBgmCategoryFilter [data-chapter-category]')", self.adapter)
        self.assertIn("document.querySelectorAll('#cueSourceFilter [data-cue-source]')", self.adapter)
        self.assertIn("refreshSoundCues().catch", self.adapter)
        self.assertIn("call('sound.import'", self.adapter)
        self.assertIn("call('sound.chapter_bgm.save'", self.adapter)
        self.assertIn("call('sound.cues.save'", self.adapter)
        self.assertIn("saveSoundMixLevels(true)", self.adapter)
        self.assertIn("setText('productionMusicSummary', productionMusicLabel)", self.adapter)

    def test_sound_tab_navigation_preempts_legacy_prototype_handlers(self):
        # The earlier test checked only that a handler string existed. The installed
        # app also runs the approved reference HTML's prototype listeners, so the
        # adapter must remove those listeners and handle navigation in capture phase.
        self.assertIn("const legacySoundTabs = document.querySelector('#sound .sound-tabs');", self.adapter)
        self.assertIn("const cleanSoundTabs = legacySoundTabs.cloneNode(true);", self.adapter)
        self.assertIn("legacySoundTabs.replaceWith(cleanSoundTabs);", self.adapter)
        tab_marker = "const soundTab = e.target?.closest?.('#sound .sound-tabs [data-sound-tab]');"
        tab_body = self.adapter.index(tab_marker)
        handler_start = self.adapter.rfind("document.addEventListener('click', async e =>", 0, tab_body)
        handler_end = self.adapter.index("}, true);", handler_start)
        handler = self.adapter[handler_start:handler_end + len("}, true);")]
        self.assertIn("e.stopImmediatePropagation();", handler)
        self.assertIn("if (!['music', 'chapters', 'cues', 'mix'].includes(nextView)) return;", handler)
        self.assertIn("document.querySelectorAll('#sound .sound-tabs [data-sound-tab]')", handler)
        self.assertIn("document.querySelectorAll('#sound .sound-view[data-sound-view]')", handler)
        self.assertLess(self.adapter.index("legacySoundTabs.replaceWith(cleanSoundTabs);"), handler_start)

    def test_chapter_bgm_assignments_survive_strategy_switch(self):
        start = self.host.index("    def _sound_chapter_bgm_save(")
        end = self.host.index("    def _sound_cues_get(", start)
        method = self.host[start:end]
        self.assertIn('state["chapter_bgm_strategy"] = strategy', method)
        self.assertNotIn('state["chapter_bgm_overrides"] = {}', method)
        self.assertIn("await saveCurrentChapterBgmDraft();", self.adapter)
        self.assertIn("chapter assignments were preserved for switching back.", self.adapter)
        strategy_handler = self._extract_js_branch(
            self.adapter,
            "const chapterStrategy = e.target.closest('#sound [data-bgm-strategy]');",
            "if (chapterStrategy)",
        )
        self.assertIn("await saveCurrentChapterBgmDraft();", strategy_handler)
        self.assertIn("await call('sound.chapter_bgm.save', {strategy:chapterStrategy.dataset.bgmStrategy});", strategy_handler)
        self.assertLess(
            strategy_handler.index("await saveCurrentChapterBgmDraft();"),
            strategy_handler.index("await call('sound.chapter_bgm.save', {strategy:chapterStrategy.dataset.bgmStrategy});"),
        )
        flush_helper = self._extract_js_function(self.adapter, "async function flushSoundDesignState(")
        self.assertIn("await saveCurrentChapterBgmDraft();", flush_helper)
        self.assertIn("await savePendingCueChanges();", flush_helper)
        self.assertLess(flush_helper.index("await saveCurrentChapterBgmDraft();"), flush_helper.index("await savePendingCueChanges();"))

    def test_master_and_chapter_bgm_gains_are_capped_at_50_percent(self):
        start = self.host.index("    def _sound_assign(")
        end = self.host.index("    def _sound_save_manifest(", start)
        assign = self.host[start:end]
        start = self.host.index("    def _sound_save_manifest(")
        end = self.host.index("    def _sound_chapter_bgm_get(", start)
        manifest = self.host[start:end]
        self.assertIn("min(0.50, float(payload.get(\"volume\", 0.18)))", assign)
        self.assertIn("min(0.50, float(payload.get(\"volume\"", manifest)
        self.assertIn("background_audio_volume = max(0.0, min(0.50, float(background_audio_volume)))", self.assembler)
        self.assertIn("gain = max(0.0, min(0.50, float(volume)))", self.assembler)
        self.assertIn("self.background_audio_volume = max(0.0, min(0.50, float(background_audio_volume)))", self.manager)
        self.assertIn('max="50" min="0" type="range" value="18"', self.sound_markup)

    def test_chapter_controls_remove_legacy_prototype_handlers(self):
        self.assertIn("'saveCueChanges','chapterBgmList','chapterTrackPicker'].forEach(id => {", self.adapter)
        self.assertIn("['#sound .chapter-bgm-strategy', '#sound .chapter-rule'].forEach(selector => {", self.adapter)
        self.assertIn("const cleanNode = node.cloneNode(true);", self.adapter)
        self.assertIn("cleanNode.querySelectorAll('[onclick]').forEach(button => button.removeAttribute('onclick'));", self.adapter)
        self.assertIn("node.replaceWith(cleanNode);", self.adapter)

    def test_chapter_bgm_uses_real_source_and_category_filters(self):
        for source in ("all", "built-in", "imported"):
            self.assertIn(f'data-chapter-source="{source}"', self.adapter)
        for category in ("all", "fantasy-adventure", "battle-warfare", "mystery",
                         "horror", "romance", "sci-fi", "calm-narration", "others"):
            self.assertIn(f'data-chapter-category="{category}"', self.adapter)
        self.assertIn("chapterMusicCategoryGroup(track) === categoryFilter", self.adapter)
        self.assertIn("const sourceKind = soundSourceKind(track);", self.adapter)
        self.assertIn("(sourceFilter === 'built-in' && sourceKind === 'built-in')", self.adapter)
        self.assertIn("(sourceFilter === 'imported' && sourceKind === 'imported')", self.adapter)
        self.assertIn("data-chapter-category", self.adapter)
        self.assertIn("chapterTrackListSignature", self.adapter)

    def test_chapter_track_selection_requires_explicit_confirmation(self):
        self.assertIn("panel.id = 'chapterBgmSelectedTrackPanel'", self.adapter)
        self.assertIn('SELECT TRACK', self.adapter)
        self.assertIn('id="confirmChapterBgmTrack"', self.adapter)
        self.assertIn("chapterBgmCandidateTrackPath = chapterTrack.dataset.chapterTrack", self.adapter)
        self.assertIn("await saveCurrentChapterBgmDraft(true)", self.adapter)
        self.assertNotIn("selectedBgmTrackPath = chapterTrack.dataset.chapterTrack", self.adapter)
        self.assertIn("Candidate only — press Select to save it", self.adapter)

    def test_mix_summary_removes_book_default_row_and_shows_effective_tracks_and_numeric_bgm_level(self):
        self.assertIn("if (defaultRow?.parentElement === statusGrid) defaultRow.remove();", self.adapter)
        self.assertIn("row.innerHTML = '<span>Effective track(s)</span><b id=\"mixEffectiveTracks\">Loading saved tracks…</b>';", self.adapter)
        self.assertIn("setText('mixEffectiveTracks', effectiveLabel)", self.adapter)
        self.assertIn("setText('mixBgmVolumeValue',", self.adapter)
        self.assertIn("BGM level (0–50%)", self.adapter)
        self.assertIn("const effectiveTrackPaths = chapterBased", self.adapter)

    def test_chapter_and_cue_saves_serialize_and_preserve_newer_drafts(self):
        self.assertIn("if (chapterBgmSavePromise) return chapterBgmSavePromise;", self.adapter)
        self.assertIn("if (cueSavePromise) return cueSavePromise;", self.adapter)
        self.assertIn("pendingCueAssignments[slot] === path", self.adapter)
        self.assertIn("while (Object.keys(pendingCueAssignments).length)", self.adapter)
        self.assertIn("chapterBgmDraftDirty = true;", self.adapter)

    def test_selected_cue_playback_and_explicit_save_are_interactive(self):
        for control in ('playSelectedCue', 'pauseSelectedCue', 'replaySelectedCue', 'saveCueChanges'):
            self.assertIn(f'id="{control}"', self.sound_markup)
            self.assertIn(f"soundButton.id === '{control}'", self.adapter)
        self.assertIn("pendingCueAssignments[pendingCueSlot] = path", self.adapter)
        self.assertIn("await call('sound.cues.save', {slot, path:path || null})", self.adapter)
        self.assertIn("It will save automatically; use Save Cue Changes to save now.", self.adapter)
        self.assertIn("function scheduleCueAutoSave()", self.adapter)
        self.assertIn("Clear All is staged. Press Save Cue Changes to remove the three saved assignments.", self.adapter)
        self.assertIn("Unsaved cue changes — saving automatically shortly. Use Save Cue Changes to save now.", self.adapter)
        self.assertIn("soundPreviewKind === 'cue' && soundPreviewPath === selectedCuePath", self.adapter)
        self.assertIn("soundPreviewKind === 'music' && soundPreviewPath === track.path", self.adapter)

    def test_narration_and_cue_levels_are_saved_and_used_in_rendering(self):
        for control in ('narrationVolume', 'cueVolume', 'mixNarrationSignal'):
            self.assertIn(f'id="{control}"', self.sound_markup)
        self.assertIn('state["narration_audio_volume"] = narration_volume', self.host)
        self.assertIn('state["sound_cue_volume"] = cue_volume', self.host)
        self.assertIn("narration_volume=self.narration_volume", self.manager)
        self.assertIn("cue_audio_volume=self.cue_audio_volume", self.manager)
        self.assertIn("narration_gain = max(0.0, min(1.0, float(narration_volume)))", self.assembler)
        self.assertIn("cue_gain = max(0.0, min(0.50, float(cue_audio_volume)))", self.assembler)
        self.assertIn("narration_volume=float(state.get(\"narration_audio_volume\")", self.host)
        self.assertIn("cue_audio_volume=float(state.get(\"sound_cue_volume\")", self.preview)
        flush_helper = self._extract_js_function(self.adapter, "async function flushSoundDesignState(")
        self.assertIn("await saveCurrentChapterBgmDraft();", flush_helper)
        self.assertIn("await savePendingCueChanges();", flush_helper)
        self.assertIn("await saveSoundMixLevels(true);", flush_helper)
        self.assertLess(flush_helper.index("await savePendingCueChanges();"), flush_helper.index("await saveSoundMixLevels(true);"))

    def test_cue_import_rejects_long_clips_and_keeps_music_import_available(self):
        start = self.host.index("    def _sound_import(")
        end = self.host.index("    def _sound_assign(", start)
        method = self.host[start:end]
        self.assertIn("duration_seconds > 5.0", method)
        self.assertIn("import longer music into the Music Library and assign it as BGM", method)
        self.assertIn("target_kind: soundButton.id === 'importMusicTracks' ? 'music' : 'cue'", self.adapter)


    def test_bundled_cue_roles_are_normalized_and_not_shown_as_music(self):
        self.assertIn('role = "cue" if role_value in {"cue", "opening", "page", "ending", "closing", "chapter"} else role_value', self.host)
        self.assertIn('metadata.get("role") or bundled_entry.get("type") or ""', self.host)
        self.assertIn("role = audio_asset_role(resolved)", self.host)
        self.assertIn("Skipping audio asset with unreadable metadata", self.host)
        self.assertIn("function isCueSoundAsset(track)", self.adapter)
        self.assertIn("const isCue = isCueSoundAsset(t);", self.adapter)
        self.assertIn("return isCue && (!query || text.includes(query))", self.adapter)

    def test_returning_to_same_bgm_restores_saved_book_default_track(self):
        start = self.host.index("    def _sound_chapter_bgm_save(")
        end = self.host.index("    def _sound_cues_get(", start)
        method = self.host[start:end]
        self.assertIn('preferred = str(state.get("background_audio_preferred_path") or state.get("background_audio_path") or "").strip()', method)
        self.assertIn("if master_enabled and preferred and preferred in catalog_paths and Path(preferred).is_file():", method)
        self.assertIn('state["background_audio_path"] = preferred', method)


    def test_saved_sound_readouts_reject_wrong_asset_roles(self):
        start = self.host.index("    def _sound_chapter_bgm_get(")
        end = self.host.index("    def _sound_chapter_bgm_save(", start)
        chapter_read = self.host[start:end]
        self.assertIn('str(track.get("role") or "music").casefold() != "cue"', chapter_read)
        self.assertIn("default_available = bool(default_track", chapter_read)
        cue_start = self.host.index("    def _sound_cues_get(")
        cue_end = self.host.index("    def _sound_cues_save(", cue_start)
        cue_read = self.host[cue_start:cue_end]
        self.assertIn('role = str((row or {}).get("role") or persisted_role or "").casefold()', cue_read)
        self.assertIn('available = bool(resolved.is_file() and role == "cue")', cue_read)
        self.assertIn('"path": str(resolved) if resolved.is_file() else path', cue_read)
        self.assertIn('"missing": not available', cue_read)

    def test_cue_assignment_rejects_music_and_long_assets(self):
        start = self.host.index("    def _sound_cues_save(")
        end = self.host.index("    def _sound_cues_clear(", start)
        method = self.host[start:end]
        self.assertIn('str(row.get("role") or "music").casefold() != "cue"', method)
        self.assertIn("if float(duration_seconds) > 5.0:", method)

    def test_cue_assets_cannot_be_used_as_book_or_chapter_bgm(self):
        self.assertIn('selected_row.get("role") or "music").casefold() == "cue"', self.host)
        self.assertIn('str(row.get("role") or "music").casefold() == "cue"', self.host)
        self.assertIn("function soundAssetRole(track)", self.adapter)
        self.assertIn("function isCueSoundAsset(track)", self.adapter)
        self.assertIn("function isMusicSoundAsset(track)", self.adapter)
        self.assertIn("const role = soundAssetRole(t);", self.adapter)
        self.assertIn("const matchesMusicType = role !== 'cue';", self.adapter)
        self.assertIn("const allMusicTracks = sounds.filter(track => isMusicSoundAsset(track));", self.adapter)
        self.assertIn("const isCue = isCueSoundAsset(t);", self.adapter)

    def test_selected_music_track_does_not_replace_saved_default_on_handoff(self):
        start = self.adapter.index("} else if (soundButton.id === 'applySoundToProduction')")
        end = self.adapter.index("} else if (soundButton.id === 'saveChapterBgm')", start)
        handoff = self.adapter[start:end]
        self.assertIn("await flushSoundDesignState();", handoff)
        flush_helper = self._extract_js_function(self.adapter, "async function flushSoundDesignState(")
        self.assertIn("await saveSoundMixLevels(true);", flush_helper)
        self.assertIn("path:chapterBased ? '' : (chapterBgmState.default_path || '')", self.adapter)
        self.assertNotIn("selectedSoundPath || chapterBgmState.default_path", handoff)

    def test_clear_all_cues_requires_explicit_save(self):
        start = self.adapter.index("} else if (soundButton.id === 'clearAllCues')")
        end = self.adapter.index("} else if (soundButton.id === 'previewCueSequence')", start)
        handler = self.adapter[start:end]
        self.assertIn("for (const slot of ['opening','chapter','closing']) pendingCueAssignments[slot] = null;", handler)
        self.assertIn("Choose Save Cue Changes", handler)
        self.assertNotIn("call('sound.cues.clear')", handler)


    def test_music_and_chapter_bgm_use_shared_category_and_source_normalization(self):
        self.assertIn("function soundCategoryGroup(track)", self.adapter)
        self.assertIn("const categoryGroup = soundCategoryGroup;", self.adapter)
        self.assertIn("function chapterMusicCategoryGroup(track) { return soundCategoryGroup(track); }", self.adapter)
        self.assertIn("function soundSourceKind(track)", self.adapter)
        self.assertIn("const sourceKind = soundSourceKind(t);", self.adapter)
        self.assertIn("const sourceKind = soundSourceKind(track);", self.adapter)
        self.assertIn("sourceKind === 'built-in'", self.adapter)
        self.assertIn("sourceKind === 'imported'", self.adapter)
        for alias in ("fantasy-adventure", "battle-warfare", "calm-narration", "others"):
            self.assertIn("'" + alias + "'", self.adapter)

    def test_chapter_and_cue_edits_autosave_without_overwriting_newer_drafts(self):
        self.assertIn("function markChapterBgmDraftDirty()", self.adapter)
        self.assertIn("function scheduleChapterBgmAutoSave()", self.adapter)
        self.assertIn("chapterBgmDraftRevision", self.adapter)
        self.assertIn("if (revision !== chapterBgmDraftRevision) continue;", self.adapter)
        self.assertIn("function scheduleCueAutoSave()", self.adapter)
        self.assertIn("while (Object.keys(pendingCueAssignments).length)", self.adapter)
        self.assertIn("pendingCueAssignments[slot] === path", self.adapter)
        self.assertIn("cueClearAllStaged = true;", self.adapter)

    def test_sound_manifest_queue_persists_latest_slider_values(self):
        self.assertIn("async function saveSoundManifest(overrides = {})", self.adapter)
        self.assertIn("while (savedRevision !== soundManifestSaveRevision)", self.adapter)
        self.assertIn("async function saveSoundMixLevels(force = false)", self.adapter)
        self.assertIn("if (revision === mixLevelsRevision)", self.adapter)
        self.assertIn("await saveSoundMixLevels(true);", self.adapter)

    def test_full_book_mix_preview_flushes_current_sound_design_drafts(self):
        start = self.adapter.index("soundButton.id === 'soundPreviewBook'")
        end = self.adapter.index("} catch (err) { message", start)
        preview = self.adapter[start:end]
        self.assertIn("await flushSoundDesignState({requireExplicitCueClear:true});", preview)
        self.assertIn("async function flushSoundDesignState", self.adapter)
        self.assertIn("if (requireExplicitCueClear && cueClearAllStaged)", self.adapter)

    def test_active_music_and_cue_preview_levels_follow_volume_sliders(self):
        self.assertIn("soundPreviewKind === 'music'", self.adapter)
        self.assertIn("soundPreviewAudio.volume = Math.max(0, Math.min(0.50, Number(e.target.value || 0) / 100));", self.adapter)
        self.assertIn("['cue','cue-sequence'].includes(soundPreviewKind)", self.adapter)

    def test_host_normalizes_music_categories_and_clears_inactive_book_default(self):
        catalogue_start = self.host.index("    def _sound_catalog(")
        import_start = self.host.index("    def _sound_import(", catalogue_start)
        catalogue = self.host[catalogue_start:import_start]
        for alias in ("fantasy-adventure", "battle-warfare", "calm-narration"):
            self.assertIn('"' + alias + '"', catalogue)
        import_end = self.host.index("    def _sound_assign(", import_start)
        import_method = self.host[import_start:import_end]
        self.assertIn('if target_kind not in {"music", "cue"}:', import_method)
        self.assertIn("category not in MUSIC_CATEGORY_LABELS", import_method)
        strategy_start = self.host.index("    def _sound_chapter_bgm_save(")
        strategy_end = self.host.index("    def _sound_cues_get(", strategy_start)
        strategy = self.host[strategy_start:strategy_end]
        self.assertIn('state["background_audio_path"] = ""', strategy)
        self.assertIn('state["background_audio_preferred_path"] = preferred', strategy)

    def test_production_summary_counts_unique_explicit_chapter_bgm_tracks(self):
        self.assertIn('"explicit_chapter_track_count": len({', self.host)
        self.assertIn("const explicitChapterTrackCount = Number(chapterBgmState.explicit_chapter_track_count ??", self.adapter)
        self.assertIn("'Chapter-Based BGM · ' + explicitChapterTrackCount + ' unique assigned track'", self.adapter)
        self.assertIn("'Voice Only · BGM disabled'", self.adapter)
        self.assertIn("defaultAvailable && defaultTrack", self.adapter)


    def test_book_default_selection_stays_preference_only_in_chapter_based_strategy(self):
        from app.ui.premium_v2_host import _sound_manifest_bgm_paths

        track = "C:/Audio Library/BookTheme.wav"
        chapter_state = {
            "chapter_bgm_strategy": "custom",
            "background_audio_path": "",
            "background_audio_preferred_path": "C:/Audio Library/OlderTheme.wav",
            "chapter_bgm_overrides": {"2": {"rule": "custom", "path": "C:/Audio Library/Chapter.wav"}},
        }
        active, preferred = _sound_manifest_bgm_paths(chapter_state, track, True)
        self.assertEqual(active, "")
        self.assertEqual(preferred, track)

        same_state = {**chapter_state, "chapter_bgm_strategy": "same"}
        active, preferred = _sound_manifest_bgm_paths(same_state, track, True)
        self.assertEqual(active, track)
        self.assertEqual(preferred, track)

        active, preferred = _sound_manifest_bgm_paths(chapter_state, "", False)
        self.assertEqual(active, "")
        self.assertEqual(preferred, chapter_state["background_audio_preferred_path"])

        method_start = self.host.index("    def _sound_save_manifest(")
        method_end = self.host.index("    def _sound_chapter_bgm_get(", method_start)
        method = self.host[method_start:method_end]
        self.assertIn("_sound_manifest_bgm_paths(state, manifest_path, enabled)", method)
        self.assertIn('"background_audio_path": active_bgm_path', method)
        self.assertIn('"background_audio_preferred_path": preferred_bgm_path', method)


    def test_cue_cards_use_readable_styles_and_accessible_selection_state(self):
        self.assertIn(".cue-grid .cue-card{", self.html)
        self.assertIn("overflow-wrap:anywhere", self.html)
        self.assertIn("class=\"cue-card card", self.adapter)
        self.assertIn("classList.toggle('selected', selected)", self.adapter)
        self.assertIn("aria-pressed", self.adapter)
        self.assertNotIn('class="cue-track card"', self.adapter)


    def test_music_library_selected_track_panel_and_preview_follow_current_track(self):
        selection_start = self.adapter.index("if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click'")
        selection_end = self.adapter.index("message('Selected ' + (track.title || 'sound track')", selection_start)
        selection = self.adapter[selection_start:selection_end]
        self.assertIn("const track = sounds.find(item => String(item.path || '') === requestedPath);", selection)
        self.assertIn("track.category_label || track.category || 'Others'", selection)
        self.assertIn("track.source || 'Local catalogue'", selection)
        self.assertIn("track.format || 'Audio'", selection)
        self.assertIn("(soundPreviewKind !== 'music' || soundPreviewPath !== selectedSoundPath)", selection)
        self.assertIn("stopSoundPreview();", selection)
        cue_start = self.adapter.index("const cueTrack = e.target.closest('#cueGrid [data-cue-path]')")
        cue_end = self.adapter.index("const soundButton = e.target.closest", cue_start)
        cue_selection = self.adapter[cue_start:cue_end]
        self.assertIn("(soundPreviewKind !== 'cue' || soundPreviewPath !== String(path))", cue_selection)
        self.assertIn("stopSoundPreview();", cue_selection)
        start = self.adapter.index("} else if (soundButton.id === 'previewSelectedTrack')")
        end = self.adapter.index("} else if (soundButton.id === 'setBookDefaultTrack')", start)
        preview = self.adapter[start:end]
        self.assertIn("soundPreviewKind === 'music' && soundPreviewPath === track.path", preview)
        self.assertIn("if (soundPreviewAudio.paused) await soundPreviewAudio.play();", preview)
        self.assertIn("else soundPreviewAudio.pause();", preview)
        self.assertIn("createSoundPreview(track.path, 'music'", preview)
        self.assertIn("soundPreviewAudio = audio;", self.adapter)
        self.assertIn("soundPreviewKind = kind;", self.adapter)
        self.assertIn("soundPreviewPath = String(rawPath || '');", self.adapter)

    def test_missing_selected_music_or_cue_clears_only_its_stale_preview(self):
        refresh_music_start = self.adapter.index("async function refreshSounds()")
        refresh_music_end = self.adapter.index("async function refreshSoundCues()", refresh_music_start)
        refresh_music = self.adapter[refresh_music_start:refresh_music_end]
        self.assertIn("const selectedMusicTrack = selectedSoundPath", refresh_music)
        self.assertIn("isMusicSoundAsset(track)", refresh_music)
        self.assertIn("if (!selectedMusicTrack)", refresh_music)
        self.assertIn("The previously selected music track is no longer available", refresh_music)
        self.assertIn("$('previewSelectedTrack').disabled = true;", refresh_music)
        refresh_cue_start = self.adapter.index("async function refreshSoundCues()")
        refresh_cue_end = self.adapter.index("function chapterMusicCategoryGroup", refresh_cue_start)
        refresh_cues = self.adapter[refresh_cue_start:refresh_cue_end]
        self.assertIn("isCueSoundAsset(track)", refresh_cues)
        self.assertIn("The previously selected cue is no longer available", refresh_cues)
        self.assertIn("soundPreviewKind === 'cue' && soundPreviewPath === stalePath", refresh_cues)

    def test_local_preview_media_error_releases_only_the_failed_audio_instance(self):
        start = self.adapter.index("function createSoundPreview(")
        end = self.adapter.index("async function saveCurrentChapterBgmDraft", start)
        preview = self.adapter[start:end]
        error_handler = preview[preview.index("audio.onerror ="):]
        self.assertIn("if (soundPreviewAudio === audio)", error_handler)
        self.assertIn("soundPreviewAudio = null;", error_handler)
        self.assertIn("soundPreviewKind = null;", error_handler)
        self.assertIn("soundPreviewPath = null;", error_handler)
        self.assertIn("message('The selected local audio file could not be played in the embedded preview.', true);", error_handler)

    def test_chapter_bgm_scroll_and_selected_track_panel_readability(self):
        self.assertIn(".chapter-bgm-list{display:grid;align-content:start;gap:6px;max-height:620px;overflow:auto}", self.html)
        self.assertIn("'#sound #chapterBgmSelectedTrackPanel .chapter-bgm-select-eyebrow{color:#e6c85f}'", self.adapter)
        self.assertIn("'#sound #chapterBgmSelectedTrackPanel h2{font-size:1.15rem;line-height:1.35;margin:10px 0}'", self.adapter)
        self.assertIn("Candidate only — press Select to save it for Chapter ", self.adapter)


    def test_master_bgm_slider_hydrates_saved_value_without_overwriting_active_edit(self):
        start = self.adapter.index("function renderSoundMixSummary()")
        end = self.adapter.index("function renderChapterBgm()", start)
        summary = self.adapter[start:end]
        self.assertIn("const bgmLevelInput = $('advancedMusicVolume');", summary)
        self.assertIn("const storedBgm = Math.max(0, Math.min(0.50, Number(chapterBgmState.default_volume ?? 0.18)));", summary)
        self.assertIn("document.activeElement !== bgmLevelInput", summary)
        self.assertIn("bgmLevelInput.value = String(Math.round(storedBgm * 100));", summary)
        self.assertIn("setText('advancedMusicVolumeValue', Math.round(bgmLevel * 100) + '%');", summary)
        self.assertIn("await saveSoundMixLevels(true);", self.adapter)


    def test_mix_summary_uses_live_master_level_only_for_same_bgm_strategy(self):
        start = self.adapter.index("function renderSoundMixSummary()")
        end = self.adapter.index("function renderChapterBgm()", start)
        summary = self.adapter[start:end]
        self.assertIn("const bgmLevel = Math.max(0, Math.min(0.50, Number(bgmLevelInput?.value ?? storedBgm * 100) / 100));", summary)
        self.assertIn("? activeChapterRows.map(item => Number(item.volume ?? chapterBgmState.default_volume ?? 0.18))", summary)
        self.assertIn(": (hasActiveBgm ? [bgmLevel] : [])", summary)
        self.assertIn("setText('mixBgmVolumeValue',", summary)
        self.assertIn("musicWidth = masterEnabled && hasActiveBgm", summary)

    def test_zero_cue_level_does_not_add_silent_audio_duration(self):
        self.assertIn("if cue is None or cue_gain <= 1e-9:", self.assembler)
        self.assertIn("return None", self.assembler[self.assembler.index("def apply_cue_level"):self.assembler.index("# Real local audio only", self.assembler.index("def apply_cue_level"))])


if __name__ == "__main__":
    unittest.main()
