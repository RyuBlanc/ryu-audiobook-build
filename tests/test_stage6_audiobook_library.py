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

    def test_stage3_keeps_stage55_project_position_acceptance(self):
        self.assertIn("stage55_audiobooks_real_playback_chapter_seek_and_position", self.packaged_js)
        self.assertNotIn("originating audiobook position remains persisted", self.packaged_js)

if __name__ == "__main__":
    unittest.main()
