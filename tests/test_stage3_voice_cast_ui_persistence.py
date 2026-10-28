"""Qt-level regression for visible and persisted Voice Cast assignments."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app.core.state import load_state, save_state
from app.tts.voice_profile import VoiceProfile
from app.ui.voice_cast_page import VoiceCastPage


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
                    "name": "Mira",
                    "role": "Supporting character",
                    "dialogue_count": 2,
                    "examples": ["Wait here."],
                    "confidence": 0.91,
                    "aliases": ["Miri"],
                }],
            })
            host = QWidget()
            host.project = SimpleNamespace(folder=folder)
            profile = VoiceProfile(
                name="Mira Voice",
                provider="piper",
                voice_id="en_US-lessac-medium",
            )
            try:
                with patch("app.ui.voice_cast_page.load_profiles", return_value=[profile]):
                    first_page = VoiceCastPage(lambda: [], parent=host)
                    self.app.processEvents()
                    self.assertEqual(first_page.rows[0]["name"], "Mira")
                    self.assertIsNone(first_page.rows[0]["voice"])

                    first_page.list.setCurrentRow(0)
                    first_page.profile.setCurrentIndex(
                        first_page.profile.findData("Mira Voice")
                    )
                    first_page.assign_voice()
                    self.app.processEvents()

                    self.assertEqual(first_page.rows[0]["voice"], "Mira Voice")
                    self.assertIn("assigned", first_page.list.item(0).text().casefold())
                    self.assertEqual(load_state(folder)["voice_cast"]["Mira"], "Mira Voice")

                    # Recreate the actual widget against the same project state,
                    # as occurs when the user navigates away and returns.
                    second_page = VoiceCastPage(lambda: [], parent=host)
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
