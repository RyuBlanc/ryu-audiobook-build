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
            "renderedMusicRows",
            "Packaged starter music is missing from the Built-in filter.",
        ):
            self.assertIn(required, script)
        self.assertIn(
            'const builtInSource = document.querySelector(\'#soundSourceFilter [data-source="built-in"]\');',
            script,
        )
        self.assertIn("if (musicButtons().length === 0)", script)

    def test_packaged_driver_waits_for_rendered_source_filter_results_not_only_button_state(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        self.assertIn('rows.every(button => rowText(button).includes("Bundled with application"))', script)
        self.assertIn('rows.every(button => rowText(button).includes("Imported locally"))', script)
        self.assertIn('rows.some(text => text.includes("Bundled with application"))', script)
        self.assertIn('rows.some(text => text.includes("Imported locally"))', script)
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
