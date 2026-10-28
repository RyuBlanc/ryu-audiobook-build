"""Stage 3 focused behavior checks on the full-feature character bridge."""
import os
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app.chapters.detector import Chapter
from app.core.project import Project
from app.core.state import load_state, save_state
from app.tts.voice_profile import VoiceProfile
from app.ui.premium_v2_host import PremiumV2Bridge
from app.ui.voice_cast_page import VoiceCastPage
from app.ui.voice_page import VoicePage


class BridgeHarness:
    def __init__(self, project):
        self.project = project

    def _active_project(self):
        return self.project

    def _find_profile(self, name):
        return {"name": name} if str(name).casefold() in {"mira voice", "ren voice"} else None

    def _now(self):
        return "2026-10-28T00:00:00Z"


class Stage3FullFeatureCharacterSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.project = Project(
            "Stage 3 regression book",
            self.folder,
            chapters=[Chapter(1, "Chapter 1", "Mira said, “Wait here.” Ren answered, “I will.”")],
        )
        self.project.save()
        self.bridge = BridgeHarness(self.project)

    def test_case_insensitive_partial_update_preserves_user_metadata(self):
        save_state(self.folder, {
            "characters": [{
                "name": "Mira", "role": "Lead",
                "short_description": "Saved description",
                "notes": "Keep this note", "scope": "Current book only",
                "voice_profile": "Mira Voice", "aliases": ["Captain Mira"],
            }]
        })
        result = PremiumV2Bridge._character_update(self.bridge, {
            "original_name": "mIrA", "name": "Mira",
            "aliases": ["Captain Mira", "Captain Mira", "Mira Vale"],
        })
        saved = load_state(self.folder)["characters"][0]
        self.assertTrue(result["saved"])
        self.assertEqual(saved["role"], "Lead")
        self.assertEqual(saved["short_description"], "Saved description")
        self.assertEqual(saved["notes"], "Keep this note")
        self.assertEqual(saved["voice_profile"], "Mira Voice")
        self.assertEqual(saved["aliases"], ["Captain Mira", "Mira Vale"])

    def test_duplicate_rename_rejected_without_mutating_state(self):
        original = {"characters": [
            {"name": "Mira", "aliases": []},
            {"name": "Ren", "aliases": []},
        ]}
        save_state(self.folder, original)
        with self.assertRaisesRegex(ValueError, "already uses that name"):
            PremiumV2Bridge._character_update(self.bridge, {
                "original_name": "Ren", "name": "mIRA",
            })
        self.assertEqual(load_state(self.folder)["characters"], original["characters"])

    def test_delete_is_blocked_until_assigned_dialogue_is_reassigned(self):
        text = self.project.chapters[0].text
        start = text.index("Wait here.")
        self.project.chapters[0].dialogue_assignments = [{
            "start": start, "end": start + len("Wait here."),
            "text": "Wait here.", "speaker": "Mira",
            "speakers": ["Mira"], "source": "manual",
        }]
        self.project.save()
        save_state(self.folder, {
            "characters": [
                {"name": "Mira", "aliases": ["Captain Mira"]},
                {"name": "Ren", "aliases": []},
            ],
            "voice_cast": {
                "Mira": "Mira Voice", "Captain Mira": "Mira Voice",
                "Ren": "Ren Voice",
            },
        })
        state_before = load_state(self.folder)
        with self.assertRaisesRegex(ValueError, "Reassign or unassign"):
            PremiumV2Bridge._character_delete(self.bridge, {"name": "mira"})
        self.assertEqual(load_state(self.folder), state_before)
        reloaded = Project.load(self.folder)
        self.assertEqual(reloaded.chapters[0].dialogue_assignments[0]["speaker"], "Mira")


class VoicePreviewRequestRaceTests(unittest.TestCase):
    def _page(self, active_request_id, current_worker=None):
        page = SimpleNamespace(
            _preview_request_id=active_request_id,
            preview_worker=current_worker,
            last_preview=None,
            engine_messages=[],
            status_messages=[],
        )
        page._preview_request_is_current = MethodType(VoicePage._preview_request_is_current, page)
        page._discard_preview_output = VoicePage._discard_preview_output
        page._set_preview_engine_status_text = lambda value: page.engine_messages.append(value)
        page._set_status_text = lambda value: page.status_messages.append(value)
        return page

    def test_stale_status_callback_cannot_overwrite_current_status(self):
        page = self._page(active_request_id=12)
        VoicePage._preview_worker_status(page, "stale worker status", request_id=11)
        self.assertEqual(page.engine_messages, [])
        self.assertEqual(page.status_messages, [])

    def test_stale_success_discards_its_audio_without_replacing_current_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            stale_audio = Path(temporary) / "stale-preview.wav"
            current_audio = Path(temporary) / "current-preview.wav"
            stale_audio.write_bytes(b"stale preview")
            current_audio.write_bytes(b"current preview")
            page = self._page(active_request_id=8)
            page.last_preview = current_audio
            VoicePage._preview_worker_ok(page, str(stale_audio), 12.0, request_id=7)
            self.assertFalse(stale_audio.exists())
            self.assertTrue(current_audio.exists())
            self.assertEqual(page.last_preview, current_audio)

    def test_stale_failure_discards_output_without_showing_old_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            stale_audio = Path(temporary) / "stale-failed-preview.wav"
            stale_audio.write_bytes(b"stale output")
            page = self._page(active_request_id=20)
            VoicePage._preview_worker_failed(
                page, "obsolete provider failure", request_id=19, output_path=stale_audio
            )
            self.assertFalse(stale_audio.exists())
            self.assertEqual(page.engine_messages, [])
            self.assertEqual(page.status_messages, [])

    def test_late_old_worker_finish_does_not_clear_newer_worker(self):
        old_worker, current_worker = object(), object()
        page = self._page(active_request_id=25, current_worker=current_worker)
        VoicePage._preview_worker_finished(page, request_id=24, worker=old_worker)
        self.assertIs(page.preview_worker, current_worker)

    def test_request_id_guard_accepts_only_the_active_request(self):
        page = self._page(active_request_id=31)
        self.assertTrue(VoicePage._preview_request_is_current(page, 31))
        self.assertFalse(VoicePage._preview_request_is_current(page, 30))


class VoiceCastPagePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_assignment_is_visible_and_survives_recreating_the_cast_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "book"
            save_state(folder, {
                "voice_cast": {},
                "voice_cast_character_roster": [{
                    "name": "Mira", "role": "Supporting character",
                    "dialogue_count": 2, "examples": ["Wait here."],
                    "confidence": 0.91, "aliases": ["Miri"],
                }],
            })
            host = QWidget()
            host.project = SimpleNamespace(folder=folder)
            profile = VoiceProfile(
                name="Mira Voice", provider="piper", voice_id="en_US-lessac-medium"
            )
            try:
                with patch("app.ui.voice_cast_page.load_profiles", return_value=[profile]):
                    first_page = VoiceCastPage(lambda: [], parent=host, get_project=lambda: SimpleNamespace(folder=folder))
                    first_page.load_current_project()
                    self.app.processEvents()
                    self.assertEqual(first_page.rows[0]["name"], "Mira")
                    self.assertIsNone(first_page.rows[0]["voice"])
                    first_page.refresh_profiles()
                    first_page.list.setCurrentRow(0)
                    target_profile = first_page.profile.findData("Mira Voice")
                    self.assertGreaterEqual(target_profile, 0)
                    first_page.profile.setCurrentIndex(target_profile)
                    self.assertEqual(first_page.profile.currentData(), "Mira Voice")
                    first_page.assign_voice()
                    self.app.processEvents()
                    self.assertEqual(first_page.rows[0]["voice"], "Mira Voice")
                    self.assertIn("assigned", first_page.list.item(0).text().casefold())
                    self.assertEqual(load_state(folder)["voice_cast"]["Mira"], "Mira Voice")
                    second_page = VoiceCastPage(lambda: [], parent=host, get_project=lambda: SimpleNamespace(folder=folder))
                    second_page.load_current_project()
                    second_page.refresh_profiles()
                    self.app.processEvents()
                    self.assertEqual(second_page.rows[0]["voice"], "Mira Voice")
                    self.assertIn("assigned", second_page.list.item(0).text().casefold())
                    self.assertEqual(second_page.profile.findData("Mira Voice"), 0)
                    second_page.deleteLater()
                    first_page.deleteLater()
                    self.app.processEvents()
            finally:
                host.close()
                host.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
