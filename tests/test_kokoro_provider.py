import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.tts.providers.kokoro import KOKORO_VOICES, KokoroProvider


class KokoroProviderTests(unittest.TestCase):
    def test_voice_catalog_is_broad_and_contains_core_english_voices(self):
        self.assertGreaterEqual(len(KOKORO_VOICES), 40)
        for voice in ("af_heart", "af_sarah", "am_michael", "bf_emma", "bm_george"):
            self.assertIn(voice, KOKORO_VOICES)

    def test_voice_language_mapping(self):
        self.assertEqual(KokoroProvider._language_for_voice("af_sarah"), "en-us")
        self.assertEqual(KokoroProvider._language_for_voice("bm_george"), "en-gb")
        self.assertEqual(KokoroProvider._language_for_voice("jf_alpha"), "ja")
        self.assertEqual(KokoroProvider._language_for_voice("zf_xiaobei"), "cmn")

    def test_missing_assets_are_reported_without_loading_runtime(self):
        with TemporaryDirectory() as tmp:
            with patch("app.tts.providers.kokoro.models_root", return_value=Path(tmp)):
                provider = KokoroProvider()
                self.assertIsNone(provider.model_path)
                self.assertIsNone(provider.voices_path)
                self.assertFalse(KokoroProvider.assets_available())
                with self.assertRaisesRegex(RuntimeError, "voice assets are not installed"):
                    provider.synthesize("Hello world.", Path(tmp) / "out.wav")

    def test_invalid_voice_is_rejected_before_runtime_load(self):
        provider = KokoroProvider(model_path=Path("model.onnx"), voices_path=Path("voices.bin"))
        with self.assertRaisesRegex(ValueError, "Unknown Kokoro voice"):
            provider.synthesize("Hello world.", Path("out.wav"), voice="not-a-voice")


if __name__ == "__main__":
    unittest.main()
