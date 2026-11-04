"""Stage 6 AB-01 Premium V2 Audiobooks Library regression contracts."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
PACKAGED_PY = ROOT / "tests" / "packaged_sound_ui_acceptance.py"
PACKAGED_JS = ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js"


class Stage6AudiobookLibraryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")
        cls.packaged_py = PACKAGED_PY.read_text(encoding="utf-8")
        cls.packaged_js = PACKAGED_JS.read_text(encoding="utf-8")

    def test_compact_cards_are_responsive_and_bounded_for_ultrawide(self):
        self.assertIn(".audiobook-library-section{width:100%;max-width:1510px", self.html)
        self.assertIn(".audiobook-library-grid{display:grid;grid-template-columns:repeat(auto-fill", self.html)
        self.assertIn("aspect-ratio:2/3", self.html)
        self.assertIn("@media(max-width:650px){.audiobook-library-section", self.html)
        self.assertIn("minmax(0,1fr)", self.html)

    def test_library_only_renders_real_completed_projects_with_output_paths(self):
        renderer = self.adapter[
            self.adapter.index("function renderAudiobookLibrary("):
            self.adapter.index("const voiceLibraryTitles", self.adapter.index("function renderAudiobookLibrary("))
        ]
        self.assertIn("project.completed === true", renderer)
        self.assertIn("typeof project.output_path === 'string'", renderer)
        self.assertIn("project.output_path.trim()", renderer)
        self.assertIn("project.status", renderer)
        self.assertIn("project.cover_path", renderer)
        self.assertIn("applyProjectCovers(container)", renderer)
        self.assertIn("data-audiobook-status", renderer)
        self.assertNotIn("<span class=\"badge\">Ready</span>", renderer)

    def test_open_and_play_are_distinct_and_keep_the_same_player_backend(self):
        self.assertIn("data-open-project-folder", self.adapter)
        self.assertIn("data-play-project-folder", self.adapter)
        self.assertIn("openPlayer(folder, {autoplay:false})", self.adapter)
        self.assertIn("arguments[1]?.autoplay !== false", self.adapter)
        self.assertIn("if (autoplay) await audio.play();", self.adapter)
        self.assertIn("else audio.load();", self.adapter)
        self.assertIn("const data = await call('player.get_active', {folder});", self.adapter)

    def test_open_action_preserves_selected_book_during_metadata_load(self):
        open_start = self.adapter.index("if (button && button.dataset.openProjectFolder)")
        play_start = self.adapter.index("if (button && button.dataset.playProjectFolder)", open_start)
        open_action = self.adapter[open_start:play_start]
        self.assertIn("await openPlayer(folder, {autoplay:false})", open_action)
        self.assertIn("renderAudiobookLibrary(projects)", open_action)
        self.assertNotIn("refreshProjects()", open_action)
        player_start = self.adapter.index("async function openPlayer(")
        player_end = self.adapter.index("const formatTime =", player_start)
        open_player = self.adapter[player_start:player_end]
        self.assertIn("audio.preload = 'metadata'", open_player)
        self.assertIn("else audio.load()", open_player)
        self.assertIn("audio.onloadedmetadata =", open_player)
        self.assertIn("String(playerAudio.dataset?.projectFolder || '') === folder", open_player)
        self.assertIn("else if (!playerAudio.paused) {", open_player)
        self.assertIn("playerAudio.pause();", open_player)
        refresh_start = self.adapter.index("async function refreshProjects()")
        refresh_end = self.adapter.index("const voiceLibraryTitles", refresh_start)
        refresh = self.adapter[refresh_start:refresh_end]
        self.assertIn("if (!playerAudio || !playerAudio.src) clearAudiobookPlayerDisplay();", refresh)

    def test_packaged_open_acceptance_allows_same_book_audio_reuse_without_duplicates(self):
        open_start = self.packaged_js.index('const existingAudioBeforeOpen = latestAcceptanceAudio();')
        open_end = self.packaged_js.index('const firstOpenedData = await invoke("player.get_active"', open_start)
        open_check = self.packaged_js[open_start:open_end]
        self.assertIn("const sameBookAlreadyLoaded = Boolean", open_check)
        self.assertIn("const sameAudioReused = sameBookAlreadyLoaded && audio === existingAudioBeforeOpen", open_check)
        self.assertIn("const newAudioLoaded = !sameBookAlreadyLoaded", open_check)
        self.assertIn("audio.readyState >= 1 && audio.paused", open_check)
        self.assertIn("Open-state diagnostics:", open_check)
    def test_completed_output_validation_and_m4b_derivative_are_preserved(self):
        summary_start = self.host.index("def _project_summary(")
        player_start = self.host.index("def _player_get_active(")
        summary = self.host[summary_start:player_start]
        player_end = self.host.index("def _player_position_save(", player_start)
        player = self.host[player_start:player_end]
        self.assertIn("output.is_file()", summary)
        self.assertIn("output.stat().st_size > 0", summary)
        self.assertIn('state.get("status") or ""', summary)
        self.assertIn('"completed": bool(completed)', summary)
        self.assertIn('"output_path": str(output) if valid_output and output else None', summary)
        self.assertIn("output = Path(output_value).expanduser() if output_value else None", player)
        self.assertIn("if not output or not output.is_file() or output.stat().st_size <= 0:", player)
        self.assertIn("prepare_audiobook_playback_source(output)", player)
        self.assertIn('"output_path": str(output.resolve())', player)
        self.assertIn('"chapters": chapters', player)

    def test_frozen_windows_acceptance_uses_two_real_completed_m4b_books(self):
        compile(self.packaged_py, str(PACKAGED_PY), "exec")
        self.assertIn("def create_stage6_audiobook_library_fixtures", self.packaged_py)
        self.assertIn("assemble_m4b(", self.packaged_py)
        self.assertIn('"status": "completed"', self.packaged_py)
        self.assertIn('"audiobook_library_fixtures": stage6_audiobook_fixtures', self.packaged_py)
        for marker in (
            "stage6_audiobooks_compact_multiple_real_output_cards",
            "stage6_audiobooks_open_loads_correct_book_paused",
            "stage6_audiobooks_play_action_starts_real_audio",
            "stage6_audiobooks_switch_preserves_project_output_identity",
            "stage6_player_full_controls_actual_audio",
            "stage6_player_seek_and_time_display",
            "stage6_player_volume_and_rate_affect_audio",
            "stage6_player_15_second_seek_clamps",
            "stage6_chapter_select_seeks_to_embedded_marker",
            "stage6_chapter_playhead_highlight_tracks_boundaries",
            "stage6_previous_next_chapter_navigation",
            "stage6_switching_book_clears_previous_chapter_selection",
            "stage6_mini_player_shares_full_player_audio_session",
            "stage6_chapter_keyboard_activation_starts_audio",
            "stage6_chapter_continuous_playback_updates_active_row",
            "stage6_chapter_space_activation_starts_audio",
            "stage6_chapter_embedded_timestamps_visible",
        ):
            self.assertIn(marker, self.packaged_js)



    def test_embedded_chapter_intervals_drive_selected_chapter(self):
        self.assertIn("data-audiobook-chapter-start", self.adapter)
        self.assertIn("data-audiobook-chapter-end", self.adapter)
        self.assertIn("current >= start && current < end", self.adapter)
        self.assertIn("aria-current", self.adapter)
        self.assertIn("syncActivePlayerChapter(playerAudio)", self.adapter)

    def test_chapter_click_and_keyboard_start_actual_media(self):
        start = self.adapter.index("function bindAudiobookPlayerControls()")
        end = self.adapter.index("async function openPlayer(", start)
        controls = self.adapter[start:end]
        self.assertIn("chapter.dataset.audiobookChapterStart", controls)
        self.assertIn("chapter.dataset.audiobookChapterEnd", controls)
        self.assertIn("await audio.play()", controls)
        self.assertIn("event.key !== 'Enter' && event.key !== ' '", controls)

    def test_legacy_player_and_timeline_overrides_removed(self):
        self.assertNotIn("act(openPlayer)", self.adapter)
        self.assertEqual(self.adapter.count("playerTimeline').oninput = () =>"), 1)
        self.assertIn("const playSelectedAudiobook = () =>", self.adapter)

    def test_stale_audio_events_are_ignored_after_book_switch(self):
        start = self.adapter.index("playerAudio = new Audio(data.file_url)")
        end = self.adapter.index("const formatTime =", start)
        handlers = self.adapter[start:end]
        self.assertIn("audio !== playerAudio || audioFolder !== selectedAudiobookFolder", handlers)
        self.assertIn("audio.onseeked = updateAudioPositionUi", handlers)


    def test_chapter_navigation_requires_valid_embedded_intervals(self):
        start = self.adapter.index("function jumpPlayerChapter(")
        end = self.adapter.index("function bindAudiobookPlayerControls(", start)
        navigation = self.adapter[start:end]
        self.assertIn("Number.isFinite(start) && start >= 0", navigation)
        self.assertIn("Number.isFinite(end) && end > start", navigation)
        render_start = self.adapter.index("function renderSelectedAudiobook(")
        render_end = self.adapter.index("function syncActivePlayerChapter(", render_start)
        renderer = self.adapter[render_start:render_end]
        self.assertIn("const hasTimedChapters = chapters.some", renderer)
        self.assertIn("Number.isFinite(end) && end > start", renderer)
        self.assertIn("No chapter metadata available.", renderer)

    def test_player_chapter_transport_is_not_intercepted_by_global_capture_handler(self):
        # The five visible transport buttons are bound directly: rewind,
        # previous chapter, main Play/Pause, next chapter, and forward.
        self.assertNotIn("if (button.closest('#player'))", self.adapter)
        player_start = self.adapter.index("function bindAudiobookPlayerControls(")
        player_end = self.adapter.index("async function openPlayer(", player_start)
        bindings = self.adapter[player_start:player_end]
        self.assertIn("buttons[1].onclick = () => jumpPlayerChapter('previous')", bindings)
        self.assertIn("buttons[3].onclick = () => jumpPlayerChapter('next')", bindings)
        self.assertIn("if ($('mainPlay')) $('mainPlay').onclick = playSelectedAudiobook;", self.adapter)
        self.assertIn("if ($('miniPlay')) $('miniPlay').onclick = playSelectedAudiobook;", self.adapter)

    def test_stage3_keeps_stage55_project_position_acceptance(self):
        self.assertIn("stage55_audiobooks_real_playback_chapter_seek_and_position", self.packaged_js)
        self.assertNotIn("originating audiobook position remains persisted", self.packaged_js)

    def test_chapter_rows_visibly_render_embedded_start_and_end_times(self):
        start = self.adapter.index("function renderSelectedAudiobook(")
        end = self.adapter.index("function syncActivePlayerChapter(", start)
        renderer = self.adapter[start:end]
        self.assertIn("data-audiobook-chapter-time", renderer)
        self.assertIn("formatTime(start)", renderer)
        self.assertIn("formatTime(end)", renderer)
        self.assertIn("Timing unavailable", renderer)

    def test_mini_player_acceptance_uses_visible_dashboard_surface(self):
        self.assertIn('window.go("dashboard")', self.packaged_js)
        self.assertIn("mini-player becomes visible outside the Audiobooks page", self.packaged_js)
        self.assertIn('window.go("player")', self.packaged_js)

    def test_full_and_mini_player_share_selected_audio_toggle_handler(self):
        start = self.adapter.index("const playSelectedAudiobook = () =>")
        end = self.adapter.index("clearAudiobookPlayerDisplay();", start)
        bindings = self.adapter[start:end]
        self.assertIn("if ($('mainPlay')) $('mainPlay').onclick = playSelectedAudiobook;", bindings)
        self.assertIn("if ($('miniPlay')) $('miniPlay').onclick = playSelectedAudiobook;", bindings)
        player_start = self.adapter.index("async function openPlayer(")
        player_end = self.adapter.index("const formatTime =", player_start)
        open_player = self.adapter[player_start:player_end]
        self.assertIn("playerAudio.src === data.file_url", open_player)
        self.assertIn("if (playerAudio.paused) await playerAudio.play(); else playerAudio.pause();", open_player)
    def test_mini_player_uses_rendered_page_state_and_direct_same_audio_toggle(self):
        self.assertIn("function audiobookPageActive()", self.adapter)
        active_start = self.adapter.index("function audiobookPageActive()")
        active_end = self.adapter.index("function syncMiniPlayer()", active_start)
        self.assertNotIn("nav .active", self.adapter[active_start:active_end])
        self.assertIn("audio.dataset.projectFolder = folder;", self.adapter)
        self.assertIn("playerAudio.dataset?.projectFolder === selectedAudiobookFolder", self.adapter)
        self.assertIn("if (current.paused)", self.adapter)
        self.assertIn("current.play().catch", self.adapter)
        self.assertIn("current.pause();", self.adapter)

    def test_player_speed_control_uses_persisted_preference_path(self):
        player_start = self.adapter.index("function bindAudiobookPlayerControls(")
        player_end = self.adapter.index("async function openPlayer(", player_start)
        bindings = self.adapter[player_start:player_end]
        self.assertIn("speedButtons.forEach(button =>", bindings)
        self.assertIn("void applyPlayerRate(rate, true);", bindings)
        self.assertIn("return savePlayerPreferences({player_rate:rate})", self.adapter)

    def test_production_generation_gate_combines_metadata_and_active_jobs(self):
        gate_start = self.adapter.index("function renderProductionMetadataGate(")
        gate_end = self.adapter.index("function populateMetadataHistory(", gate_start)
        gate = self.adapter[gate_start:gate_end]
        self.assertIn("start.disabled = !complete || unsaved || audioActive;", gate)

        generation_start = self.adapter.index("function renderProductionGeneration(")
        generation_end = self.adapter.index("async function refreshChapterBgm(", generation_start)
        generation = self.adapter[generation_start:generation_end]
        self.assertIn("const metadataComplete = project?.metadata_complete === true && !metadataDialogDirty;", generation)
        self.assertIn("fullStart.disabled = anyAudioActive || !metadataComplete;", generation)
        self.assertIn("previewStart.disabled = anyAudioActive;", generation)

        save_start = self.adapter.index("project.metadata.save")
        save_end = self.adapter.index("if (persisted)", save_start)
        save_handler = self.adapter[save_start:save_end]
        self.assertIn("metadata_complete: result.metadata_complete === true", save_handler)
        self.assertIn("metadata_missing_fields: Array.isArray(result.metadata_missing_fields)", save_handler)

        host_start = self.host.index("def _project_metadata_save(")
        host_end = self.host.index("def _active_project(", host_start)
        save_method = self.host[host_start:host_end]
        self.assertIn("missing_metadata = missing_required_metadata_fields(title, persisted_state, narrator_profile)", save_method)
        self.assertIn('"metadata_complete": not missing_metadata', save_method)
        self.assertIn('"metadata_missing_fields": missing_metadata', save_method)

if __name__ == "__main__":
    unittest.main()
