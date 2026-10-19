from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ui.premium_v2_host import PremiumV2Bridge


class PremiumV2VoiceSaveTests(unittest.TestCase):
    def test_chatterbox_profile_is_persisted_without_explicit_voice_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"test reference placeholder")
            voices = root / "voices"

            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                bridge = PremiumV2Bridge()
                result = bridge._voice_save({
                    "name": "Test Chatterbox",
                    "provider": "chatterbox",
                    "sample_path": str(sample),
                    "authorized": True,
                })

                self.assertTrue(result["saved"])
                self.assertEqual(result["voice_id"], "Test Chatterbox")
                self.assertEqual(result["provider"], "chatterbox")
                self.assertEqual(result["count"], 1)

                catalogue = voices / "voices.json"
                self.assertTrue(catalogue.is_file())
                saved = catalogue.read_text(encoding="utf-8")
                self.assertIn('"name": "Test Chatterbox"', saved)
                self.assertIn('"voice_id": "Test Chatterbox"', saved)

    def test_chatterbox_profile_requires_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"test reference placeholder")
            voices = root / "voices"

            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                bridge = PremiumV2Bridge()
                with self.assertRaisesRegex(ValueError, "permission"):
                    bridge._voice_save({
                        "name": "Unauthorized Test",
                        "provider": "chatterbox",
                        "sample_path": str(sample),
                        "authorized": False,
                    })
                self.assertFalse((voices / "voices.json").exists())


if __name__ == "__main__":
    unittest.main()
