"""Packaged Windows Sound Design acceptance gate contract tests."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage2PackagedSoundUiAcceptanceTests(unittest.TestCase):
    def test_acceptance_hook_is_opt_in_and_attached_to_real_frontend_readiness(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('self._start_sound_ui_acceptance()', host)
        self.assertIn('RYU_SOUND_UI_ACCEPTANCE_SCRIPT', host)
        self.assertIn('RYU_SOUND_UI_ACCEPTANCE_CONFIG', host)
        self.assertIn('RYU_SOUND_UI_ACCEPTANCE_MARKER', host)
        self.assertIn('window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__', host)
        self.assertIn('QTimer(self)', host)

    def test_browser_driver_uses_real_music_library_controls_and_bridge(self):
        script = (ROOT / "tests/stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        for required in (
            "window.go('sound')",
            "#sound .sound-tabs [data-sound-tab]",
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
        ):
            self.assertIn(required, script)

    def test_packaged_runner_creates_isolated_project_and_audio_fixtures(self):
        helper = (ROOT / "tests/packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for required in (
            "QSettings",
            "Project(",
            "Chapter(",
            "write_tone_fixture",
            "RYU_SOUND_UI_ACCEPTANCE_SCRIPT",
            "RYU_SOUND_UI_ACCEPTANCE_CONFIG",
            "RYU_SOUND_UI_ACCEPTANCE_MARKER",
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "validate_saved_music_state",
        ):
            self.assertIn(required, helper)

    def test_windows_package_job_runs_the_real_frozen_executable_acceptance(self):
        workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("Run packaged Sound Design Music Library acceptance", workflow)
        self.assertIn("tests\\packaged_sound_ui_acceptance.py", workflow)
        self.assertIn("dist\\Ryu's Audiobook\\Ryu's Audiobook.exe", workflow)
