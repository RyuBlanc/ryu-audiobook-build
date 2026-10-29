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
        for field in ("mixBgmStatus", "mixDefaultTrack", "mixStrategy", "mixOverrides",
                      "mixOpening", "mixChapterCue", "mixClosing", "soundPreviewPath",
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
        self.assertIn("metadata?.category", self.adapter)

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
        self.assertIn("const soundTab = e.target.closest('#sound .sound-tabs [data-sound-tab]');", self.adapter)
        self.assertIn("document.querySelectorAll('#sound .sound-view[data-sound-view]')", self.adapter)
        self.assertIn("if (nextView === 'music') await refreshSounds();", self.adapter)
        self.assertIn("else if (nextView === 'chapters') await refreshChapterBgm();", self.adapter)
        self.assertIn("else if (nextView === 'cues') await refreshSoundCues();", self.adapter)

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

    def test_selected_cue_playback_and_explicit_save_are_interactive(self):
        for control in ('playSelectedCue', 'pauseSelectedCue', 'replaySelectedCue', 'saveCueChanges'):
            self.assertIn(f'id="{control}"', self.sound_markup)
            self.assertIn(f"soundButton.id === '{control}'", self.adapter)
        self.assertIn("pendingCueAssignments[pendingCueSlot] = path", self.adapter)
        self.assertIn("await call('sound.cues.save', {slot, path:path || null})", self.adapter)
        self.assertIn("Use Save Cue Changes to persist this assignment.", self.adapter)
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
        self.assertIn('role = "cue" if role_value in {"opening", "page", "ending", "closing", "chapter"} else role_value', self.host)
        self.assertIn("const isCue = String(t.role || t.metadata?.role || 'music').toLowerCase() === 'cue';", self.adapter)
        self.assertIn("return isCue && (!query || text.includes(query))", self.adapter)

    def test_returning_to_same_bgm_restores_saved_book_default_track(self):
        start = self.host.index("    def _sound_chapter_bgm_save(")
        end = self.host.index("    def _sound_cues_get(", start)
        method = self.host[start:end]
        self.assertIn('preferred = str(state.get("background_audio_path") or state.get("background_audio_preferred_path") or "").strip()', method)
        self.assertIn("if master_enabled and preferred and preferred in catalog_paths and Path(preferred).is_file():", method)
        self.assertIn('state["background_audio_path"] = preferred', method)

    def test_cue_assignment_rejects_music_and_long_assets(self):
        start = self.host.index("    def _sound_cues_save(")
        end = self.host.index("    def _sound_cues_clear(", start)
        method = self.host[start:end]
        self.assertIn('str(row.get("role") or "music").casefold() != "cue"', method)
        self.assertIn("if float(duration_seconds) > 5.0:", method)

    def test_cue_assets_cannot_be_used_as_book_or_chapter_bgm(self):
        self.assertIn('selected_row.get("role") or "music").casefold() == "cue"', self.host)
        self.assertIn('selected_row.get("role") or "music").casefold() == "cue"', self.host)
        self.assertIn('str(row.get("role") or "music").casefold() == "cue"', self.host)
        self.assertIn("String(t.role || t.metadata?.role || 'music').toLowerCase() !== 'cue'", self.adapter)
        self.assertIn("const isCue = String(t.role || t.metadata?.role || 'music').toLowerCase() === 'cue';", self.adapter)

    def test_selected_music_track_does_not_replace_saved_default_on_handoff(self):
        start = self.adapter.index("} else if (soundButton.id === 'applySoundToProduction')")
        end = self.adapter.index("} else if (soundButton.id === 'saveChapterBgm')", start)
        handoff = self.adapter[start:end]
        self.assertIn("path:chapterBased ? '' : (chapterBgmState.default_path || '')", handoff)
        self.assertNotIn("selectedSoundPath || chapterBgmState.default_path", handoff)

    def test_clear_all_cues_requires_explicit_save(self):
        start = self.adapter.index("} else if (soundButton.id === 'clearAllCues')")
        end = self.adapter.index("} else if (soundButton.id === 'previewCueSequence')", start)
        handler = self.adapter[start:end]
        self.assertIn("for (const slot of ['opening','chapter','closing']) pendingCueAssignments[slot] = null;", handler)
        self.assertIn("Choose Save Cue Changes", handler)
        self.assertNotIn("call('sound.cues.clear')", handler)

    def test_zero_cue_level_does_not_add_silent_audio_duration(self):
        self.assertIn("if cue is None or cue_gain <= 1e-9:", self.assembler)
        self.assertIn("return None", self.assembler[self.assembler.index("def apply_cue_level"):self.assembler.index("# Real local audio only", self.assembler.index("def apply_cue_level"))])

    def test_chapter_bgm_filters_selected_track_panel_and_explicit_confirmation_are_connected(self):
        for control in ("chapterBgmSearch", "chapterBgmSourceFilter", "chapterBgmCategoryFilter",
                        "chapterSelectedTrackTitle", "chapterSelectedTrackMeta", "chapterSavedAssignment",
                        "confirmChapterTrackSelection", "chapterSelectStatus"):
            self.assertIn(f'id="{control}"', self.sound_markup)
        for source in ("All", "Built-in", "Imported", "Fantasy adventure", "Battle &amp; warfare",
                       "Mystery", "Horror", "Romance", "Sci-fi", "Calm narration", "Others"):
            self.assertIn(source, self.sound_markup)
        self.assertIn("soundMusicCategoryGroup(track)", self.adapter)
        self.assertIn("soundMusicCategoryGroup(t) === selectedMusicCategory", self.adapter)
        self.assertIn("categoryFilter === 'all' || soundMusicCategoryGroup(track) === categoryFilter", self.adapter)
        self.assertIn("chapterBgmCandidateConfirmed = true;", self.adapter)
        self.assertIn("await saveCurrentChapterBgmDraft(true);", self.adapter)
        self.assertIn("chapterBgmCandidateConfirmed) {", self.adapter)
        self.assertIn("Candidate only. Select confirms and saves this chapter assignment.", self.adapter)
        self.assertRegex(self.html, r"\.chapter-bgm-editor\{[^}]*overflow-y:auto")
        self.assertRegex(self.html, r"\.chapter-track-picker\{[^}]*overflow-y:auto")

    def test_selecting_chapter_music_candidate_does_not_mark_saved_settings_dirty(self):
        start = self.adapter.index("const chapterTrack = e.target.closest('#chapterTrackPicker [data-chapter-track]');")
        end = self.adapter.index("if (e.target.closest('#confirmChapterTrackSelection'))", start)
        candidate_handler = self.adapter[start:end]
        self.assertIn("selectedBgmTrackPath = chapterTrack.dataset.chapterTrack;", candidate_handler)
        self.assertIn("chapterBgmCandidateConfirmed = false;", candidate_handler)
        self.assertNotIn("chapterBgmDraftDirty = true;", candidate_handler)
        self.assertIn("Candidate only. Select confirms and saves this chapter assignment.", candidate_handler)
        self.assertIn("if (rule === 'custom' && selectedBgmTrackPath !== (savedCurrent.path || null) && !chapterBgmCandidateConfirmed)", self.adapter)

    def test_mix_summary_uses_selected_track_and_real_saved_state_labels(self):
        mix = self.sound_markup[self.sound_markup.index('data-sound-view="mix"'):]
        self.assertIn('<span>Selected book track</span>', mix)
        self.assertIn('<span>Next chapter cue</span>', mix)
        self.assertIn('id="mixSavedState"', mix)
        self.assertNotIn('<span>Book default</span>', mix)
        self.assertNotRegex(mix, r"Scene Cue|Scene transition cue")
        self.assertIn('id="mixBgmVolume"', mix)
        self.assertIn('max="50"', mix[mix.index('id="mixBgmVolume"') - 100:mix.index('id="mixBgmVolume"') + 150])
        self.assertIn("setText('mixSavedState', anySoundDraft ? 'Unsaved changes' : (chapterBgmState.last_saved_at ? 'Saved' : 'Not saved'));", self.adapter)


    def test_production_summary_counts_unique_chapter_tracks_and_no_bgm_chapters(self):
        self.assertIn("const uniqueChapterTracks = [...new Set(activeChapterRows.map(item => String(item.path || '')).filter(Boolean))];", self.adapter)
        self.assertIn("const noBgmChapterCount = rowsCountForChapterSummary(overrides, chapterBgmState.chapters || chapters);", self.adapter)
        self.assertIn("'Chapter-Based BGM (' + uniqueChapterTracks.length + ' unique tracks; ' + noBgmChapterCount + ' No BGM chapters)'", self.adapter)
        self.assertIn("Not used · Chapter-Based BGM", self.adapter)
        self.assertIn('id="mixBgmVolumeHelp"', self.sound_markup)
        self.assertIn("mixBgmInput.disabled = chapterBased", self.adapter)
        self.assertIn("Not applied in Chapter-Based BGM. Use the chapter-level volume for each assigned track.", self.adapter)


    def test_cue_autosave_is_debounced_serialized_and_preserves_newer_edits(self):
        self.assertIn("function scheduleCueAutosave(delay = 650)", self.adapter)
        self.assertIn("if (cueSavePromise) {", self.adapter)
        self.assertIn("cueSaveQueued = true;", self.adapter)
        self.assertIn("pendingCueAssignments[slot] === path", self.adapter)
        self.assertIn("scheduleCueAutosave();", self.adapter)
        self.assertIn("Cue changes autosaved.", self.adapter)
        self.assertIn("Save failed. Unsaved cue changes have been retained; retry manually.", self.adapter)
        clear_start = self.adapter.index("else if (soundButton.id === 'clearAllCues')")
        clear_end = self.adapter.index("else if (soundButton.id === 'previewCueSequence')", clear_start)
        self.assertIn("scheduleCueAutosave();", self.adapter[clear_start:clear_end])
        save_start = self.adapter.index("else if (soundButton.id === 'saveCueChanges')")
        save_end = self.adapter.index("else if (soundButton.id === 'playSelectedCue')", save_start)
        self.assertIn("clearTimeout(cueSaveTimer)", self.adapter[save_start:save_end])
        self.assertIn("savePendingCueChanges({source:'manual'})", self.adapter[save_start:save_end])

    def test_generate_bgm_voice_only_toggle_is_connected_to_saved_sound_manifest(self):
        self.assertIn('id="generate"', self.html)
        generate = self.html[self.html.index('<section class="page" id="generate">'):self.html.index('<section class="page" id="player">')]
        self.assertIn('data-bgm-enabled="true"', generate)
        self.assertIn('data-bgm-enabled="false"', generate)
        self.assertIn("e.target.closest('#sound [data-bgm-enabled], #generate [data-bgm-enabled]')", self.adapter)
        self.assertIn("document.querySelectorAll('#sound [data-bgm-enabled], #generate [data-bgm-enabled]')", self.adapter)
        start = self.adapter.index("const bgmMasterToggle = e.target.closest")
        end = self.adapter.index("const chapterBgmItem =", start)
        handler = self.adapter[start:end]
        self.assertIn("await call('sound.save_manifest'", handler)
        self.assertIn("manifest.updated_at", handler)
        self.assertIn("Voice Only saved. Background music and all story cues are disabled", handler)
        self.assertIn("await refreshSoundCues();", handler)

    def test_production_handoff_refuses_unsaved_sound_state_and_confirms_manifest(self):
        start = self.adapter.index("} else if (soundButton.id === 'applySoundToProduction')")
        end = self.adapter.index("} else if (soundButton.id === 'saveChapterBgm')", start)
        handoff = self.adapter[start:end]
        self.assertIn("await savePendingCueChanges({source:'manual'});", handoff)
        self.assertIn("cueChangesDirty || chapterBgmDraftDirty || mixLevelsDirty", handoff)
        self.assertIn("The backend did not confirm saving the sound configuration.", handoff)
        self.assertIn("manifest.updated_at", handoff)
        self.assertLess(handoff.index("manifest.updated_at"), handoff.index("document.querySelector('[data-page=\"generate\"]')?.click();"))


if __name__ == "__main__":
    unittest.main()
