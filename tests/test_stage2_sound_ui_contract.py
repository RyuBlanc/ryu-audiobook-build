"""Stage 2 regression contracts for the approved Sound Design UI."""

from pathlib import Path
import re
import unittest


class Stage2SoundDesignUiContractTests(unittest.TestCase):
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

    def test_voice_only_copy_and_master_toggle_match_saved_generation_contract(self):
        self.assertIn("Narration only; BGM and all story cues are disabled", self.sound_markup)
        self.assertNotIn("Keep narration and story cues only", self.sound_markup)
        self.assertIn("const bgmMasterToggle = e.target.closest('#sound [data-bgm-enabled]');", self.adapter)
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
        self.assertIn("await saveCurrentChapterBgmDraft();\n            await savePendingCueChanges();", self.adapter)

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
        self.assertIn("await saveCurrentChapterBgmDraft();\n            await savePendingCueChanges();", self.adapter)

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
        self.assertIn('str(row.get("role") or "music").casefold() == "cue"', cue_read)

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
        self.assertIn("await saveSoundMixLevels(true);", handoff)
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
        self.assertIn("if (cueClearAllStaged)", preview)
        self.assertIn("await saveCurrentChapterBgmDraft();", preview)
        self.assertIn("await savePendingCueChanges();", preview)
        self.assertIn("await saveSoundMixLevels(true);", preview)

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
        selection_end = self.adapter.index("async function refreshSoundCues()", selection_start)
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

    def test_zero_cue_level_does_not_add_silent_audio_duration(self):
        self.assertIn("if cue is None or cue_gain <= 1e-9:", self.assembler)
        self.assertIn("return None", self.assembler[self.assembler.index("def apply_cue_level"):self.assembler.index("# Real local audio only", self.assembler.index("def apply_cue_level"))])


if __name__ == "__main__":
    unittest.main()
