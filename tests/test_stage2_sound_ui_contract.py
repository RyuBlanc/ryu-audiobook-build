"""Stage 2 regression contracts for the approved Sound Design UI."""

from pathlib import Path
import re
import unittest


class Stage2SoundDesignUiContractTests(unittest.TestCase):
    def setUp(self):
        self.html = Path("assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.adapter = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
