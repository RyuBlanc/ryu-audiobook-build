from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.tts.cast_provider import CastAwareProvider
from app.tts.generation_mode import narrator_only_for_generation
from app.tts.generator import safe_name
from app.tts.manager import GenerationManager
from app.tts.pacing import append_silence


ROOT = Path(__file__).resolve().parents[1]


def _write_wav(path: Path, frames: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22050)
        output.writeframes(b"\x00\x00" * frames)


def _wav_frame_count(path: Path) -> int:
    with wave.open(str(path), "rb") as source:
        return source.getnframes()


class _UnusedProvider:
    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 2


class ReportedProductionUiRegressionTests(unittest.TestCase):
    def test_chapter_folder_names_remove_line_breaks_and_windows_control_characters(self):
        raw = "GOD \r\n SLAYING\rINCARNATION OF\nDESTRUCTION / DOG GOD"
        result = safe_name(raw)
        self.assertNotRegex(result, r"[\x00-\x1f\x7f-\x9f]")
        self.assertNotRegex(result, r'[<>:"/\\|?*]')
        self.assertIn("GOD", result)
        self.assertEqual(result, safe_name(raw))
        self.assertEqual(GenerationManager._safe_title(raw), result)

    def test_chapter_folder_names_handle_reserved_devices_and_bound_long_titles(self):
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertEqual(safe_name("NUL.txt"), "_NUL.txt")
        long_title = "A" * 400
        first = safe_name(long_title)
        self.assertEqual(len(first), 120)
        self.assertEqual(first, safe_name(long_title))
        self.assertNotEqual(first, safe_name("B" * 400))

    def test_pacing_retries_transient_windows_access_denied_and_commits_once_unlocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "00001.wav"
            _write_wav(path, frames=100)
            real_replace = os.replace
            attempts = {"count": 0}

            def flaky_replace(source, destination):
                attempts["count"] += 1
                if attempts["count"] < 3:
                    error = PermissionError(5, "Access is denied")
                    error.winerror = 5
                    raise error
                return real_replace(source, destination)

            with patch("app.tts.pacing.os.replace", side_effect=flaky_replace), \
                 patch("app.tts.pacing.time.sleep"):
                append_silence(path, 100)

            self.assertEqual(attempts["count"], 3)
            self.assertEqual(_wav_frame_count(path), 100 + 2205)
            self.assertEqual(list(Path(temporary).glob("*.pacing.wav")), [])

    def test_pacing_preserves_original_chunk_and_cleans_temp_when_windows_lock_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "00001.wav"
            _write_wav(path, frames=100)
            original = path.read_bytes()

            def always_locked(_source, _destination):
                error = PermissionError(5, "Access is denied")
                error.winerror = 5
                raise error

            with patch("app.tts.pacing.os.replace", side_effect=always_locked), \
                 patch("app.tts.pacing.time.sleep"):
                with self.assertRaises(PermissionError):
                    append_silence(path, 100)

            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(_wav_frame_count(path), 100)
            self.assertEqual(list(Path(temporary).glob("*.pacing.wav")), [])

    def test_unassigned_dialogue_uses_third_person_while_narration_stays_with_narrator(self):
        router = CastAwareProvider(
            narrator_provider=_UnusedProvider(),
            narrator_voice="Narrator",
            profiles={},
            assignments={},
            unassigned_voice="Third Person",
        )
        parts = router.split_for_cast(
            'Before the door opened. “Stay back!” The hallway fell quiet.',
            "Narrator",
        )
        self.assertIn(("Before the door opened.", "Narrator"), parts)
        self.assertIn(("Stay back!", "Third Person"), parts)
        self.assertIn(("The hallway fell quiet.", "Narrator"), parts)

    def test_third_person_profile_changes_legacy_automatic_narrator_only_default(self):
        legacy_auto_state = {"narrator_only_generation": True}
        self.assertFalse(narrator_only_for_generation(legacy_auto_state, 0, True))
        self.assertTrue(narrator_only_for_generation(legacy_auto_state, 0, False))

    def test_explicit_per_book_narrator_only_choice_overrides_third_person_default(self):
        explicit_on = {
            "narrator_only_generation": True,
            "narrator_only_generation_user_choice": True,
        }
        explicit_off = {
            "narrator_only_generation": False,
            "narrator_only_generation_user_choice": True,
            "narrator_only_generation_user_opt_out": True,
        }
        self.assertTrue(narrator_only_for_generation(explicit_on, 0, True))
        self.assertFalse(narrator_only_for_generation(explicit_off, 0, True))

    def test_production_status_labels_clip_and_show_full_text_only_on_overflow(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("installProductionOverflowTooltips", adapter)
        self.assertIn("ryu-production-overflow-tooltip", adapter)
        self.assertIn("dataset.ryuFullText", adapter)
        self.assertIn("-webkit-line-clamp:2", adapter)
        self.assertIn("ryu-gen-percent-value", adapter)
        self.assertIn("ryu-gen-percent-label", adapter)
        self.assertIn("scheduleProductionOverflowRefresh", adapter)

    def test_dropdowns_retain_native_select_action_and_webengine_page_focus(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("installNativeDropdownSupport", adapter)
        self.assertIn("select.showPicker()", adapter)
        self.assertIn("select:not(:disabled){pointer-events:auto!important", adapter)
        self.assertIn("Qt.FocusPolicy.StrongFocus", host)
        self.assertIn("FocusOnNavigationEnabled", host)
        self.assertIn("self.web.setFocus", host)

    def test_official_drake_and_fang_cursor_assets_are_packaged_as_valid_pngs(self):
        for file_name in ("drake_cursor_32.png", "fang_cursor_32.png"):
            image = ROOT / "assets" / file_name
            data = image.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (32, 32))

    def test_icon_pack_settings_use_drake_fang_and_persistent_custom_import(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('data-icon-pack="drake"', adapter)
        self.assertIn('data-icon-pack="fang"', adapter)
        self.assertIn("Import custom icon", adapter)
        self.assertIn('"icon.pack.import": self._icon_pack_import', host)
        self.assertIn('settings_root() / "Icon Packs"', host)
        self.assertIn('"drake": assets_directory / "drake_cursor_32.png"', host)
        self.assertIn('"fang": assets_directory / "fang_cursor_32.png"', host)
        self.assertIn("ROOT / 'assets' / 'drake_cursor_32.png'};assets", build)
        self.assertIn("ROOT / 'assets' / 'fang_cursor_32.png'};assets", build)

    def test_third_person_role_is_visible_and_separate_from_narrator_profile(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        generation_mode = (ROOT / "app" / "tts" / "generation_mode.py").read_text(encoding="utf-8")
        self.assertIn("Third Person Voice · Global Default", adapter)
        self.assertIn("ordinary narration", adapter)
        self.assertIn("narrator_only_for_generation", host)
        self.assertIn("narrator_only_generation_user_choice", host)
        self.assertIn("third_person_profile_available", generation_mode)
        self.assertIn("narrator_only_for_generation(", host.split("narrator_only_automatic =")[0])


if __name__ == "__main__":
    unittest.main()
